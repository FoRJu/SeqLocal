# plasmid-tier.md — M4 plasmid tier + the shared assembly core

Tier-1 plasmid sequencing: reads → **assembled, circularized, polished consensus** + per-base
QC. The same `ASSEMBLE_CONSENSUS` core will later replace M3 Phase 1's provisional linear
amplicon consensus and feed WAIS insert-inference.

## Shared assembly core — `workflows/assemble.nf` (`ASSEMBLE_CONSENSUS`)

Input per barcode: reads + expected genome size (bp, from the order's `size_kb`).

| Stage | Module | Tool | Notes |
|-------|--------|------|-------|
| Filter | `READ_FILTER` | filtlong | length/quality filter (`--filter_min_len`, `--filter_keep_percent`) |
| Assemble | `AUTOCYCLER_ASSEMBLE` | autocycler + **Flye + raven + miniasm** | multi-assembler consensus — the CLAUDE.md guardrail (never a single assembler for circular plasmids). subsample → assemble → compress/cluster/trim/resolve/combine |
| Reorient | `DNAAPLER_REORIENT` | dnaapler | canonical circular start (guardrail); non-circular passes through |
| Polish | `DORADO_POLISH` | dorado 2.0.0 (GPU) | host binary, `maxForks 1`, `cuda:0` (ADR-0010) |
| QC | `CONSENSUS_QC` | minimap2 + samtools + `amplicon/qc.py` | per-base QC FASTQ + counts + size/depth check |

**Determinism:** the subsample seed + tool versions are logged in the manifest. GPU polishing
is **not** byte-deterministic (like basecalling) — the manifest records what was produced; the
downstream CPU AB1 path stays byte-identical.

## M4 plasmid tier — `workflows/plasmid.nf`

Routes `PLASMID`-assay barcodes through the core. Deliverables in `results/plasmid/<barcode>/`:

```
consensus.fasta            # circular, reoriented, polished consensus
<barcode>.qc.fastq         # per-base QC (consensus-derived quality, NOT Sanger Phred)
<barcode>.qc.json          # length vs expected, mean depth, status
consensus.gfa              # assembly graph (circularity)
counts.tsv                 # per-position pileup counts
{assemble,polish}.stage.json   # provenance fragments
```

## Order intake

A `PLASMID` order (tier 1) needs only `sample_id` + `size_kb` (no primers):

```json
{ "order_id": "9000001", "assay": "PLASMID",
  "samples": [ { "sample_id": "PLZ1", "dna_name": "pXYZ", "size_kb": 3.4 } ] }
```

Exact plasmid-order PDF fields will be finalized when an example arrives. Routing dispatches by
assay: `FAIS|WAIS → amplicon`, `PLASMID → plasmid`.

## Run

```bash
bin/ont_pipeline.sh --pod5_dir <dir> --barcode_kit <KIT> --outdir results \
  --samplesheet samplesheet.csv --orders_dir orders/
```

## Tooling (added at M4, ADR-0010)

`environment.yml`: `flye=2.9.6`, `raven-assembler=1.8.3`, `miniasm=0.3`, `minipolish=0.2.1`,
`any2fasta=0.8.1` (racon transitive via minipolish). `bin/install_dorado.sh` also fetches the
dorado **polish** model. `conf/base.config` adds the `assembly` label (cpus/mem).

> **Box-only validation.** Flye/raven/miniasm/dorado-polish are Linux/GPU — none run on macOS.
> The Mac validates wiring via `-stub-run`; real assembly is verified on the Ubuntu box with
> control plasmid reads (single circular contig, no Flye concatemer; assembled length ≈ size).
