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

The wrapper asserts `dorado --version == 2.0.0`, then launches Nextflow with
`-profile conda` (override with `PROFILE=docker|singularity`). Validate the kit string
against your installed binary first:

```bash
tools/dorado/bin/dorado demux --help    # shows the valid --kit-name choices
```

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
├── demux/<KIT>_barcodeNN.bam               # per-barcode BAM + unclassified.bam
├── demux/barcoding_summary.txt             # Dorado per-read barcode assignments
├── fastq/<barcode>.fastq.gz                # per-barcode FASTQ (downstream input)
├── qc/readcounts.tsv                       # barcode, reads, PASS/LOW
└── pipeline_info/                          # versions.yml, timeline/report/trace
```

## Structural smoke test (no GPU / no data)

Validates channel wiring via process stubs — runs even on the Mac if Nextflow is
present. Use `-profile standard` (not `conda`) so it doesn't try to build the env:

```bash
mkdir -p /tmp/fake_pod5
nextflow run . -profile standard -stub-run \
  --pod5_dir /tmp/fake_pod5 --barcode_kit SQK-NBD114-24 --outdir /tmp/m1_stub
```

Launch from the repo root via `nextflow run .` (uses `manifest.mainScript`) so
`projectDir` resolves to the repo root and the `environment.yml` / `tools/` paths
hold. Expect `completed=5` with the output tree above (FASTQ excludes `unclassified`).

## Confirming the GPU path

During a real run, `nvidia-smi` should show the `dorado` process on the 4090, and the
Dorado log reports the Ada/FP8 fast path. `results/pipeline_info/versions.yml` records
the Dorado version + model for the run manifest.
