# SeqLocal — ONT Sequencing Service Pipeline

Production data-analysis pipeline for an oncology-CRO Oxford Nanopore
(MinION / PromethION) sequencing service. Turns raw ONT signal into customer
deliverables across three service tiers: plasmid, advanced plasmid, and amplicon
insert analysis.

## Where things are

| Doc | Purpose |
|-----|---------|
| [CLAUDE.md](CLAUDE.md) | Project constitution — locked technical decisions and working agreements |
| [docs/PLAN.md](docs/PLAN.md) | Design rationale, data flows, milestone build order (M0–M7) |
| [docs/SETUP.md](docs/SETUP.md) | M0 environment runbook — pinned toolchain, install + verify |
| [.claude/memory/decisions.md](.claude/memory/decisions.md) | ADR log — version pins and benchmark outcomes |

## Status

**M0 (environment) — toolchain pinned.** See `docs/SETUP.md` to provision the
Ubuntu 24.04 GPU host. Pipeline code (basecalling, AB1 synth, tier subworkflows)
begins at M1; see `docs/PLAN.md`.

## Quick start (provisioning)

```bash
mamba env create -f environment.yml          # main tools (ont-tools)
mamba env create -f environment-medaka.yml   # isolated medaka (ont-medaka)
bash bin/install_dorado.sh                    # Dorado 2.0.0 + v6.0 models
bash bin/install_nextflow.sh                  # Nextflow 26.04.3
```
