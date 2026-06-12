# Decision log (ADR style)

Architecture and benchmark decisions for the ONT sequencing-service pipeline.
Newest entries at the bottom. Benchmark outcomes (M7) land here too.

Status values: Accepted · Superseded · Open (pending benchmark).

---

## ADR-0001 — Dorado executable pinned to 2.0.0 (supersedes CLAUDE.md "1.x")

- **Date:** 2026-06-10
- **Status:** Accepted (supersedes the locked "Dorado 1.x" decision in CLAUDE.md)
- **Context:** CLAUDE.md locked the basecaller at "Dorado 1.x series" while also
  requiring the **v6.0** basecalling models ("Use the v6.0 models. Default HAC v6.0").
  Research (June 2026) showed these are incompatible: the Dorado 1.x line ended at
  **v1.4.0** (2026-02-19), whose release notes cover only RNA v5.3.0 models. The
  **DNA HAC/SUP v6.0** models ship in the **2.x** executable; latest is **v2.0.0**
  (2026-05-20, GitHub `prerelease: false`). The v6.0 goal therefore requires a 2.x
  executable.
- **Decision:** Pin the Dorado executable at **2.0.0**, installed from the ONT CDN
  tarball (not bioconda). v6.0 DNA models are downloaded via `dorado download`.
  CLAUDE.md's "Locked technical decisions → Basecaller" line is updated to match.
- **Consequences:** The "'v6.0' = model generation, not software version" note in
  CLAUDE.md remains true, but the implication that a 1.x executable suffices does not.
  CUDA targets (11.8/12.8) and the RTX 4090 / Ada fast path are unchanged.
- **Tarball:** `https://cdn.oxfordnanoportal.com/software/analysis/dorado-2.0.0-linux-x64.tar.gz`

## ADR-0002 — Toolchain version pins (M0)

- **Date:** 2026-06-10
- **Status:** Accepted
- **Context:** CRO deliverable — no unpinned tool versions in production. Versions
  verified against GitHub `releases/latest` and the bioconda anaconda.org API
  (June 2026).
- **Decision:** Pin exactly:

  | Tool | Version | Source |
  |------|---------|--------|
  | Dorado (exe) | 2.0.0 | ONT CDN tarball |
  | Dorado DNA models | v6.0 (HAC default, SUP for plasmid) | `dorado download` |
  | Nextflow | 26.04.3 (stable) | standalone installer (`NXF_VER`) |
  | autocycler | 0.6.2 | bioconda |
  | dnaapler | 1.3.0 | bioconda |
  | seqkit | 2.13.0 | bioconda |
  | minimap2 | 2.31 | bioconda |
  | samtools | 1.23.1 | bioconda |
  | bcftools | 1.23.1 | bioconda |
  | rasusa | 4.1.0 | bioconda |
  | filtlong | 0.3.1 | bioconda |
  | medaka | 2.2.2 | bioconda (isolated env — see ADR-0003) |

- **Consequences:** `environment.yml` uses exact `=x.y.z`. A `conda-lock` lockfile is
  the true reproducibility artifact and should be generated/committed per host arch.
  samtools and bcftools both bundle HTSlib 1.23.1 — keep them lockstep on bumps.

## ADR-0003 — Medaka in an isolated conda env

- **Date:** 2026-06-10
- **Status:** Accepted
- **Context:** Medaka 2.x is PyTorch-based and the bioconda package **bundles** its
  own samtools/minimap2/bgzip helpers, which can collide with our explicitly pinned
  samtools 1.23.1 / minimap2 2.31 in a shared env (solver may pull a second copy).
  ONT also states the bioconda medaka packages are **not supported** by Oxford
  Nanopore (they recommend pip/Docker).
- **Decision:** Ship Medaka in its own env file (`environment-medaka.yml`, env name
  `ont-medaka`, `medaka=2.2.2` only), separate from the main `ont-tools` env. The M7
  Medaka-vs-Dorado-polish benchmark runs from this isolated env.
- **Consequences:** Two envs to manage; clean, non-colliding pins in the main env.

## ADR-0004 — Conda channel ordering

- **Date:** 2026-06-10
- **Status:** Accepted
- **Decision:** Channels `conda-forge` > `bioconda`, **strict** channel priority, and
  **no `defaults`** channel (current bioconda guidance). Getting this wrong is the
  usual cause of unsolvable/incorrect samtools/bcftools/htslib pins.

## ADR-0005 — Dorado run pattern in Nextflow (M1)

- **Date:** 2026-06-10
- **Status:** Accepted
- **Context:** M1 basecalls POD5 → demuxes by barcode on the Ubuntu RTX 4090 box.
  Researched Dorado 2.0.0 behavior: the Nextflow `accelerator` directive does **not**
  reserve a GPU on the local executor; the default model download is ephemeral
  (deleted post-run); inline `--kit-name` during basecalling hits a nested-output bug
  (dorado#1544); Dorado emits unaligned BAM to stdout by default.
- **Decision:**
  - **Basecall kit-free, then demux classifies.** `dorado basecaller hac@v6.0 <pod5>
    --device cuda:0 --models-directory tools/dorado-models > calls.bam`, then
    `dorado demux --kit-name <KIT> --emit-summary --output-dir demux calls.bam`.
  - Run the **host Dorado binary** from the Nextflow process (no container — GPU
    exception), label `gpu`, `maxForks 1`, `-x cuda:0` to serialize the single 4090.
  - Pre-fetched models in `tools/dorado-models` (never the ephemeral default).
  - **Version gate:** `bin/ont_pipeline.sh` asserts `dorado --version == 2.0.0`; each
    process emits `versions.yml` (dorado + model) collated to `pipeline_info/`.
  - Keep default trimming (strips ONT adapters/barcodes, not customer primers); expose
    `--no_trim` for later per-tier needs.
- **Consequences:** GPU step isn't pinned by an image digest — the version gate +
  versions.yml manifest are the reproducibility substitute. Kit-name strings validated
  against `dorado demux --help` at runtime (compiled-in enumerated list), not hardcoded.

## ADR-0006 — Interim conda exec backend; containers scaffolded (M1)

- **Date:** 2026-06-10
- **Status:** Accepted (interim; revisit at M6)
- **Context:** CLAUDE.md locks "every step containerized." M0 produced a version-pinned
  conda env (`ont-tools`); M1's only non-Dorado step (samtools-based demux QC / BAM→FASTQ)
  can run from it immediately, whereas authoring per-process container images now would
  block M1 from running end-to-end on the box.
- **Decision:** Default `-profile conda` (uses `ont-tools` via `environment.yml`) for
  non-Dorado steps. Scaffold `docker` and `singularity` profiles in `nextflow.config`
  with per-process `container` directives left as TODO-M6. Conda pins (+ `conda-lock`)
  provide interim reproducibility.
- **Consequences:** A documented, temporary divergence from the containerization lock,
  with the migration path (M6) in place. CLAUDE.md's Reproducibility bullet is annotated
  to reflect this rather than silently diverging.

## ADR-0007 — Run-manifest architecture & M1 hardening retrofit

- **Date:** 2026-06-11
- **Status:** Accepted
- **Context:** The "Production hardening & integrity → Enforced now" requirements were
  added to CLAUDE.md/PLAN.md after M1 was built, and apply retroactively. PLAN.md gates
  M2 on it: *"Do not start M2 proper until M1 emits a manifest."* Needed: a run manifest
  per stage, sha256 at every stage boundary, non-root (`bfxsvc`) execution, and the
  integrity + kill-flag chokepoint — built so M2 and later stages inherit the same
  provenance plumbing. CLAUDE.md instructs recording the now/later split as an ADR.
- **Decision:**
  - **Division of labor.** `bin/ont_pipeline.sh` is the integrity chokepoint: it computes
    the run-level header facts (non-root/`bfxsvc` check, repo code hash, kill-flag,
    MinKNOW yield, operator, git commit) and passes them to Nextflow as params. Each
    Nextflow **process emits a stage fragment** (`<name>.stage.json`) that sha256-hashes
    its real inputs/outputs *in its own work dir* — hashing happens at the boundary, not
    after. A new **`MANIFEST_MERGE`** process assembles header + ordered fragments +
    deliverables into a schema-validated `pipeline_info/run-manifest.json`. The
    basecall→demux DAG dependency enforces stage order; shell-glob ordering of fragments
    is the tie-break.
  - **Emitter is stdlib-only + Python 3.9-compatible** (`python/provenance/manifest.py`),
    so it runs identically under the GPU label (no conda — system python3) and the
    samtools label (ont-tools python), and the Mac `-stub-run` still validates wiring.
    **No new conda dependency** (keeps ADR-0002 pins intact); schema validation is a
    hand-rolled required-keys/enum check mirroring `assets/run-manifest.schema.json`.
    JSON is written sorted + fixed-separators → byte-deterministic for identical inputs.
  - **`main.nf` moved to the repo root** (was `workflows/main.nf`). `projectDir` resolves
    to the *main script's* directory, so the old layout made every `${projectDir}/…`
    tooling path (dorado_bin, models, conda env, provenance_cli) resolve into
    `workflows/` — latent because no `${projectDir}` path was exercised at stub-runtime
    until the manifest CLI. Root `main.nf` makes `projectDir` = repo root (nf-core idiom).
    `workflows/` is retained for the M3+ tier subworkflows.
  - **now/later split.** Built now (changes code/data shape): manifest emission, stage
    hashing, non-root enforcement, kill-flag + integrity + MinKNOW stubs in the entrypoint.
    Deferred (external infra, seam reserved): real code-hash baseline recording + image
    signing → M6 (`container_digest` stays null meanwhile); central kill trigger, scoped
    delivery creds, append-only manifest store, systemd GPU slices → M8.
- **Consequences:** M1 now emits a reproducible, schema-valid manifest and refuses to run
  as root / under a kill-flag / against a live flow cell. The entrypoint hash covers
  git-tracked files only (committed state) — correct for the deploy model (commit →
  record baseline → run), but uncommitted edits are not reflected until tracked. M2
  reuses `python/provenance/` directly.

## ADR-0008 — AB1 synthesizer design (M2)

- **Date:** 2026-06-11
- **Status:** Accepted
- **Context:** ONT has no fluorescence, so a Sanger `.ab1` chromatogram must be synthesized
  from the read pileup's per-position base composition over a consensus. Biopython reads
  ABIF but cannot write it — the encoder is bespoke. Per the scope decision, M2 builds the
  ABIF encoder **in isolation** (deterministic, unit-tested against a known consensus);
  primer detection (WAIS start+end, FAIS start +800 bp) is M3.
- **Decision:**
  - **Input contract = consensus + per-position A/C/G/T pileup counts (TSV).** The read →
    counts step (alignment + mpileup) is M3; decoupling here keeps M2 free of
    minimap2/pysam and trivially testable with synthetic counts. Consensus is FASTA
    (quality derived from pileup support of the called base) or FASTQ (use its Phred).
  - **Delivery modes are parameters, not primers:** full consensus; `--window START:END`
    (WAIS between-primer); `--max-len N` + `--min-qual Q` hard cutoffs (FAIS 800 bp single
    read). M3 supplies the coordinates.
  - **Emitted ABIF tags:** `PBAS1/2`, `PCON1/2`, `FWO_` (`"ACGT"`), `PLOC1/2`,
    `DATA1-4` (raw) + `DATA9-12` (analyzed), `SMPL1`. `PBAS2`/`PCON2` are what Biopython
    reads as seq/quality; the DATA/FWO_/PLOC set makes it a real chromatogram. Byte layout
    in `docs/abif-format-notes.md`.
  - **Determinism:** directory entries sorted by (name, number); **no wall-clock
    RUND/RUNT tags**; integer trace → byte-identical `.ab1` for identical input. Quality is
    **consensus-derived, not Sanger Phred** (flagged), capped < 128 (60 derived / 93
    supplied) so `PCON` bytes survive Biopython's utf-8 decode.
  - **Validation (canonical):** round-trip through **Biopython** (the authoritative ABIF
    reader). Added **`biopython=1.87`** (conda-forge — bioconda's listing is stale at 1.70)
    to `environment.yml`; M3 needs it too. Package ships a minimal stdlib reader for
    structural self-tests so they run without the dependency.
  - Provenance: the `ab1synth` CLI reuses `python/provenance/manifest.py` to emit a stage
    fragment (ab1synth version, consensus sha256, AB1 sha256, params, seed=null) — the
    PLAN.md M2 hardening seam; M3 wires it into the Nextflow run manifest.
  - **"classic" delivery format deferred to M3** (per user). M2 emits AB1 + FASTA + FASTQ.
- **Consequences:** A pure-stdlib, deterministic ABIF writer validated against Biopython,
  reusable by the amplicon tier. The trace is synthetic (fixed Gaussian peaks, flat
  baseline) — faithful enough for Sanger viewers, not a literal instrument trace.

## ADR-0009 — Amplicon tier intake + provisional-consensus seam (M3 Phase 1)

- **Date:** 2026-06-11
- **Status:** Accepted (Phase 1; provisional consensus revisited at M3 Phase 2 / M4)
- **Context:** Real VirtuizeBio orders (FAIS 7340110/7340113; WAIS 7340118/7340073) define
  the amplicon tier. Clarified with the lab: primers are **named** (two-tier resolve: repo
  `assets/primers.csv` + customer primers); inputs are **structured** (`samplesheet.csv`
  `barcode,sample_id,order_id` + per-order JSON), **never the PDFs**; and the consensus is
  meant to be real **assembly + circularization** capturing SNP/indel for the AB1 — a heavy
  core that overlaps M4 and the M7 assembler/polisher benchmark.
- **Decision:**
  - **Build the bespoke, order-specific logic now, at the consensus boundary** (same
    isolation that made M2 work): `python/amplicon/` — IUPAC-aware fuzzy primer matching on
    both strands (`match.py`), FAIS 800 bp / WAIS between-primer region extraction with
    RC-aware orientation (`region.py`), two-tier primer registry (`registry.py`), and
    sample-sheet/order load+validate+join (`orders.py`). Deterministic; unit-tested with
    synthetic consensus. Orientation is decided by the matched strand, not the name suffix.
  - **No PDF parsing.** Structured records only; schemas in `assets/{samplesheet,order}.schema.json`;
    mapping documented in `docs/amplicon-orders.md`.
  - **Primer-not-found is a recognized QC outcome**, not a crash: write `<barcode>.qc.json`
    with `status=primer_not_found` ("possible wrong primer selected") and emit **no AB1**.
    Real intake errors (unknown order, bad sheet) fail loud.
  - **Consensus is a provisional, modular seam**: Phase 1 uses a reference-free **linear**
    consensus (longest-read draft → minimap2 realign → `samtools consensus`) + pileup counts
    (minimap2 → `samtools mpileup` → `python/amplicon/pileup.py`). **No de novo assembler
    added, no circularization yet.** The real assembler (Flye/Autocycler/wf-clone-validation)
    drops into `AMPLICON_CONSENSUS` at Phase 2/M4; the **assembler/polisher benchmark stays
    open → M7**. Interface fixed: reads → (consensus.fasta, counts.tsv).
  - **Routing:** `main.nf` gains a tier router keyed on `--samplesheet`; barcodes absent from
    the sheet are dropped. The amplicon subworkflow emits per-sample AB1/FASTA/FASTQ + QC +
    a valid provenance stage fragment. The run-level manifest (M1) is unchanged; per-sample
    manifest assembly (`service_tier` is genuinely per-sample, not run-level) is a follow-up.
- **Deferred (named):** WAIS insert-inference, no primers (7340073) → Phase 2; real
  assembly + circularization → Phase 2/M4; "classic" format, annotation/variants → later/M5.
- **Consequences:** the genuinely new, customer-facing logic is testable now (46 unit tests;
  byte-deterministic AB1; stub-run end-to-end through both assays). The provisional consensus
  is honestly linear/uncircularized — adequate to validate the region/primer logic, replaced
  before production by the M4 assembler.

## ADR-0010 — Assembly/consensus core + plasmid tier (M4)

- **Date:** 2026-06-11
- **Status:** Accepted (provisional engine choices revisited at the M7 benchmark)
- **Context:** The amplicon tier (M3 Phase 1) used a provisional linear consensus. The lab
  confirmed samples are plasmids / long amplicons that must be **assembled + circularized**
  (SNP/indel captured for the AB1). M4 builds the real shared assembly core + the tier-1
  plasmid deliverable. This intersects the M7 benchmarks, so engine choices are provisional.
- **Decision (confirmed with the user this session):**
  - **Assembler = Autocycler multi-assembler.** subsample → **Flye + raven + miniasm
    (+minipolish)** → `autocycler compress/cluster/trim/resolve/combine` → one consensus.
    This honors the CLAUDE.md guardrail "never a single assembler for circular plasmids
    (Flye concatemers)". It is the **custom side of the M7 benchmark**, built now;
    wf-clone-validation remains the M7 comparator (not built).
  - **Polisher = `dorado polish`** (2.0.0 host binary, GPU; ADR-0010): ONT's high-accuracy
    assembly polisher, no env change, sidesteps the bioconda-medaka issues (ADR-0003). The
    Medaka-vs-dorado-polish benchmark stays open → M7. `bin/install_dorado.sh` fetches the
    polish model alongside the v6.0 basecall models.
  - **Reorient with dnaapler** (guardrail: consistent circular start); non-circular passes through.
  - **Env additions (pinned, ADR-0002 lockstep):** `flye=2.9.6`, `raven-assembler=1.8.3`,
    `miniasm=0.3`, `minipolish=0.2.1`, `any2fasta=0.8.1` (racon transitive via minipolish,
    captured by conda-lock). `autocycler=0.6.2` already pinned.
  - **Subsampling:** `autocycler subsample` (designed for multi-assembly independence)
    supersedes the generic Rasusa step on the Autocycler path; Rasusa stays available/seeded
    for other tiers. The subsample seed + tool versions are logged in the manifest.
  - **Routing:** `main.nf` dispatches by order **assay** (`FAIS|WAIS → amplicon`,
    `PLASMID → plasmid`) via a light Groovy parse of the sample sheet + order JSONs; the
    authoritative order validation stays in `python/amplicon`. Added `PLASMID` to the order
    assay enum (no primers; needs only `sample_id` + `size_kb`).
  - **Scope:** shared core + M4 plasmid only. **Deferred:** M3 Phase 2 (swap amplicon
    consensus to this core + circular-aware primer matching), WAIS insert-inference,
    advanced-plasmid annotation/variants (M5).
- **Consequences:** the deterministic Python (per-base QC `amplicon/qc.py`, PLASMID join) is
  unit-tested on the Mac (51 tests); the assembly/GPU stages are **box-only** (Flye/raven/
  miniasm/dorado-polish are Linux/GPU) and validated via `-stub-run` for wiring on the Mac.
  GPU polish is not byte-deterministic — provenance records output, per the basecall caveat.
  Per-sample manifest assembly (run-manifest is run-level) remains a deferred follow-up.

## ADR-0011 — Real intake formats (sample sheet TSV + order-detail CSV)

- **Date:** 2026-06-12
- **Status:** Accepted (supersedes the M3 Phase 1 placeholder intake)
- **Context:** M3 Phase 1 assumed a `barcode,sample_id,order_id` CSV + per-order JSON. The
  real VirtuizeBio LIMS exports (run `aa051826a.csv`, `Order_7340017.csv`,
  `Order_7340018.csv`) are different shapes, and tier routing depends on parsing them right.
- **Decision:**
  - **Sample sheet = TSV** (tab-delimited despite `.csv`): metadata preamble, a header row
    beginning `Well`, then 96 rows (most empty). Process only rows with `Sample Name` +
    `Order`; `Order = Customer#orderid#`. **`Sample Name` == the order's `DNA Name`** (the
    join key — not the order's Sample ID).
  - **Order detail = multi-section CSV** per order (`Order_<id>.csv`): `Order No`,
    `Service Type`, and a `Samples (N)` table keyed by `DNA Name`. **`Service Type → assay`**:
    `Whole Plasmid Sequencing→PLASMID`, `WAIS→WAIS`, `FAIS→FAIS`. Sample columns detected by
    name per assay (PLASMID: `Plasmid Size (Kb)`; WAIS: `F/R Primer`,`Insert Size`; FAIS:
    `Primers`). WAIS/FAIS column names are **inferred from the PDFs** until a real WAIS/FAIS
    order CSV arrives (both examples were Whole Plasmid).
  - `python/amplicon/orders.py` is the authoritative parser (stdlib `csv`); `main.nf` does a
    light routing-only parse (range-based, not C-style for — the strict Nextflow parser
    rejects C-style loops and `import`). Orders dir holds `Order_*.csv`; PRIMER_REGION globs
    `*.csv` (was `*.json`).
  - **Genome size:** Whole-plasmid orders rarely declare size (`-`). `AUTOCYCLER_ASSEMBLE`
    estimates it from the reads (`seqkit stats -a` N50) when undeclared, default fallback;
    the value + source are logged in the manifest.
  - Retired the obsolete `assets/{samplesheet,order}.schema.json` (described the old JSON);
    format reference is now `docs/amplicon-orders.md`.
- **Consequences:** real run sheets parse correctly (verified: `aa051826a` → 9 jobs across two
  Whole-Plasmid orders). The pending M4 box plasmid run uses 7340017/7340018 (both PLASMID).
  A real WAIS/FAIS order CSV is still needed to confirm those Sample-column names.

---

## Open — pending empirical benchmark (resolve in M7, record outcomes here)

- **Assembler/consensus:** stock ONT `wf-clone-validation` vs. Autocycler-based custom
  pipeline. Benchmark on control plasmids; keep the cleaner consensus.
- **Polisher:** Medaka (`--bacteria` model) vs. Dorado polish. Medaka may be
  neutral-or-harmful on modern SUP basecalls — validate on controls before defaulting.
