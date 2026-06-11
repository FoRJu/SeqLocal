# RUNNING.md — running the pipeline

Grows per milestone. Currently covers **M1 (basecall + demux)**. All real runs happen
on the Ubuntu RTX 4090 box (the Mac is edit-only — see `DEV_WORKFLOW.md`).

## Prerequisites (one-time, on the box)

Provision per [SETUP.md](SETUP.md): create the `ont-tools` conda env, install Dorado
2.0.0 (`bin/install_dorado.sh`) and Nextflow 26.04.3 (`bin/install_nextflow.sh`), and
download the v6.0 HAC/SUP models into `tools/dorado-models`.

## M1 — basecall + demux

```bash
bin/ont_pipeline.sh \
  --pod5_dir /nvme/run123/pod5 \
  --barcode_kit SQK-NBD114-24 \
  --outdir results
```

Before launching Nextflow the wrapper runs the integrity/kill-switch chokepoint
(non-root/`bfxsvc`, kill-flag, code-hash, MinKNOW yield) and asserts
`dorado --version == 2.0.0`, then launches with `-profile conda` (override with
`PROFILE=docker|singularity`). See [security.md](security.md) for the hardening seams.
Validate the kit string against your installed binary first:

```bash
tools/dorado/bin/dorado demux --help    # shows the valid --kit-name choices
```

### Preflight gates (entrypoint) & run-metadata flags

The wrapper refuses to run as root, refuses if the kill-flag is present, refuses on a
code-hash mismatch, and refuses if a flow cell is declared active. Relevant env:

| Env | Effect |
|-----|--------|
| `SEQLOCAL_REQUIRE_BFXSVC=1` | hard-fail unless the runtime account is `bfxsvc` (set in prod) |
| `SEQLOCAL_KILL_FLAG` | kill-flag path (default `/var/lib/seqlocal/KILL`) |
| `SEQLOCAL_CODE_HASH` | expected repo code sha256 (else `/var/lib/seqlocal/code.sha256`) |
| `SEQLOCAL_FLOWCELL_ACTIVE=1` | declare a live flow cell → refuse (yield to MinKNOW) |

Optional run-metadata flags flow into the run manifest (all default to empty / runName):
`--run_id`, `--sample_id`, `--service_tier`, `--site_id`, `--instrument`,
`--flow_cell_id`, `--run_uuid`.

### Key params (defaults in `nextflow.config`)

| Param | Default | Notes |
|-------|---------|-------|
| `--pod5_dir` | (required) | directory of POD5 files (basecall off local NVMe) |
| `--barcode_kit` | (required) | e.g. `SQK-NBD114-24`; validate vs `dorado demux --help` |
| `--basecall_model` | `hac@v6.0` | use `sup@v6.0` for high-value plasmid jobs |
| `--cuda_device` | `cuda:0` | pins the single 4090 |
| `--no_trim` | `false` | keep default ONT adapter/barcode trimming |
| `--min_reads_per_barcode` | `0` | QC warn (non-fatal) threshold |
| `--outdir` | `results` | output root |

### Outputs

```
results/
├── basecall/calls.bam                      # unaligned BAM (canonical)
├── demux/<run_id>/.../<KIT>_barcodeNN.bam  # per-barcode BAM + unclassified.bam (dorado nests by run)
├── demux/sequencing_summary.txt            # Dorado per-read barcode assignments (--emit-summary)
├── fastq/<barcode>.fastq.gz                # per-barcode FASTQ (downstream input; flat)
├── qc/readcounts.tsv                       # barcode, reads, PASS/LOW
└── pipeline_info/
    ├── run-manifest.json                   # provenance: per-stage tool/version/sha256/timestamps + deliverables
    ├── versions.yml                        # collated tool versions
    └── timeline.html / report.html / trace.txt
```

The **run manifest** (`pipeline_info/run-manifest.json`) is the reproducibility record:
the entrypoint's run-level header (operator, git commit, code hash, integrity/kill-flag
state) plus a sha256-hashed block per stage (basecall, demux) and the per-barcode
deliverables. It is schema-validated (`assets/run-manifest.schema.json`) before it lands.

## Structural smoke test (no GPU / no data)

Validates channel wiring via process stubs — runs even on the Mac if Nextflow is
present. Use `-profile standard` (not `conda`) so it doesn't try to build the env:

```bash
mkdir -p /tmp/fake_pod5
nextflow run . -profile standard -stub-run \
  --pod5_dir /tmp/fake_pod5 --barcode_kit SQK-NBD114-24 --outdir /tmp/m1_stub
```

Launch from the repo root via `nextflow run .` (entry is `main.nf` at the repo root, so
`projectDir` resolves to the repo root and the `environment.yml` / `tools/` / `python/`
paths hold). Expect `completed=6` (basecall, demux, 2× bam_to_fastq, demux_qc,
manifest_merge); FASTQ excludes `unclassified`. The stub also produces and validates
`pipeline_info/run-manifest.json`.

## Confirming the GPU path

During a real run, `nvidia-smi` should show the `dorado` process on the 4090, and the
Dorado log reports the Ada/FP8 fast path. `results/pipeline_info/versions.yml` records
the Dorado version + model for the run manifest.
