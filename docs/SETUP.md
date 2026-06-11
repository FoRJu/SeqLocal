# SETUP.md — M0 environment runbook

How to stand up the pinned toolchain on the sequencing host. This is the executable
companion to milestone **M0** in [PLAN.md](PLAN.md). All version decisions are
recorded as ADRs in [`.claude/memory/decisions.md`](../.claude/memory/decisions.md).

> These steps run on the **Ubuntu 24.04 LTS GPU host** (NVIDIA + CUDA). The repo
> can be scaffolded anywhere, but env-create and the binary installs target Linux.

## 1. Prerequisites

| Requirement | Pin / note |
|-------------|------------|
| OS | Ubuntu 24.04.x LTS Server (NOT 26.04 yet — see CLAUDE.md) |
| GPU stack | NVIDIA driver + CUDA 12.8 (NVIDIA apt repo); RTX 4090 / Ada 8.9 |
| Conda frontend | `mamba` (or `conda`) with strict channel priority |
| Java | Temurin JDK **17** LTS (21 also supported) — for Nextflow |
| Storage | NVMe hot scratch for POD5 + basecalling + work dirs |

Set strict channel priority once:

```bash
conda config --set channel_priority strict
```

## 2. Pinned versions

| Tool | Version | Install |
|------|---------|---------|
| Dorado (executable) | **2.0.0** | `bin/install_dorado.sh` (ONT CDN tarball) |
| Dorado DNA models | **v6.0** (HAC default, SUP for plasmid) | `dorado download` |
| Nextflow | **26.04.3** (stable) | `bin/install_nextflow.sh` |
| autocycler | **0.6.2** | `environment.yml` |
| dnaapler | **1.3.0** | `environment.yml` |
| seqkit | **2.13.0** | `environment.yml` |
| minimap2 | **2.31** | `environment.yml` |
| samtools | **1.23.1** | `environment.yml` |
| bcftools | **1.23.1** | `environment.yml` |
| rasusa | **4.1.0** | `environment.yml` |
| filtlong | **0.3.1** | `environment.yml` |
| medaka | **2.2.2** | `environment-medaka.yml` (isolated) |

## 3. Create the conda environments

```bash
mamba env create -f environment.yml          # → env: ont-tools
mamba env create -f environment-medaka.yml   # → env: ont-medaka (isolated, ADR-0003)
```

Reproducibility (CRO requirement — no unpinned versions): after the first solve,
generate and commit a lockfile per host architecture, then build from it:

```bash
conda-lock -f environment.yml -p linux-64     # → conda-lock.yml (commit this)
conda-lock install -n ont-tools conda-lock.yml
```

## 4. Install Dorado (+ v6.0 models)

```bash
bash bin/install_dorado.sh
```

Installs Dorado 2.0.0 under `tools/` (gitignored), symlinks `tools/dorado`, and
lists the v6.0 DNA models. The script does **not** hardcode model identifier
strings — it prints the matching v6.0 HAC/SUP names from `dorado download --list`;
fetch them with:

```bash
tools/dorado/bin/dorado download --model <exact-hac-v6-name> --models-directory tools/dorado-models
tools/dorado/bin/dorado download --model <exact-sup-v6-name> --models-directory tools/dorado-models
```

## 5. Install Nextflow

```bash
bash bin/install_nextflow.sh   # requires Java 17; pins NXF_VER=26.04.3
```

## 6. Verify

```bash
# main env
mamba run -n ont-tools bash -c '
  seqkit version; minimap2 --version; samtools --version | head -1;
  bcftools --version | head -1; autocycler --version; dnaapler --version;
  rasusa --version; filtlong --version'

# isolated medaka env
mamba run -n ont-medaka medaka --version    # expect 2.2.2

# binaries
tools/dorado/bin/dorado --version           # expect 2.0.0
tools/nextflow -version                      # expect 26.04.3
```

Each command should report exactly the pinned version in the table above. Any
mismatch means the solve drifted — regenerate the lockfile and re-pin.
