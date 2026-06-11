#!/usr/bin/env bash
# Install Nextflow (pinned, stable) for the ONT pipeline orchestration layer.
#
# Pinned to 26.04.3 stable (NOT edge) — CRO production (ADR-0002).
# Requires Java 17 (Temurin LTS recommended; 21 also supported). On Ubuntu 24.04:
#     sudo apt-get install -y temurin-17-jdk   # via Adoptium apt repo
#
# Usage:  bash bin/install_nextflow.sh
set -euo pipefail

export NXF_VER="26.04.3"

# Install into repo-local tools/ (gitignored). Override with NXF_PREFIX.
PREFIX="${NXF_PREFIX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools}"
mkdir -p "${PREFIX}"

if ! command -v java >/dev/null 2>&1; then
  echo "!! Java not found. Install Temurin JDK 17 (or 21) before continuing." >&2
  exit 1
fi

echo ">> Installing Nextflow ${NXF_VER} (Java: $(java -version 2>&1 | head -1))"
( cd "${PREFIX}" && curl -fsSL https://get.nextflow.io | bash )
chmod +x "${PREFIX}/nextflow"

echo ">> Verifying"
"${PREFIX}/nextflow" -version

echo ">> Nextflow ${NXF_VER} installed at ${PREFIX}/nextflow"
echo "   Add to PATH or symlink, e.g.:  sudo ln -sf ${PREFIX}/nextflow /usr/local/bin/nextflow"
