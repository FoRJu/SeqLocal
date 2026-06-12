"""ab1synth CLI: consensus + pileup counts -> <out>.ab1 / .fasta / .fastq.

Delivery modes are parameters (the primer detection that computes them is the M3 amplicon
tier): full consensus, a --window sub-region (WAIS between-primer case), and --max-len /
--min-qual hard cutoffs (FAIS "single primer + 800 bp strict cutoff" case).

  python -m ab1synth --consensus C.fa --counts P.tsv --out NAME \
      [--window START:END] [--max-len 800] [--min-qual 20] [--sample-name S] \
      [--manifest-out F.stage.json]
"""
import argparse
import os
import sys

from . import __version__
from .synth import read_consensus, read_counts, synthesize_ab1


def _parse_window(text):
    if text is None:
        return None
    try:
        a, b = text.split(":")
        return (int(a), int(b))
    except Exception:
        raise argparse.ArgumentTypeError("--window must be START:END (0-based), got %r" % text)


def build_parser():
    p = argparse.ArgumentParser(prog="ab1synth", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--consensus", required=True, help="consensus FASTA (>) or FASTQ (@)")
    p.add_argument("--counts", required=True,
                   help="pileup counts TSV: pos<TAB>A<TAB>C<TAB>G<TAB>T, one row per base")
    p.add_argument("--out", required=True, help="output basename; writes <out>.ab1/.fasta/.fastq")
    p.add_argument("--window", type=_parse_window, default=None,
                   help="render sub-region START:END (0-based, half-open)")
    p.add_argument("--max-len", type=int, default=None, help="hard length cutoff from region start")
    p.add_argument("--min-qual", type=int, default=None,
                   help="3' truncate at the first base below this Phred (hard quality cutoff)")
    p.add_argument("--sample-name", default=None, help="SMPL tag / record id (default: consensus id)")
    p.add_argument("--manifest-out", default=None,
                   help="also emit a provenance stage fragment JSON to this path")
    return p


def _emit_manifest(out_path, consensus_path, ab1_path, params, status="ok"):
    """Reuse python/provenance/manifest.py to write the M2 stage fragment (PLAN.md seam)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # python/
    from provenance import manifest
    argv = ["stage", "--name", "ab1synth", "--tool", "ab1synth",
            "--tool-version", __version__,
            "--input", consensus_path, "--output", ab1_path,
            "--status", status, "--out", out_path]
    for k, v in params.items():
        argv += ["--param", "%s=%s" % (k, v)]
    manifest.main(argv)


def main(argv=None):
    args = build_parser().parse_args(argv)

    consensus = read_consensus(args.consensus)
    counts = read_counts(args.counts)
    result = synthesize_ab1(
        consensus, counts, sample_name=args.sample_name,
        window=args.window, max_len=args.max_len, min_qual=args.min_qual)

    ab1_path = args.out + ".ab1"
    with open(ab1_path, "wb") as fh:
        fh.write(result["ab1"])
    with open(args.out + ".fasta", "w") as fh:
        fh.write(result["fasta"])
    with open(args.out + ".fastq", "w") as fh:
        fh.write(result["fastq"])

    start, end = result["region"]
    mode = "full" if (args.window is None and args.max_len is None and args.min_qual is None) \
        else "windowed"
    sys.stderr.write(
        ">> ab1synth: %s  region [%d,%d) len=%d  ->  %s.{ab1,fasta,fastq}\n"
        % (result["name"], start, end, end - start, args.out))

    if args.manifest_out:
        _emit_manifest(
            args.manifest_out, args.consensus, ab1_path,
            params={"mode": mode, "region_start": start, "region_end": end,
                    "max_len": args.max_len, "min_qual": args.min_qual})


if __name__ == "__main__":
    main()
