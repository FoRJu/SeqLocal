# PLAN.md — Design & Build Spec

Companion to CLAUDE.md. CLAUDE.md holds the rules and locked decisions; this file
holds the design rationale, data flows, and build order. Read this to understand
*what* we're building and *in what order*. **M0 and M1 are built; M2 is next.** This
is the living design/build tracker.

## Build order (milestones)

**Hardening note:** the seams in CLAUDE.md → "Production hardening & integrity →
Enforced now" apply to EVERY milestone from M1 onward (non-root run, manifest
emission, stage-boundary hashing, determinism/seed logging, the entrypoint
integrity + kill-flag check). They are NOT a separate milestone — they are built into
each stage as it is written. Only the external infrastructure is deferred (M6/M8).

- **M0 — Environment. [DONE]** Pinned toolchain: `environment.yml` (mamba/bioconda:
  autocycler, dnaapler, medaka, seqkit, minimap2, samtools, bcftools, rasusa,
  filtlong), Dorado 2.0.0 host-binary install (ONT tarball, not conda), Nextflow.
  Exact versions recorded.
- **M1 — Basecall + demux. [DONE]** Dorado 2.0.0 (HAC v6.0 default) POD5 → FASTQ/BAM,
  demux by barcode. GPU path on the RTX 4090 verified. Clean per-barcode read set.
  - **M1 retrofit [DONE — ADR-0007]:** the hardening seams were specified after M1 was
    built, so M1 was brought up to standard before the project accreted more
    un-provenanced stages. Checklist (all complete):
    1. ✅ Entrypoint enforces non-root and (with `SEQLOCAL_REQUIRE_BFXSVC=1`) `bfxsvc`.
    2. ✅ Each stage emits a manifest block: dorado version, model name
       (`dna_r10.4.1_e8.2_400bps_hac@v6.0.0`), input POD5 sha256(s), demux params,
       flow-cell/instrument ID (run-metadata flags), timestamps, status.
    3. ✅ sha256 of inputs and outputs recorded per stage; finalized by `MANIFEST_MERGE`.
    4. ✅ Integrity + kill-flag (+ MinKNOW yield) chokepoint in `ont_pipeline.sh`.
    Provenance plumbing lives in `python/provenance/` and is reused by M2 onward.
- **M2 — AB1 synthesizer (bespoke). [DONE — ADR-0008]** The one component with no
  off-the-shelf equivalent, built and unit-tested **in isolation** against a known
  consensus (`python/ab1synth/`: stdlib ABIF writer + trace synth + CLI). Input contract is
  consensus + per-position A/C/G/T pileup counts; delivery modes (full / `--window` /
  `--max-len` / `--min-qual`) are parameters — the primer detection that computes WAIS/FAIS
  windows is M3. Validated by **Biopython round-trip** + byte-determinism. Hardening seams
  carried: deterministic (byte-identical AB1; no wall-clock tags); inputs validated at the
  boundary; loud failure (never a silent empty AB1); emits a provenance stage fragment
  (ab1synth version, consensus sha256, AB1 sha256, params, seed=null) via
  `python/provenance/`. "classic" format deferred here → M3.
- **M3 — Amplicon tier.** Primer-anchored orientation → consensus → AB1 + FASTQ +
  FASTA + classic, plus the "single primer + 800 bp strict cutoff" mode.
  - **Phase 1 [DONE — ADR-0009]:** explicit-primer cases (FAIS single primer + 800 bp; WAIS
    F&R between-primer). Structured intake (`samplesheet.csv` + per-order JSON + two-tier
    primer registry — never the PDFs); `python/amplicon/` fuzzy IUPAC primer matching +
    region extraction with primer-not-found QC; provisional reference-free **linear**
    consensus + pileup counts → `python/ab1synth` AB1/FASTA/FASTQ; `main.nf` tier router on
    `--samplesheet`. Order→record mapping in `docs/amplicon-orders.md`.
  - **Phase 2 [NEXT]:** real assembly + circularization in `AMPLICON_CONSENSUS` (shared with
    M4; assembler/polisher benchmark = M7), and **WAIS insert-inference** (no primers,
    7340073: identify insert vs backbone). Plus per-sample manifest assembly + "classic".
- **M4 — Plasmid tier.** Assembly (benchmark wf-clone-validation vs Autocycler) →
  dnaapler reorient → polish (benchmark Medaka vs Dorado polish) → circular consensus
  + per-base QC. (Rasusa subsample seed MUST be pinned + logged — see Determinism.)
- **M5 — Advanced plasmid tier.** M4 + annotation + primer-based insert localization
  + insert-vs-reference variant calls.
- **M6 — Delivery packaging + signing.** Per-tier output bundles, naming,
  customer-facing QC report, failure policy. Deliverables checksum-verified against
  the manifest at packaging. Per-process container images built + signed (cosign).
- **M7 — Validation.** Run control plasmids/amplicons end-to-end; lock the two pending
  benchmarks (assembler, polisher) and record results in `.claude/memory/decisions.md`.
- **M8 — Fleet hardening & central plane. [DEFERRED — needs multiple sites]** Central
  management plane, heartbeat / dead-man's-switch token, scoped+revocable delivery
  credentials, config-as-code push (Ansible/Salt), OS tamper-evidence rollout
  (dm-verity / AIDE / read-only mounts), and the central kill-switch trigger. The
  local kill-flag + integrity gate stubbed from M1 is the interface this milestone
  flips. Build nothing here until the single-site app is validated (M7).

## Target directory structure

```
SeqLocal/
├── CLAUDE.md
├── environment.yml
├── docs/
│   ├── PLAN.md                 # this file
│   ├── abif-format-notes.md    # ABIF byte-layout reference (write during M2)
│   └── security.md             # hardening reference + kill-switch runbook (grows M6/M8)
├── bin/
│   └── ont_pipeline.sh         # thin entry + integrity/kill-flag chokepoint
├── main.nf                     # pipeline entry (repo root → projectDir = repo root)
├── workflows/                  # tier subworkflows (M3+)
│   ├── amplicon.nf
│   ├── plasmid.nf
│   └── plasmid_advanced.nf
├── modules/                    # Nextflow DSL2 process modules
├── python/
│   ├── ab1synth/               # the AB1 synthesizer package (pip-installable)
│   └── provenance/             # run-manifest emitter (used by every stage)
├── conf/                       # nextflow.config, container profiles
├── assets/
│   ├── samplesheet.schema.json
│   └── run-manifest.schema.json
├── tests/
└── .claude/
    ├── agents/                 # subagent defs (research, implementer, validator, docs)
    └── memory/
        ├── decisions.md        # ADR log — benchmark outcomes + hardening rationale
        └── scratchpad.md
```

Note: the kill-flag and recorded code/env hash live OUTSIDE the repo at a runtime path
(e.g. `/var/lib/seqlocal/`), owned by the deploy identity, not writable by `bfxsvc`.

## Per-tier data flow

**Amplicon (M3):** demuxed reads → orient to defined primer → (full mode) consensus
over the amplicon via pileup; (Sanger mode) emit primer-anchored 800 bp window with
hard length/quality cutoff → AB1 synth + FASTQ + FASTA + classic.

**Plasmid (M4):** demuxed reads → SeqKit/Filtlong size+quality filter (params per tier,
aggressive for repeat-containing constructs) → Rasusa subsample → multi-assembly
consensus (NOT a single assembler — Flye concatemers) → dnaapler reorient → polish →
circular consensus FASTA + per-base QC FASTQ.

**Advanced plasmid (M5):** plasmid flow + annotation (pLannotate/Bakta) + insert
localization from customer primers + BCFtools insert-vs-reference variants → annotated
GenBank / SnapGene .dna + insert report.

## AB1 algorithm (M2 detail)

ONT has no fluorescence; synthesize the trace from read composition:

1. Align/pile up the contributing reads against the consensus.
2. For each consensus position, count A/T/G/C across the pileup and normalize to
   proportions → these become the four ABIF DATA channel intensities at that position.
3. Base call = consensus base; per-base confidence (PCON) from consensus quality.
4. Write the ABIF binary container: directory entries for PBAS (bases), PCON (quals),
   DATA1–4 (channel traces), plus required header/metadata fields.

Constraints: Biopython reads ABIF but does NOT write it — this encoder is ours.
Build a byte-layout reference in `docs/abif-format-notes.md` as you go. Unit-test by
round-tripping (write → read back with Biopython/seqret → compare bases) AND by the
determinism check (same input → byte-identical output).

## Run-manifest schema (the concrete center of the reproducibility goal)

One JSON manifest per run/sample, written INCREMENTALLY — each stage appends its block
before the next stage runs (append, never rewrite history). Lives with the run's
outputs; shipped to the central append-only store at M8. Emitter lives in
`python/provenance/`; JSON Schema in `assets/run-manifest.schema.json`. Shape:

```json
{
  "manifest_version": "1",
  "run_id": "",
  "sample_id": "<barcode/alias>",
  "service_tier": "amplicon | plasmid | plasmid_advanced",
  "site_id": "",
  "instrument": { "device": "MinION|PromethION", "flow_cell_id": "...", "run_uuid": "..." },
  "operator": "<account/id>",
  "pipeline": {
    "git_commit": "...",
    "code_sha256": "...",
    "container_digest": null
  },
  "integrity": { "code_hash_verified": true, "kill_flag_present": false },
  "created_utc": "",
  "stages": [
    {
      "name": "basecall",
      "tool": "dorado",
      "tool_version": "2.0.0",
      "model": "dna_r10.4.1_e8.2_400bps_hac@v6.0.0",
      "params": {},
      "seed": null,
      "inputs":  [ { "path": "...", "sha256": "..." } ],
      "outputs": [ { "path": "...", "sha256": "..." } ],
      "started_utc": "...",
      "finished_utc": "...",
      "status": "ok | failed"
    }
  ],
  "deliverables": [
    { "path": "...", "sha256": "...", "format": "ab1 | fastq | fasta | genbank | ..." }
  ]
}
```

Rules: every stage MUST append its block before the next runs; a stage with
`status: failed` halts the run; `container_digest` is null while on the conda interim
(ADR-0005/0006) and populated from M6; deliverables are checksum-verified against this
manifest at packaging (M6).

## Kill-switch & MinKNOW co-location design

**Kill-switch (fail-safe).** `ont_pipeline.sh` checks, before any work: the recorded
code/env hash, and a local kill-flag file (e.g. `/var/lib/seqlocal/KILL`, configurable).
On trip → halt, quarantine in-flight data, refuse to emit/transmit deliverables, revoke
delivery creds (once the central plane exists), alert. NEVER wipe data; NEVER auto-abort
a live flow cell. Central revocation + dead-man's-switch token arrive at M8; the local
flag is their interface. The switch is only as good as its runbook — define the alert
path and owner in `docs/security.md`.

**MinKNOW co-location.** The analysis pipeline must never preempt instrument control
(live basecalling already struggles to keep up with the flow cell on a single 4090).
Until systemd resource slices land (integration), gate jobs on "no active flow-cell run"
instead of running concurrently. Final state: MinKNOW services in a high-priority
systemd slice; the pipeline in a constrained slice (CPU weight, MemoryMax, GPU
arbitration so it yields while a flow cell is live).

## Notes carried over from planning (so they don't get lost)

- Dorado executable pinned to **2.0.0** — the 2.x line is the first to ship the v6.0
  DNA models; 1.x ended at 1.4.0 without them. "v6.0" = the model generation. See
  CLAUDE.md and ADR-0001. (Supersedes the earlier "executable is 1.x" note.)
- Ubuntu 24.04 LTS now; 26.04 is blocked on NVIDIA CUDA repo support — revisit Q4 2026.
- HAC v6.0 is the throughput default; SUP only for high-value plasmid jobs.
- Two benchmarks are deliberately unresolved until M7: assembler and polisher choice.
- Hardening is split now/later — see CLAUDE.md → "Production hardening & integrity."
