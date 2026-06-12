"""amplicon CLI: per-barcode consensus + counts + order -> AB1 (FAIS/WAIS) + QC.

Given an assembled consensus and its per-position pileup counts, look up the sample's order
(via the sample sheet), resolve its primers, extract the FAIS/WAIS window, and render the
AB1 with python/ab1synth. A primer that can't be located writes a QC record and emits NO
AB1 (recognized outcome, not a crash). Always writes <out>.qc.json.

  python -m amplicon --barcode barcode05 --consensus C.fa --counts P.tsv \
      --samplesheet samplesheet.csv --order ORDER.json [--order ...] \
      --primers assets/primers.csv --out NAME [--max-mismatch-frac 0.10] [--manifest-out F]
"""
import argparse
import json
import os
import sys

from . import __version__
from .orders import load_samplesheet, load_orders, join
from .region import fais_region, wais_region, orient_counts
from . import registry as reg

# ab1synth is a sibling package under python/ (added to sys.path when run as a module).
from ab1synth import read_consensus, read_counts, Consensus
from ab1synth.synth import synthesize_ab1


def build_parser():
    p = argparse.ArgumentParser(prog="amplicon", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--barcode", required=True)
    p.add_argument("--consensus", required=True, help="assembled consensus FASTA")
    p.add_argument("--counts", required=True, help="pileup counts TSV (pos,A,C,G,T)")
    p.add_argument("--samplesheet", required=True)
    p.add_argument("--order", action="append", required=True, help="order detail CSV (repeatable)")
    p.add_argument("--primers", required=True, help="repo primer registry CSV")
    p.add_argument("--out", required=True, help="output basename")
    p.add_argument("--max-mismatch-frac", type=float, default=0.10)
    p.add_argument("--manifest-out", default=None)
    return p


def _hit_json(name, hit):
    return None if hit is None else {
        "name": name, "start": hit.start, "end": hit.end,
        "strand": hit.strand, "mismatches": hit.mismatches}


def main(argv=None):
    args = build_parser().parse_args(argv)

    jobs = join(load_samplesheet(args.samplesheet), load_orders(args.order))
    matches = [j for j in jobs if j.barcode == args.barcode]
    if len(matches) != 1:
        sys.exit("ERROR: expected exactly one sample-sheet row for %s, found %d"
                 % (args.barcode, len(matches)))
    job = matches[0]

    registry = reg.merge_customer(reg.load_registry(args.primers), job.customer_primers)

    consensus = read_consensus(args.consensus).seq
    counts = read_counts(args.counts)
    if len(counts) != len(consensus):
        sys.exit("ERROR: counts rows (%d) != consensus length (%d)"
                 % (len(counts), len(consensus)))

    if job.assay == "FAIS":
        primer = reg.resolve(job.single_primer, registry)
        result = fais_region(consensus, primer, max_mismatch_frac=args.max_mismatch_frac)
        primers_used = {"single": (job.single_primer, result.hits.get("primer"))}
    else:  # WAIS
        pf = reg.resolve(job.primer_f, registry)
        pr = reg.resolve(job.primer_r, registry)
        result = wais_region(consensus, pf, pr, max_mismatch_frac=args.max_mismatch_frac)
        primers_used = {"forward": (job.primer_f, result.hits.get("forward")),
                        "reverse": (job.primer_r, result.hits.get("reverse"))}

    qc = {
        "barcode": job.barcode, "sample_id": job.sample_id, "order_id": job.order_id,
        "assay": job.assay, "status": result.status, "message": result.message,
        "consensus_length": len(consensus), "size_kb_expected": job.size_kb,
        "primers": {role: _hit_json(nm, hit) for role, (nm, hit) in primers_used.items()},
        "region": (None if not result.ok else {
            "start": result.start, "end": result.end, "strand": result.strand,
            "revcomp": result.revcomp, "length": len(result.seq)}),
    }
    with open(args.out + ".qc.json", "w") as fh:
        json.dump(qc, fh, sort_keys=True, indent=2)
        fh.write("\n")

    if not result.ok:
        sys.stderr.write(">> QC FAIL [%s/%s]: %s\n" % (job.sample_id, job.assay, result.message))
        return  # recognized QC outcome; no AB1 emitted, exit 0

    sub_counts = orient_counts(counts, result.start, result.end, result.revcomp)
    out = synthesize_ab1(Consensus(job.sample_id, result.seq), sub_counts)
    ab1_path = args.out + ".ab1"
    with open(ab1_path, "wb") as fh:
        fh.write(out["ab1"])
    with open(args.out + ".fasta", "w") as fh:
        fh.write(out["fasta"])
    with open(args.out + ".fastq", "w") as fh:
        fh.write(out["fastq"])
    sys.stderr.write(">> amplicon %s [%s]: region [%d,%d) len=%d -> %s.{ab1,fasta,fastq}\n"
                     % (job.sample_id, job.assay, result.start, result.end,
                        len(result.seq), args.out))

    if args.manifest_out:
        _emit_manifest(args.manifest_out, args.consensus, ab1_path, job, result)


def _emit_manifest(out_path, consensus_path, ab1_path, job, result):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # python/
    from provenance import manifest
    argv = ["stage", "--name", "amplicon", "--tool", "amplicon",
            "--tool-version", __version__,
            "--input", consensus_path, "--output", ab1_path, "--status", "ok",
            "--param", "assay=%s" % job.assay, "--param", "sample_id=%s" % job.sample_id,
            "--param", "region_start=%d" % result.start,
            "--param", "region_end=%d" % result.end,
            "--param", "strand=%s" % result.strand,
            "--out", out_path]
    manifest.main(argv)


if __name__ == "__main__":
    main()
