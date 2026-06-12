"""IUPAC-aware fuzzy primer search against a consensus, on both strands.

Deterministic: scans every offset, returns the best hit (fewest mismatches, then lowest
start, then + strand before -), or None if nothing is within the mismatch threshold.
"""
from collections import namedtuple

# IUPAC code -> the set of concrete bases it represents.
_IUPAC_SETS = {
    "A": set("A"), "C": set("C"), "G": set("G"), "T": set("T"),
    "R": set("AG"), "Y": set("CT"), "S": set("GC"), "W": set("AT"),
    "K": set("GT"), "M": set("AC"), "B": set("CGT"), "D": set("AGT"),
    "H": set("ACT"), "V": set("ACG"), "N": set("ACGT"),
}
_COMPLEMENT = {
    "A": "T", "T": "A", "G": "C", "C": "G", "R": "Y", "Y": "R", "S": "S",
    "W": "W", "K": "M", "M": "K", "B": "V", "V": "B", "D": "H", "H": "D", "N": "N",
}

# Forward-coordinate hit: [start, end) on the consensus; strand the primer annealed to.
PrimerHit = namedtuple("PrimerHit", "start end strand mismatches")


def revcomp(seq):
    """Reverse complement, IUPAC-aware (treats unknown chars as N)."""
    return "".join(_COMPLEMENT.get(b, "N") for b in reversed(seq))


def _base_match(p, t):
    """True if IUPAC primer base p is compatible with consensus base t (sets overlap)."""
    return bool(_IUPAC_SETS.get(p, set()) & _IUPAC_SETS.get(t, set()))


def _count_mismatches(probe, target, cap):
    """Mismatches between probe and equal-length target; early-exit once it exceeds cap."""
    mm = 0
    for p, t in zip(probe, target):
        if not _base_match(p, t):
            mm += 1
            if mm > cap:
                return mm
    return mm


def find_primer(consensus, primer, max_mismatch_frac=0.10):
    """Best fuzzy hit of `primer` in `consensus` over both strands, or None.

    Allows up to floor(len(primer) * max_mismatch_frac) mismatches. Deterministic
    tie-break: fewer mismatches, then lower start, then + before -."""
    consensus = consensus.upper()
    primer = primer.upper()
    L = len(primer)
    if L == 0 or L > len(consensus):
        return None
    cap = int(L * max_mismatch_frac)

    best = None
    # "+" first so it wins an exact tie on (mismatches, start).
    for strand, probe in (("+", primer), ("-", revcomp(primer))):
        for i in range(0, len(consensus) - L + 1):
            mm = _count_mismatches(probe, consensus[i:i + L], cap)
            if mm > cap:
                continue
            cand = PrimerHit(i, i + L, strand, mm)
            if best is None or (cand.mismatches, cand.start) < (best.mismatches, best.start):
                best = cand
    return best
