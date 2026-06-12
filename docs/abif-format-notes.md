# abif-format-notes.md — ABIF (.ab1) byte-layout reference

Working reference for the bespoke ABIF writer (`python/ab1synth/abif.py`). ONT has no
fluorescence, so we synthesize the chromatogram; Biopython **reads** ABIF but does not
**write** it, so this encoder is ours. Layout verified against Biopython's reader
(`Bio/SeqIO/AbiIO.py`) and the Applied Biosystems ABIF spec (July 2006).

## Whole-file structure

```
offset 0   : b"ABIF"                      4-byte magic marker
offset 4   : header struct ">H4sI2H3I"    version + root "tdir" directory entry
offset 30..127 : zero padding             header is 128 bytes total
offset 128 : directory array              N entries × 28 bytes (">4sI2H4I")
then       : data region                  payloads for tags whose datasize > 4
```

**All integers are big-endian.**

### Header (after the 4-byte marker), `">H4sI2H3I"`

| field | type | value we write |
|-------|------|----------------|
| version | `H` uint16 | `101` (1.01) |
| name | `4s` | `b"tdir"` |
| number | `I` | `1` |
| elementtype | `H` | `1023` (directory pseudo-type) |
| elementsize | `H` | `28` (size of one dir entry) |
| numelements | `I` | N = number of tags |
| datasize | `I` | N × 28 |
| dataoffset | `I` | `128` (directory starts right after the header) |

The reader uses `elementsize` (#4), `numelements` (#5) and `dataoffset` (#7) to walk the
directory. (Note the header struct omits the entry's trailing `datahandle`.)

### Directory entry (28 bytes), `">4sI2H4I"`

| field | type | notes |
|-------|------|-------|
| name | `4s` | tag name, exactly 4 ASCII bytes (`PBAS`, `DATA`, `FWO_`, …) |
| number | `I` | tag number (e.g. PBAS **1** vs PBAS **2**) |
| elementtype | `H` | element type code (below) |
| elementsize | `H` | bytes per element (char=1, short=2) |
| numelements | `I` | element count |
| datasize | `I` | total payload bytes = elementsize × numelements |
| dataoffset | `I` | **inline payload if datasize ≤ 4**, else absolute file offset |
| datahandle | `I` | reserved, `0` |

### Inline rule (critical)

If `datasize ≤ 4`, the payload is stored **inside the dataoffset field**. The reader reads
`datasize` bytes starting at `entry_offset + 20` (the dataoffset field's position within the
28-byte entry). We write the payload left-justified, zero-padded to 4 bytes. Example:
`FWO_` = `b"ACGT"` is exactly 4 bytes → inline.

## Element type codes (the subset we use)

| code | meaning | struct | used for |
|------|---------|--------|----------|
| 2 | char array | `s` | `PBAS`, `PCON`, `FWO_`, `SMPL` — read back as **bytes** via `tag_data.decode()` |
| 4 | short / int16 array | `h` | `DATA` channels, `PLOC` peak positions |

Others exist (1 byte, 3 word, 5 long, 7 float, 10 date, 11 time, 18/19 string) but M2 needs
only char + short. `PCON` values are stored as a char array, so each quality byte must be
**< 128** or Biopython's utf-8 `.decode()` fails — we cap Phred at 60 (derived) / 93 (supplied).

## Tags we emit

| tag | type | meaning |
|-----|------|---------|
| `PBAS1`, `PBAS2` | char | called bases. **`PBAS2` → `record.seq`** in Biopython |
| `PCON1`, `PCON2` | char | per-base quality bytes. **`PCON2` → `phred_quality`** |
| `FWO_1` | char(4) | base order for the channels, e.g. `"ACGT"` (inline) |
| `PLOC1`, `PLOC2` | short | peak x-position (trace sample index) of each base call |
| `DATA1`–`DATA4` | short | raw trace channels, in `FWO_` order |
| `DATA9`–`DATA12` | short | analyzed trace channels (what viewers display), in `FWO_` order |
| `SMPL1` | char | sample name |

`PBAS2` + `PCON2` are the minimum for Biopython to yield a sequence with qualities; the
`DATA`/`FWO_`/`PLOC` set makes it a real chromatogram for SnapGene / FinchTV / Chromas.

## Determinism

- Directory entries are written **sorted by (name, number)**; the data region follows the
  same order.
- **No wall-clock tags** (`RUND`/`RUNT` date/time) are emitted, so identical input yields a
  **byte-identical** `.ab1`. Quality is **consensus-derived, not Sanger Phred** — flagged to
  customers and recorded in the run manifest.
