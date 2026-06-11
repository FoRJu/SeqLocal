#!/usr/bin/env bash
# Install the Dorado basecaller (pinned) + v6.0 DNA models.
#
# Pinned to 2.0.0 — the v6.0 DNA models require the 2.x executable; the 1.x line
# ended at 1.4.0 without them (ADR-0001 in .claude/memory/decisions.md).
# Dorado is a static binary from the ONT CDN, NOT a conda package.
#
# Target host: Ubuntu 24.04 LTS, NVIDIA driver + CUDA 12.8, RTX 4090 (Ada 8.9).
# Usage:  bash bin/install_dorado.sh
set -euo pipefail

DORADO_VERSION="2.0.0"
TARBALL="dorado-${DORADO_VERSION}-linux-x64.tar.gz"
URL="https://cdn.oxfordnanoportal.com/software/analysis/${TARBALL}"

# Install under repo-local tools/ (gitignored). Override with DORADO_PREFIX.
PREFIX="${DORADO_PREFIX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools}"
DEST="${PREFIX}/dorado-${DORADO_VERSION}"
LINK="${PREFIX}/dorado"            # stable symlink → versioned dir
BIN="${LINK}/bin/dorado"

mkdir -p "${PREFIX}"

if [[ ! -x "${DEST}/bin/dorado" ]]; then
  echo ">> Downloading Dorado ${DORADO_VERSION} from ONT CDN"
  tmp="$(mktemp -d)"
  curl -fSL --retry 3 -o "${tmp}/${TARBALL}" "${URL}"
  echo ">> Extracting to ${DEST}"
  mkdir -p "${DEST}"
  tar -xzf "${tmp}/${TARBALL}" -C "${DEST}" --strip-components=1
  rm -rf "${tmp}"
else
  echo ">> Dorado ${DORADO_VERSION} already present at ${DEST}"
fi

ln -sfn "${DEST}" "${LINK}"

echo ">> Verifying"
"${BIN}" --version

# --- v6.0 DNA models ------------------------------------------------------------
# Do NOT hardcode model identifier strings — they change across model gens and a
# wrong guess silently fetches the wrong model. List, then pull the v6.0 DNA
# models (HAC is the throughput default; SUP reserved for high-value plasmid jobs).
MODELS_DIR="${PREFIX}/dorado-models"
mkdir -p "${MODELS_DIR}"

echo ">> Available models (filter for v6.0 DNA HAC/SUP):"
"${BIN}" download --list 2>&1 | grep -Ei 'dna.*(hac|sup).*v6' || {
  echo "!! No v6.0 DNA models matched in --list output. Inspect the full list:"
  echo "     ${BIN} download --list"
  echo "   then fetch with: ${BIN} download --model <exact-name> --models-directory ${MODELS_DIR}"
  exit 1
}

echo ">> To download a model, run e.g.:"
echo "     ${BIN} download --model <exact-hac-v6-name> --models-directory ${MODELS_DIR}"
echo "     ${BIN} download --model <exact-sup-v6-name> --models-directory ${MODELS_DIR}"
echo ">> Dorado ${DORADO_VERSION} installed. Symlink: ${LINK}"
