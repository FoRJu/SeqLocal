"""Convert `samtools mpileup` output into the per-position A/C/G/T counts TSV M2 consumes.

Reads a consensus FASTA (to know length, and to resolve '.'/',' match symbols to the ref
base) and mpileup lines on stdin; writes `pos<TAB>A<TAB>C<TAB>G<TAB>T`, one row per
consensus base (zero-coverage positions emitted as 0,0,0,0 so the TSV length always equals
the consensus length — the contract python/ab1synth requires).

  minimap2 -a consensus.fa reads.fastq | samtools sort - | samtools mpileup -f consensus.fa - \
    | python -m amplicon.pileup consensus.fa > counts.tsv
"""
import sys


def read_fasta_len(path):
    """Length of the (single-record) consensus FASTA."""
    seq = []
    with open(path) as fh:
        for line in fh:
            if line.startswith(">"):
                if seq:
                    break
                continue
            seq.append(line.strip())
    return len("".join(seq))


def count_bases(read_bases, ref):
    """A/C/G/T counts from one mpileup read-base column (handles ^ $ +N -N * markers)."""
    counts = {"A": 0, "C": 0, "G": 0, "T": 0}
    ref = ref.upper()
    i, n = 0, len(read_bases)
    while i < n:
        c = read_bases[i]
        if c == "^":            # read start: skip the following mapping-quality char
            i += 2
            continue
        if c == "$":            # read end marker
            i += 1
            continue
        if c in "+-":           # indel: +N<bases> / -N<bases> — skip N bases
            j = i + 1
            num = ""
            while j < n and read_bases[j].isdigit():
                num += read_bases[j]
                j += 1
            i = j + (int(num) if num else 0)
            continue
        if c in ".,":           # match to ref (+/- strand)
            if ref in counts:
                counts[ref] += 1
            i += 1
            continue
        cu = c.upper()          # mismatch base, or '*' gap / 'N'
        if cu in counts:
            counts[cu] += 1
        i += 1
    return counts


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        sys.exit("usage: pileup.py CONSENSUS.fa  (mpileup on stdin)")
    n = read_fasta_len(argv[0])
    rows = [(0, 0, 0, 0)] * n

    for line in sys.stdin:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5:
            continue
        pos = int(parts[1]) - 1                 # mpileup is 1-based
        if not (0 <= pos < n):
            continue
        c = count_bases(parts[4], parts[2])
        rows[pos] = (c["A"], c["C"], c["G"], c["T"])

    out = sys.stdout
    out.write("pos\tA\tC\tG\tT\n")
    for i, (a, cc, g, t) in enumerate(rows):
        out.write("%d\t%d\t%d\t%d\t%d\n" % (i, a, cc, g, t))


if __name__ == "__main__":
    main()
