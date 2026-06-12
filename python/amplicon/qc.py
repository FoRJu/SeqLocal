"""Per-base QC FASTQ for an assembled consensus, from its realigned pileup counts.

The plasmid tier (M4) delivers the circular consensus FASTA + a per-base QC FASTQ. Quality
is consensus-derived (support of the called base / coverage), the same model the AB1 uses —
flagged to customers as not a Sanger/basecaller Phred. Deterministic; stdlib + ab1synth
parsers; reuses the `pos,A,C,G,T` counts produced by python/amplicon/pileup.py.

  python -m amplicon.qc --consensus consensus.fa --counts counts.tsv --out NAME [--name S]
"""
import argparse
import math
import sys

from ab1synth import read_consensus, read_counts   # sibling package under python/

QUAL_MAX = 60          # cap (consensus-derived, not Sanger Phred); < 128 for FASTQ safety
_BASE_IDX = {b: i for i, b in enumerate("ACGT")}


def derive_quality(counts, base):
    """Phred for the called base = confidence from support/coverage (matches ab1synth)."""
    total = sum(counts)
    if total <= 0 or base not in _BASE_IDX:
        return 0
    p = counts[_BASE_IDX[base]] / total
    q = -10.0 * math.log10(max(1.0 - p, 1e-6))
    return max(0, min(QUAL_MAX, int(round(q))))


def consensus_to_qc_fastq(seq, counts, name):
    """Build a single-record FASTQ string with per-base consensus-derived quality."""
    if len(counts) != len(seq):
        raise ValueError("counts rows (%d) != consensus length (%d)" % (len(counts), len(seq)))
    quals = [derive_quality(counts[i], b) for i, b in enumerate(seq.upper())]
    qline = "".join(chr(q + 33) for q in quals)
    return "@%s\n%s\n+\n%s\n" % (name, seq, qline)


def main(argv=None):
    p = argparse.ArgumentParser(prog="amplicon.qc", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--consensus", required=True)
    p.add_argument("--counts", required=True)
    p.add_argument("--out", required=True, help="output basename; writes <out>.qc.fastq")
    p.add_argument("--name", default=None, help="FASTQ record id (default: consensus id)")
    args = p.parse_args(argv)

    cons = read_consensus(args.consensus)
    counts = read_counts(args.counts)
    fastq = consensus_to_qc_fastq(cons.seq, counts, args.name or cons.name)
    with open(args.out + ".qc.fastq", "w") as fh:
        fh.write(fastq)
    sys.stderr.write(">> qc: %s  %d bp -> %s.qc.fastq\n" % (args.name or cons.name, len(cons.seq), args.out))


if __name__ == "__main__":
    main()
