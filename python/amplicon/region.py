"""Turn primer hit(s) into the oriented consensus window the AB1 synthesizer renders.

FAIS: single primer -> 800 bp downstream of its 3' end, in the matched strand's direction.
WAIS: forward + reverse primers -> the region between them (RC-aware), reading 5'->3' in
the forward primer's direction.

A primer that can't be located under the mismatch threshold yields a structured QC failure
("possible wrong primer selected") — never a guessed window. Coordinates are 0-based,
half-open, on the *forward* consensus; `seq` is already oriented (reverse-complemented when
the read runs on the bottom strand). Counts are oriented to match via `orient_counts`.
"""
from collections import namedtuple

from .match import find_primer, revcomp

FAIS_DOWNSTREAM = 800   # FAIS "single primer + 800 bp strict cutoff"

# ok: bool; status/message describe a QC outcome; seq is the oriented window (None on fail).
RegionResult = namedtuple(
    "RegionResult", "ok status message seq start end strand revcomp hits")


def _fail(status, message):
    return RegionResult(False, status, message, None, None, None, None, None, {})


def orient_counts(counts, start, end, do_revcomp):
    """Slice per-position (a,c,g,t) counts to [start,end) and orient to match the window.

    Reverse-complement = reverse order + swap A<->T, C<->G so each row tracks its base."""
    sub = counts[start:end]
    if do_revcomp:
        sub = [(t, g, c, a) for (a, c, g, t) in reversed(sub)]
    return sub


def fais_region(consensus, primer_seq, downstream=FAIS_DOWNSTREAM, max_mismatch_frac=0.10):
    """Window from the single FAIS primer's 3' end, `downstream` bp in its direction."""
    hit = find_primer(consensus, primer_seq, max_mismatch_frac)
    if hit is None:
        return _fail("primer_not_found",
                     "FAIS primer not found in consensus — possible wrong primer selected")
    if hit.strand == "+":
        start, end, rc = hit.end, min(len(consensus), hit.end + downstream), False
    else:                                   # read runs leftward on the bottom strand
        start, end, rc = max(0, hit.start - downstream), hit.start, True
    if end <= start:
        return _fail("empty_region", "no sequence downstream of the FAIS primer")
    seq = consensus[start:end]
    if rc:
        seq = revcomp(seq)
    return RegionResult(True, "ok", "", seq, start, end, hit.strand, rc, {"primer": hit})


def wais_region(consensus, primer_f_seq, primer_r_seq, max_mismatch_frac=0.10):
    """Region between the forward and reverse primers (the insert), oriented 5'->3' fwd."""
    hf = find_primer(consensus, primer_f_seq, max_mismatch_frac)
    hr = find_primer(consensus, primer_r_seq, max_mismatch_frac)
    missing = [n for n, h in (("forward", hf), ("reverse", hr)) if h is None]
    if missing:
        return _fail("primer_not_found",
                     "WAIS %s primer(s) not found in consensus — possible wrong primer "
                     "selected" % " & ".join(missing))

    hits = {"forward": hf, "reverse": hr}
    if hf.strand == "+" and hr.strand == "-":          # canonical orientation
        start, end, rc = hf.end, hr.start, False
    elif hf.strand == "-" and hr.strand == "+":        # consensus is reverse-oriented
        start, end, rc = hr.end, hf.start, True
    else:
        return _fail("primer_orientation",
                     "WAIS primers anneal to the same strand (F:%s R:%s) — check primer "
                     "selection/orientation" % (hf.strand, hr.strand))
    if end <= start:
        return _fail("primer_orientation",
                     "WAIS forward/reverse primers overlap or are out of order")
    seq = consensus[start:end]
    if rc:
        seq = revcomp(seq)
    return RegionResult(True, "ok", "", seq, start, end, "+" if not rc else "-", rc, hits)
