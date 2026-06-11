# CLAUDE.md — ONT Sequencing Service Pipeline

Project constitution for the Oxford Nanopore (MinION / PromethION) data-analysis
pipeline. This file is the source of truth for decisions already made. When in
doubt, follow this file; if something here is wrong or outdated, propose an edit
rather than silently diverging.

## What this project is

A production software pipeline for an oncology-CRO sequencing service that turns
raw ONT signal into customer deliverables across three service tiers:

1. **Plasmid sequencing** — de novo reconstruction + circularization of plasmids,
   delivered as a full circular consensus sequence with per-base QC.
2. **Advanced plasmid sequencing** — tier 1 plus full annotation and insert-region
   localization from customer-provided flanking primers, with insert-vs-reference
   variant calls.
3. **Amplicon insert analysis (whole / focused)** — consensus delivered in
   Sanger-compatible formats: synthetic AB1 (full-length, >800 bp), classic, and
   FASTQ. Plus a "single read from a defined primer + 800 bp strict cutoff" mode
   that deliberately mimics one Sanger read.

## Locked technical decisions

- **OS:** Ubuntu 24.04.x LTS Server. Do NOT build on 26.04 yet — NVIDIA's official
  CUDA repo does not list ubuntu2604 and Canonical recommends waiting for 26.04.1
  (Aug 2026). Revisit migration in Q4 2026.
- **Basecaller:** Dorado, executable pinned to **2.0.0** (ONT CDN tarball, not conda).
  "v6.0" refers to the basecalling MODEL generation, not the software version — but
  the v6.0 *DNA* models ship only in the 2.x executable (the 1.x line ended at 1.4.0
  without them), so 2.x is required to meet the v6.0 goal. Use the v6.0 models;
  default to HAC v6.0 for throughput, reserve SUP for high-value plasmid jobs.
  Rationale and supersession of the original "1.x" decision: ADR-0001 in
  `.claude/memory/decisions.md`.
- **GPU stack:** NVIDIA driver + CUDA 12.8 from NVIDIA's apt repo (Dorado targets
  CUDA 11.8/12.8, Torch 2.9). RTX 4090 = Ada / compute 8.9, FP8 fast path.
- **Input format:** POD5 only. Basecall off local NVMe (heavy random access).
- **Storage:** NVMe = hot scratch (POD5 + basecalling + assembly work dirs);
  separate bulk volume for delivered results + raw archive.
- **Orchestration:** Nextflow (DSL2). `ont_pipeline.sh` is the thin entry layer
  that routes a barcode → service-tier subworkflow via a sample sheet.
- **Reproducibility:** every step containerized (Docker/Singularity), version-pinned
  per job. This is a CRO deliverable — no unpinned tool versions in production.
  Two standing exceptions (see ADR-0005/0006): Dorado runs as a **host binary** (the
  GPU path can't be reserved through a container on the local executor) and is pinned
  via a `dorado --version` gate + `versions.yml` manifest instead of an image digest;
  and non-Dorado steps run from the **pinned conda env on an interim basis** (default
  `-profile conda`), with per-process container images to be filled in at M6.

## Decisions pending empirical benchmark (log outcomes in .claude/memory/decisions.md)

- **Assembler/consensus:** stock ONT `wf-clone-validation` (Nextflow, purpose-built:
  assembly + annotation + primer-based insert localization + QC) vs. an
  Autocycler-based custom pipeline (Autocycler = automated successor to Trycycler).
  Benchmark both on control plasmids; keep whichever gives cleaner consensus.
- **Polisher:** Medaka (`--bacteria` model, as wf-clone-validation uses) vs. Dorado
  polish. Published testing shows Medaka can be neutral-or-harmful on modern SUP
  basecalls — do NOT assume it helps. Validate on controls before defaulting.

## Bespoke component: AB1 synthesizer (no off-the-shelf tool)

ONT has no fluorescence, so AB1 traces are synthesized from per-position base
composition of the read pileup over the consensus (this is the documented
industry approach). Build spec:

1. Align/pile up amplicon reads against the consensus.
2. Per consensus position, compute A/T/G/C proportions across the pileup → the
   four synthetic trace channel intensities.
3. Encode into the ABIF binary container (PBAS / PCON / DATA channels, etc.).
   Biopython READS abi but does NOT write it — this encoder is ours to build.

Delivery modes:
- Full-length consensus AB1 (>800 bp) + FASTQ + FASTA + classic format. Flag to
  customers that quality is consensus-derived, not Sanger Phred.
- "Single primer + 800 bp strict cutoff": orient reads to the named primer, emit
  exactly the downstream window with a hard length/quality cutoff.

## Known pitfalls → required guardrails

- **Flye produces concatemers on circular templates.** Never rely on a single
  assembler for circular plasmids — use consensus-of-multiple (Autocycler/Trycycler).
- **Terminal/inverted repeats (ITR, LTR) break assembly.** Size-filter parameters
  must be per-service-tier, not global; aggressive pre-assembly filtering for
  repeat-containing constructs.
- **Inconsistent circular start positions.** Always reorient final circular contigs
  with dnaapler so every delivery is canonically oriented.
- **Over-polishing.** Gated by the Medaka-vs-Dorado-polish benchmark above.

## Working agreements

- Use **plan mode** before implementing any subworkflow. A plan must name the files
  to edit, the functions to add/modify, and the order of operations.
- If execution diverges from the approved plan, STOP and report — do not improvise.
- Architecture/benchmark decisions go in `.claude/memory/decisions.md` (ADR style)
  BEFORE implementation.
- Never speculate about the contents of files you have not read.
- Delegate codebase exploration and research to subagents to preserve main context.

## Model routing (custom OpenRouter/DeepSeek backend)

- Strongest available model: ABIF binary writer, Nextflow DSL2 channel logic,
  the bioinfo-validator's correctness judgments.
- DeepSeek/cheaper: doc-maintainer, codebase exploration/research subagents.
- Expect to spot-check more when a third-party backend drives a complex step.

## Compaction policy

When compacting, always preserve: the full list of modified files, all test/run
commands, and every entry in or reference to decisions.md.
