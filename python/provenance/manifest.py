#!/usr/bin/env python3
"""SeqLocal run-manifest emitter — the concrete center of the reproducibility goal.

One JSON manifest per run/sample, assembled INCREMENTALLY: each stage emits a fragment
(`<name>.stage.json`) hashing its real inputs/outputs at the stage boundary; a final
`merge` combines the run-level header + ordered stage fragments + deliverables into
`run-manifest.json`. Schema: docs/PLAN.md and assets/run-manifest.schema.json.

Stdlib only and Python 3.9-compatible on purpose: this runs identically under the GPU
Nextflow label (no conda — system python3) and the samtools label (ont-tools python),
and lets the Mac `-stub-run` validate wiring without extra deps. JSON is written with
sorted keys + fixed separators so identical inputs yield byte-identical output (the
determinism requirement in CLAUDE.md); timestamps are the only runtime-variable field
and can be pinned via flags for tests.

Subcommands:
    header   build the run-level header block
    stage    emit one stage block (hashes --input/--output paths)
    merge    header + stage fragments + deliverables -> validated run-manifest.json
    hash     print the sha256 of a file (shell helper)
"""
import argparse
import datetime
import hashlib
import json
import sys

MANIFEST_VERSION = "1"

# Mirrors assets/run-manifest.schema.json. Kept here so validation needs no extra dep.
SERVICE_TIERS = {"amplicon", "plasmid", "plasmid_advanced"}
STAGE_STATUSES = {"ok", "failed"}

MANIFEST_REQUIRED = [
    "manifest_version", "run_id", "sample_id", "service_tier", "site_id",
    "instrument", "operator", "pipeline", "integrity", "created_utc",
    "stages", "deliverables",
]
STAGE_REQUIRED = [
    "name", "tool", "tool_version", "params",
    "inputs", "outputs", "started_utc", "finished_utc", "status",
]


# --------------------------------------------------------------------------- helpers
def sha256(path):
    """Streaming sha256 of a file (handles large BAM/POD5 without loading to memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hashed(paths):
    """[(path, sha256)] for a list of paths, in given order (deterministic)."""
    return [{"path": str(p), "sha256": sha256(p)} for p in (paths or [])]


def _params(pairs):
    """['k=v', ...] -> {'k': 'v'} (values stay strings; loud on a missing '=')."""
    out = {}
    for item in (pairs or []):
        if "=" not in item:
            die("--param must be key=value, got: %r" % item)
        k, v = item.split("=", 1)
        out[k] = v
    return out


def _to_bool(s):
    if isinstance(s, bool):
        return s
    if str(s).lower() in ("true", "1", "yes"):
        return True
    if str(s).lower() in ("false", "0", "no"):
        return False
    die("expected a boolean, got: %r" % s)


_FORMAT_BY_SUFFIX = {
    ".ab1": "ab1", ".fastq": "fastq", ".fq": "fastq", ".fasta": "fasta",
    ".fa": "fasta", ".fna": "fasta", ".bam": "bam", ".gb": "genbank",
    ".gbk": "genbank", ".genbank": "genbank", ".vcf": "vcf", ".json": "json",
    ".tsv": "tsv", ".txt": "txt",
}


def _infer_format(path):
    """Map a deliverable path to a manifest 'format' label (handles .fastq.gz)."""
    name = str(path).lower()
    if name.endswith(".gz"):
        name = name[:-3]
    for suffix, fmt in _FORMAT_BY_SUFFIX.items():
        if name.endswith(suffix):
            return fmt
    return "other"


def die(msg):
    sys.stderr.write("ERROR (manifest): %s\n" % msg)
    sys.exit(1)


def dump(obj, path):
    """Deterministic JSON write: sorted keys, compact stable separators, trailing NL."""
    text = json.dumps(obj, sort_keys=True, indent=2, separators=(",", ": ")) + "\n"
    if path and path != "-":
        with open(path, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


# --------------------------------------------------------------------------- validate
def validate(manifest):
    """Loud structural + enum check matching the JSON Schema. Raises SystemExit on fail."""
    for key in MANIFEST_REQUIRED:
        if key not in manifest:
            die("manifest missing required key: %s" % key)
    tier = manifest.get("service_tier")
    if tier not in (None, "") and tier not in SERVICE_TIERS:
        die("service_tier %r not in %s" % (tier, sorted(SERVICE_TIERS)))
    for sub in ("git_commit", "code_sha256", "container_digest"):
        if sub not in manifest["pipeline"]:
            die("pipeline block missing key: %s" % sub)
    for sub in ("code_hash_verified", "kill_flag_present"):
        if sub not in manifest["integrity"]:
            die("integrity block missing key: %s" % sub)
    if not isinstance(manifest["stages"], list):
        die("stages must be a list")
    for st in manifest["stages"]:
        for key in STAGE_REQUIRED:
            if key not in st:
                die("stage %r missing required key: %s" % (st.get("name"), key))
        if st["status"] not in STAGE_STATUSES:
            die("stage %r status %r not in %s"
                % (st.get("name"), st["status"], sorted(STAGE_STATUSES)))
    if not isinstance(manifest["deliverables"], list):
        die("deliverables must be a list")
    return manifest


# --------------------------------------------------------------------------- commands
def cmd_hash(args):
    print(sha256(args.path))


def cmd_stage(args):
    started = args.started or now_utc()
    finished = args.finished or now_utc()
    block = {
        "name": args.name,
        "tool": args.tool,
        "tool_version": args.tool_version,
        "model": args.model,                 # null for non-model stages (e.g. demux)
        "params": _params(args.param),
        "seed": args.seed,                   # null unless a stochastic step set it
        "inputs": _hashed(args.input),
        "outputs": _hashed(args.output),
        "started_utc": started,
        "finished_utc": finished,
        "status": args.status,
    }
    if args.status not in STAGE_STATUSES:
        die("status %r not in %s" % (args.status, sorted(STAGE_STATUSES)))
    dump(block, args.out)


def cmd_header(args):
    header = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": args.run_id or "",
        "sample_id": args.sample_id or "",
        "service_tier": args.service_tier or "",
        "site_id": args.site_id or "",
        "instrument": {
            "device": args.instrument or "",
            "flow_cell_id": args.flow_cell_id or "",
            "run_uuid": args.run_uuid or "",
        },
        "operator": args.operator or "",
        "pipeline": {
            "git_commit": args.git_commit or "",
            "code_sha256": args.code_sha256 or "",
            "container_digest": None,        # populated from M6 (containers)
        },
        "integrity": {
            "code_hash_verified": _to_bool(args.code_hash_verified),
            "kill_flag_present": _to_bool(args.kill_flag_present),
        },
        "created_utc": args.created_utc or now_utc(),
        "stages": [],
        "deliverables": [],
    }
    dump(header, args.out)


def cmd_merge(args):
    with open(args.header) as fh:
        manifest = json.load(fh)

    fragments = []
    for frag_path in (args.stage or []):
        with open(frag_path) as fh:
            fragments.append(json.load(fh))
    # Order by started_utc, then by the order given on the CLI (stable) — the
    # basecall->demux DAG already enforces the real ordering; this is belt-and-braces.
    indexed = list(enumerate(fragments))
    indexed.sort(key=lambda pair: (pair[1].get("started_utc", ""), pair[0]))
    manifest["stages"] = [frag for _, frag in indexed]

    deliverables = []
    for path in (args.deliverable or []):
        deliverables.append({
            "path": str(path),
            "sha256": sha256(path),
            "format": _infer_format(path),
        })
    manifest["deliverables"] = deliverables

    # Fail loud if any stage failed (a failed stage halts the run — PLAN.md rule).
    failed = [s["name"] for s in manifest["stages"] if s.get("status") == "failed"]
    if failed:
        die("refusing to finalize manifest; failed stage(s): %s" % ", ".join(failed))

    validate(manifest)
    dump(manifest, args.out)


# --------------------------------------------------------------------------- argparse
def build_parser():
    p = argparse.ArgumentParser(prog="manifest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("hash", help="print sha256 of a file")
    h.add_argument("path")
    h.set_defaults(func=cmd_hash)

    s = sub.add_parser("stage", help="emit one stage block")
    s.add_argument("--name", required=True)
    s.add_argument("--tool", required=True)
    s.add_argument("--tool-version", required=True)
    s.add_argument("--model", default=None)
    s.add_argument("--param", action="append", help="key=value (repeatable)")
    s.add_argument("--seed", default=None)
    s.add_argument("--input", action="append", help="input path to hash (repeatable)")
    s.add_argument("--output", action="append", help="output path to hash (repeatable)")
    s.add_argument("--started", default=None, help="UTC; defaults to now")
    s.add_argument("--finished", default=None, help="UTC; defaults to now")
    s.add_argument("--status", default="ok", choices=sorted(STAGE_STATUSES))
    s.add_argument("--out", default="-", help="output path ('-' for stdout)")
    s.set_defaults(func=cmd_stage)

    hd = sub.add_parser("header", help="build the run-level header block")
    hd.add_argument("--run-id", default=None)
    hd.add_argument("--sample-id", default=None)
    hd.add_argument("--service-tier", default=None)
    hd.add_argument("--site-id", default=None)
    hd.add_argument("--instrument", default=None)
    hd.add_argument("--flow-cell-id", default=None)
    hd.add_argument("--run-uuid", default=None)
    hd.add_argument("--operator", default=None)
    hd.add_argument("--git-commit", default=None)
    hd.add_argument("--code-sha256", default=None)
    hd.add_argument("--code-hash-verified", default="false")
    hd.add_argument("--kill-flag-present", default="false")
    hd.add_argument("--created-utc", default=None, help="UTC; defaults to now")
    hd.add_argument("--out", default="-")
    hd.set_defaults(func=cmd_header)

    m = sub.add_parser("merge", help="header + stages + deliverables -> run-manifest.json")
    m.add_argument("--header", required=True)
    m.add_argument("--stage", action="append", help="stage fragment json (repeatable)")
    m.add_argument("--deliverable", action="append", help="deliverable path (repeatable)")
    m.add_argument("--out", default="-")
    m.set_defaults(func=cmd_merge)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
