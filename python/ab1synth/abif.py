"""ABIF (Applied Biosystems / .ab1) binary container writer — the bespoke core of M2.

Biopython READS ABIF but does not WRITE it, so this encoder is ours. Layout verified
against Biopython's reader (`Bio/SeqIO/AbiIO.py`) and the ABIF spec:

  - Big-endian throughout.
  - File = b"ABIF" + header struct `>H4sI2H3I` (version + the root `tdir` directory
    entry, minus its datahandle) padded to 128 bytes; then the directory array of
    28-byte entries `>4sI2H4I`; then the data region.
  - Directory entry: name(4s) number(I) elementtype(H) elementsize(H) numelements(I)
    datasize(I) dataoffset(I) datahandle(I).
  - **Inline rule:** if datasize <= 4 the payload is stored *in* the dataoffset field
    (the reader reads `datasize` bytes from entry_offset+20); otherwise dataoffset is an
    absolute file offset into the data region.
  - Element types used here: 2 = char array (PBAS/PCON/FWO_/SMPL — read back as bytes via
    `tag_data.decode()`), 4 = short/int16 array (DATA channels, PLOC peak positions).

Stdlib only (`struct`) so it runs anywhere — no third-party dependency to WRITE an AB1.
Output is byte-deterministic: directory entries are sorted by (name, number) and no
wall-clock tags are emitted.
"""
import struct
from collections import namedtuple

# Element type codes (ABIF elementtype field).
CHAR = 2     # char array  -> bytes; Biopython does tag_data.decode()
SHORT = 4    # int16 array  -> trace channels, peak locations

_HEADFMT = ">H4sI2H3I"   # version + root tdir entry (no datahandle), after the marker
_DIRFMT = ">4sIHHIII"    # one 28-byte directory entry, EXCLUDING the trailing datahandle
HEADER_SIZE = 128
DIR_ENTRY_SIZE = 28
ABIF_VERSION = 101       # 1.01
ROOT_ELEMTYPE = 1023     # directory-of-entries pseudo type used by the root `tdir`

# A fully-resolved tag ready to serialize. `data` is the raw big-endian payload bytes.
Tag = namedtuple("Tag", "name number elem_code elem_size num_elements data")


def char_tag(name, number, value):
    """Char-array tag (PBAS, PCON, FWO_, SMPL). `value` is bytes (e.g. ASCII bases,
    or quality values as raw bytes 0..255 — keep < 128 so Biopython's utf-8 decode works)."""
    if isinstance(value, str):
        value = value.encode("ascii")
    if not isinstance(value, (bytes, bytearray)):
        raise TypeError("char_tag value must be bytes/str, got %r" % type(value))
    value = bytes(value)
    return Tag(_name4(name), number, CHAR, 1, len(value), value)


def short_tag(name, number, values):
    """int16-array tag (DATA channels, PLOC). `values` is a sequence of ints in [-32768, 32767]."""
    vals = list(values)
    for v in vals:
        if not -32768 <= int(v) <= 32767:
            raise ValueError("short_tag %s value out of int16 range: %r" % (name, v))
    data = struct.pack(">%dh" % len(vals), *[int(v) for v in vals]) if vals else b""
    return Tag(_name4(name), number, SHORT, 2, len(vals), data)


def _name4(name):
    b = name.encode("ascii") if isinstance(name, str) else bytes(name)
    if len(b) != 4:
        raise ValueError("ABIF tag name must be exactly 4 bytes, got %r" % name)
    return b


def write_abif(tags, path=None, version=ABIF_VERSION):
    """Serialize `tags` (a list of Tag) to ABIF bytes; optionally write to `path`.

    Returns the bytes. Deterministic: entries sorted by (name, number); data region in the
    same order. Raises on duplicate (name, number)."""
    ordered = sorted(tags, key=lambda t: (t.name, t.number))
    seen = set()
    for t in ordered:
        key = (t.name, t.number)
        if key in seen:
            raise ValueError("duplicate ABIF tag %r%d" % (t.name.decode(), t.number))
        seen.add(key)

    n = len(ordered)
    dir_offset = HEADER_SIZE
    data_start = dir_offset + n * DIR_ENTRY_SIZE

    entries = bytearray()
    data_region = bytearray()
    cursor = data_start
    for t in ordered:
        datasize = len(t.data)
        head = struct.pack(">4sIHHII", t.name, t.number, t.elem_code,
                           t.elem_size, t.num_elements, datasize)
        if datasize <= 4:
            offset_field = t.data.ljust(4, b"\x00")[:4]   # inline payload
        else:
            offset_field = struct.pack(">I", cursor)
            data_region += t.data
            cursor += datasize
        entries += head + offset_field + struct.pack(">I", 0)  # + datahandle

    header = b"ABIF" + struct.pack(
        _HEADFMT, version, b"tdir", 1, ROOT_ELEMTYPE, DIR_ENTRY_SIZE,
        n, n * DIR_ENTRY_SIZE, dir_offset)
    header = header.ljust(HEADER_SIZE, b"\x00")

    blob = bytes(header) + bytes(entries) + bytes(data_region)
    if path is not None:
        with open(path, "wb") as fh:
            fh.write(blob)
    return blob


# --------------------------------------------------------------------------- reader
# Minimal stdlib reader for the structural self-test. The AUTHORITATIVE round-trip check
# uses Biopython (see tests); this is here so the package can validate its own output
# without a third-party dependency.
def read_abif(source):
    """Parse ABIF bytes (or a path) into {('NAME', number): value}.

    char tags -> bytes; short tags -> tuple of ints. Mirrors Biopython's inline rule."""
    if isinstance(source, (bytes, bytearray)):
        buf = bytes(source)
    else:
        with open(source, "rb") as fh:
            buf = fh.read()

    if buf[:4] != b"ABIF":
        raise ValueError("not an ABIF file (bad marker %r)" % buf[:4])
    version, name, number, etype, esize, nelem, dsize, doff = struct.unpack(
        _HEADFMT, buf[4:4 + struct.calcsize(_HEADFMT)])

    out = {}
    for i in range(nelem):
        start = doff + i * DIR_ENTRY_SIZE
        e_name, e_num, e_etype, e_esize, e_nelem, e_dsize, e_doff, _handle = struct.unpack(
            ">4sIHHIIII", buf[start:start + DIR_ENTRY_SIZE])
        if e_dsize <= 4:
            raw = buf[start + 20:start + 20 + e_dsize]      # inline: at entry+20
        else:
            raw = buf[e_doff:e_doff + e_dsize]
        out[(e_name.decode(), e_num)] = _decode(e_etype, e_nelem, raw)
    return {"_version": version, **out}


def _decode(etype, nelem, raw):
    if etype == CHAR:
        return raw
    if etype == SHORT:
        return struct.unpack(">%dh" % nelem, raw) if nelem else ()
    return raw  # unknown types returned as raw bytes
