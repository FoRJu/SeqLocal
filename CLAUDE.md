# CLAUDE.md — ONT Sequencing Service Pipeline

Project constitution for the Oxford Nanopore (MinION / PromethION) data-analysis
pipeline. This file is the source of truth for decisions already made. When in
doubt, follow this file; if something here is wrong or outdated, propose an edit
rather than silently diverging.

## Current status

- **M0, M1 (+ hardening retrofit), M2 (AB1 synthesizer), and M3 Phase 1 (amplicon tier,
  explicit-primer FAIS/WAIS): complete. M3 Phase 2 (real assembly + circularization, WAIS
  insert-inference; shared with M4) is next.**
- M2 (ADR-0008) is the bespoke ABIF writer in `python/ab1synth/` (Biopython round-trip +
  byte-determinism). M3 Phase 1 (ADR-0009) adds `python/amplicon/` — structured order intake
  (never PDFs), two-tier named-primer registry, IUPAC fuzzy primer matching + FAIS/WAIS region
  extraction with primer-not-found QC — and a `--samplesheet` tier router in `main.nf`. The
  amplicon **consensus is a provisional linear seam**; real assembly/circularization and the
  assembler/polisher benchmark stay open (Phase 2 / M4 / M7).
- The **Production hardening & integrity** section below applies to ALL milestones. The
  M1 retrofit (ADR-0007) is done: M1 emits a schema-validated run manifest with per-stage
  sha256 hashing, and `bin/ont_pipeline.sh` enforces the non-root/`bfxsvc`, kill-flag,
  code-integrity, and MinKNOW-yield chokepoint. The provenance plumbing
  (`python/provenance/`, `assets/run-manifest.schema.json`) is reused by every new stage —
  each MUST emit its manifest block. Pipeline entry is `main.nf` at the repo root.

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
- **GPU stack:** NVIDIA driver + CUDA 12.8 from NVIDIA's apt repo (Dorado 2.0.0
  minimum CUDA is 12.8 on x86; targets CUDA 11.8/12.8, Torch 2.9). RTX 4090 = Ada /
  compute 8.9, FP8 fast path.
- **Input format:** POD5 only. Basecall off local NVMe (heavy random access).
- **Storage:** NVMe = hot scratch (POD5 + basecalling + assembly work dirs);
  separate bulk volume for delivered results + raw archive.
- **Orchestration:** Nextflow (DSL2). `ont_pipeline.sh` is the thin entry layer
  that routes a barcode → service-tier subworkflow via a sample sheet, AND is the
  single chokepoint for the startup integrity + kill-switch check (see hardening).
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
4. **Determinism (hardening):** pileup ordering and any tie-breaks must be
   deterministic; if a seed is used, record it in the run manifest. Same input must
   produce a byte-identical AB1.

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

## Production hardening & integrity

Integrity and reproducible data integrity are the core Bfx goal. Hardening is split
by whether an item changes the SHAPE of the code/data (do it NOW, while there is
little to refactor) or is external infrastructure (DEFER, but reserve its seam now so
it is drop-in later, not a thread-through). Record the now/later rationale as a new
ADR in `.claude/memory/decisions.md`.

### Enforced now — every milestone from M1 onward (build into each stage as written)

- **Run as a non-root service account (`bfxsvc`).** No login, no shell, no sudo. Code
  and containers are owned by a separate deploy identity and are read+execute-only to
  `bfxsvc` — the account that runs the pipeline must not be able to modify it. Never
  develop or test as root.
- **Emit a run manifest from every stage.** Each stage appends a provenance block
  (schema in PLAN.md) before the next stage runs: tool name+version, model
  name+version, input and output sha256, parameters, any RNG seed, instrument/
  flow-cell ID, timestamps, status. Reproducibility is born with the stage.
- **Hash at every stage boundary.** sha256 inputs and outputs; record in the manifest.
- **Determinism.** Any stochastic step records its seed in the manifest. Establish the
  habit now (M2 AB1 pileup ordering; later M4 Rasusa subsampling).
- **Integrity + kill-switch seam in `ont_pipeline.sh`.** Before doing any work the
  entrypoint must (a) verify the recorded code/env hash and (b) check a local
  kill-flag file and refuse to run if present. Stubs are acceptable now; this one
  chokepoint is where image signing and the central kill trigger plug in later.
- **Never preempt instrument control.** The analysis pipeline must yield to MinKNOW.
  Until the systemd resource slices land (integration milestone), gate jobs on
  "no active flow-cell run" rather than running concurrently with live basecalling.

### Deferred — seam reserved now, built at the noted milestone

- **Container image signing (cosign/sigstore) + per-process image digests → M6.**
  Interim: pinned conda env (ADR-0005/0006) + the `dorado --version` / `versions.yml`
  gate. Keep pinning versions meanwhile.
- **Central management plane → M8 (needs multiple sites):** heartbeat, dead-man's-
  switch token, scoped+revocable delivery credentials, config-as-code push. The local
  kill-flag + integrity gate above is the interface it flips.
- **OS tamper-evidence (dm-verity / AIDE / read-only immutable mounts) → M8 /
  deployment hardening, pre-production.**
- **Kill-switch fail-safe semantics:** on trip → halt, quarantine in-flight data,
  refuse to emit/transmit deliverables, revoke delivery creds, alert. NEVER auto-wipe
  data (forensics + chain of custody); NEVER auto-abort a live flow cell (analysis-stop
  and sequencing-stop are separate decisions). Keep the local stub aligned to these
  semantics so M8 only has to wire the triggers.

## Working agreements

- Use **plan mode** before implementing any subworkflow. A plan must name the files
  to edit, the functions to add/modify, and the order of operations.
- If execution diverges from the approved plan, STOP and report — do not improvise.
- Architecture/benchmark decisions go in `.claude/memory/decisions.md` (ADR style)
  BEFORE implementation.
- Never speculate about the contents of files you have not read.
- Delegate codebase exploration and research to subagents to preserve main context.
- **Robustness conventions (every stage):** fail loud on unexpected state (never
  silently continue or paper over a partial result), validate inputs at each stage
  boundary, make stages idempotent and resumable, and keep stochastic steps
  deterministic via logged seeds.

## Model routing (custom OpenRouter/DeepSeek backend)

- Strongest available model: ABIF binary writer, Nextflow DSL2 channel logic,
  the bioinfo-validator's correctness judgments.
- DeepSeek/cheaper: doc-maintainer, codebase exploration/research subagents.
- Expect to spot-check more when a third-party backend drives a complex step.

## Compaction policy

When compacting, always preserve: the full list of modified files, all test/run
commands, every entry in or reference to decisions.md, and the Production hardening
"enforced now" list.
