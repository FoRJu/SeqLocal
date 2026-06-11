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

---

## Open — pending empirical benchmark (resolve in M7, record outcomes here)

- **Assembler/consensus:** stock ONT `wf-clone-validation` vs. Autocycler-based custom
  pipeline. Benchmark on control plasmids; keep the cleaner consensus.
- **Polisher:** Medaka (`--bacteria` model) vs. Dorado polish. Medaka may be
  neutral-or-harmful on modern SUP basecalls — validate on controls before defaulting.
