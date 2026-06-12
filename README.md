# SeqLocal — ONT Sequencing Service Pipeline

Production data-analysis pipeline for an oncology-CRO Oxford Nanopore
(MinION / PromethION) sequencing service. Turns raw ONT signal into customer
deliverables across three service tiers: plasmid, advanced plasmid, and amplicon
insert analysis.

## Where things are

| Doc | Purpose |
|-----|---------|
| [CLAUDE.md](CLAUDE.md) | Project constitution — locked technical decisions and working agreements |
| [docs/PLAN.md](docs/PLAN.md) | Design rationale, data flows, milestone build order (M0–M8) |
| [docs/SETUP.md](docs/SETUP.md) | M0 environment runbook — pinned toolchain, install + verify |
| [docs/RUNNING.md](docs/RUNNING.md) | How to run the pipeline (M1 basecall + demux), params, outputs |
| [docs/amplicon-orders.md](docs/amplicon-orders.md) | Amplicon tier (M3): FAIS/WAIS order intake, sample sheet, primers |
| [docs/plasmid-tier.md](docs/plasmid-tier.md) | Plasmid tier (M4): shared assembly core, dorado polish, deliverables |
| [docs/security.md](docs/security.md) | Hardening reference + kill-switch runbook |
| [.claude/memory/decisions.md](.claude/memory/decisions.md) | ADR log — version pins and benchmark outcomes |

## Status

**M0, M1 (+ hardening retrofit), M2 (AB1 synthesizer), M3 Phase 1 (amplicon tier), and M4
(assembly core + plasmid tier) — complete.** M1 turns POD5 into per-barcode BAM/FASTQ + QC
with a schema-validated run manifest; `bin/ont_pipeline.sh` enforces the non-root / kill-flag
/ integrity / MinKNOW-yield chokepoint. M2 is the bespoke ABIF (`.ab1`) writer. M3 Phase 1
adds the amplicon tier (FAIS/WAIS order intake → primer matching → AB1). M4 adds the shared
assembly core — filtlong → Autocycler multi-assembler (Flye+raven+miniasm) → dnaapler reorient
→ dorado polish → per-base QC — and the plasmid tier (`docs/plasmid-tier.md`). Routed by
`--samplesheet`. **M3 Phase 2 (swap amplicon consensus to the M4 core) is next.** See
`docs/PLAN.md`.

## Quick start (provisioning)

```bash
# Java for Nextflow — via SDKMAN (Temurin 21 LTS)
curl -s "https://get.sdkman.io" | bash
source ~/.sdkman/bin/sdkman-init.sh
sdk install java 21.0.7-tem

mamba env create -f environment.yml          # main tools (ont-tools)
mamba env create -f environment-medaka.yml   # isolated medaka (ont-medaka)
bash bin/install_dorado.sh                    # Dorado 2.0.0 + v6.0 models
bash bin/install_nextflow.sh                  # Nextflow 26.04.3
```
