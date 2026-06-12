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
| [docs/security.md](docs/security.md) | Hardening reference + kill-switch runbook |
| [.claude/memory/decisions.md](.claude/memory/decisions.md) | ADR log — version pins and benchmark outcomes |

## Status

**M0 (environment), M1 (basecall + demux) + hardening retrofit, and M2 (AB1 synthesizer) — complete.**
M1 turns POD5 into per-barcode BAM/FASTQ + QC and emits a schema-validated run manifest
(per-stage sha256 provenance); `bin/ont_pipeline.sh` enforces the non-root / kill-flag /
integrity / MinKNOW-yield chokepoint. M2 is the bespoke ABIF (`.ab1`) writer in
`python/ab1synth/` (Biopython round-trip + byte-deterministic). **M3 (amplicon tier) is
next.** See `docs/PLAN.md`.

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
