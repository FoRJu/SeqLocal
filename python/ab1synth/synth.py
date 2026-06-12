"""Orchestrate AB1 synthesis: (consensus + per-position pileup counts) -> ab1/fasta/fastq.

The bespoke ABIF encoding lives in abif.py; trace channel generation in trace.py. This
module parses inputs, validates them loudly, applies the delivery-mode window/cutoffs,
derives per-base quality, and assembles the ABIF tag set + the text deliverables.

Quality is **consensus-derived, not Sanger Phred** (CLAUDE.md): it reflects how strongly
the pileup supports the called base, not a real basecaller Phred — flag this to customers.
"""
import math

from . import abif
from .trace import BASE_ORDER, synthesize

_BASE_IDX = {b: i for i, b in enumerate(BASE_ORDER)}   # A/C/G/T -> 0..3
PCON_DERIVED_MAX = 60      # cap for pileup-derived quality
PCON_DECODE_MAX = 93       # hard cap so PCON bytes stay < 128 (Biopython utf-8 decode)
VALID_BASES = set("ACGTN")


class Consensus:
    """A parsed consensus: name, sequence (upper), optional per-base Phred (FASTQ)."""

    def __init__(self, name, seq, quals=None):
        self.name = name
        self.seq = seq.upper()
        self.quals = quals


# --------------------------------------------------------------------------- parsing
def read_consensus(path):
    """Parse a single-record FASTA or FASTQ consensus. FASTQ supplies real per-base Phred."""
    with open(path) as fh:
        text = fh.read()
    if not text.strip():
        raise ValueError("empty consensus file: %s" % path)
    if text[0] == ">":
        lines = text.splitlines()
        name = lines[0][1:].split()[0] if lines[0][1:].strip() else "consensus"
        seq = "".join(l.strip() for l in lines[1:] if l and not l.startswith(">"))
        if not seq:
            raise ValueError("FASTA consensus has no sequence: %s" % path)
        return Consensus(name, seq)
    if text[0] == "@":
        lines = text.splitlines()
        if len(lines) < 4:
            raise ValueError("truncated FASTQ consensus: %s" % path)
        name = lines[0][1:].split()[0] if lines[0][1:].strip() else "consensus"
        seq, qualline = lines[1], lines[3]
        if len(seq) != len(qualline):
            raise ValueError("FASTQ seq/qual length mismatch in %s" % path)
        quals = [ord(c) - 33 for c in qualline]
        return Consensus(name, seq, quals)
    raise ValueError("consensus must be FASTA (>) or FASTQ (@): %s" % path)


def read_counts(path):
    """Parse a pileup-counts TSV (`pos<TAB>A<TAB>C<TAB>G<TAB>T`) -> list of (a,c,g,t)."""
    rows = []
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if parts[0].lower() in ("pos", "position"):     # header row
                continue
            if len(parts) < 5:
                raise ValueError(
                    "counts line %d needs pos,A,C,G,T (got %d cols): %r" % (lineno, len(parts), line))
            try:
                rows.append(tuple(int(parts[i]) for i in range(1, 5)))
            except ValueError:
                raise ValueError("non-integer counts on line %d: %r" % (lineno, line))
    if not rows:
        raise ValueError("no counts rows in %s" % path)
    return rows


# --------------------------------------------------------------------------- quality
def _derive_quality(counts, base):
    """Pileup-derived Phred for the CALLED base: confidence = support / coverage."""
    total = sum(counts)
    if total <= 0 or base not in _BASE_IDX:
        return 0
    p = counts[_BASE_IDX[base]] / total
    q = -10.0 * math.log10(max(1.0 - p, 1e-6))
    return max(0, min(PCON_DERIVED_MAX, int(round(q))))


def _resolve_quals(consensus, compositions):
    """Per-base Phred over the consensus: FASTQ values if given, else pileup-derived.
    All capped < 128 so the bytes round-trip through Biopython's decode."""
    if consensus.quals is not None:
        return [max(0, min(PCON_DECODE_MAX, q)) for q in consensus.quals]
    return [_derive_quality(compositions[i], b) for i, b in enumerate(consensus.seq)]


# --------------------------------------------------------------------------- region
def _select_region(nbase, window, max_len):
    """Resolve [start, end) on the consensus from the delivery-mode args (loud on bad input)."""
    start, end = 0, nbase
    if window is not None:
        start, end = window
        if not (0 <= start < end <= nbase):
            raise ValueError("window %r out of bounds for length %d" % (window, nbase))
    if max_len is not None:
        if max_len <= 0:
            raise ValueError("--max-len must be positive, got %d" % max_len)
        end = min(end, start + max_len)        # FAIS-style hard length cutoff
    return start, end


def _apply_min_qual(quals, start, end, min_qual):
    """3' truncate the region at the first base below `min_qual` (hard quality cutoff)."""
    if min_qual is None:
        return end
    for i in range(start, end):
        if quals[i] < min_qual:
            return i
    return end


# --------------------------------------------------------------------------- assemble
def synthesize_ab1(consensus, compositions, sample_name=None,
                   window=None, max_len=None, min_qual=None):
    """Produce {ab1, fasta, fastq, region, name}. Validates inputs; never returns an empty AB1."""
    seq = consensus.seq
    nbase = len(seq)
    if nbase == 0:
        raise ValueError("empty consensus sequence")
    bad = set(seq) - VALID_BASES
    if bad:
        raise ValueError("consensus has non-ACGTN bases: %s" % sorted(bad))
    if len(compositions) != nbase:
        raise ValueError(
            "counts rows (%d) must equal consensus length (%d)" % (len(compositions), nbase))

    quals = _resolve_quals(consensus, compositions)
    start, end = _select_region(nbase, window, max_len)
    end = _apply_min_qual(quals, start, end, min_qual)
    if end <= start:
        raise ValueError("selected region is empty after cutoffs (start=%d end=%d)" % (start, end))

    sub_seq = seq[start:end]
    sub_quals = quals[start:end]
    sub_comp = compositions[start:end]
    name = sample_name or consensus.name

    channels, ploc = synthesize(sub_comp, sub_seq)
    ab1 = _build_ab1(sub_seq, sub_quals, channels, ploc, name)

    return {
        "ab1": ab1,
        "fasta": _to_fasta(name, sub_seq),
        "fastq": _to_fastq(name, sub_seq, sub_quals),
        "region": (start, end),
        "name": name,
    }


def _build_ab1(seq, quals, channels, ploc, sample_name):
    seq_b = seq.encode("ascii")
    qual_b = bytes(quals)
    tags = [
        abif.char_tag("PBAS", 1, seq_b), abif.char_tag("PBAS", 2, seq_b),
        abif.char_tag("PCON", 1, qual_b), abif.char_tag("PCON", 2, qual_b),
        abif.char_tag("FWO_", 1, BASE_ORDER),
        abif.short_tag("PLOC", 1, ploc), abif.short_tag("PLOC", 2, ploc),
        abif.char_tag("SMPL", 1, sample_name),
    ]
    # DATA1-4 (raw) and DATA9-12 (analyzed) in FWO_ base order.
    for n, b in enumerate(BASE_ORDER):
        tags.append(abif.short_tag("DATA", 1 + n, channels[b]))
        tags.append(abif.short_tag("DATA", 9 + n, channels[b]))
    return abif.write_abif(tags)


def _to_fasta(name, seq, width=70):
    body = "\n".join(seq[i:i + width] for i in range(0, len(seq), width))
    return ">%s\n%s\n" % (name, body)


def _to_fastq(name, seq, quals):
    qline = "".join(chr(q + 33) for q in quals)
    return "@%s\n%s\n+\n%s\n" % (name, seq, qline)
