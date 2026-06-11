#!/usr/bin/env bash
# ont_pipeline.sh — thin entry layer for the ONT pipeline.
#
# M1 scope: basecall + demux. Asserts the pinned Dorado version, then launches the
# Nextflow workflow. Service-tier routing via sample sheet is added in M3.
#
# Usage:
#   bin/ont_pipeline.sh --pod5_dir <dir> --barcode_kit <KIT> [--outdir results] [-- <extra nextflow args>]
#
# Env:
#   PROFILE   Nextflow profile (default: conda). e.g. PROFILE=docker bin/ont_pipeline.sh ...
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DORADO_BIN="${DORADO_BIN:-${REPO}/tools/dorado/bin/dorado}"
EXPECTED_DORADO="2.0.0"
PROFILE="${PROFILE:-conda}"

POD5_DIR=""
BARCODE_KIT=""
OUTDIR="results"
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pod5_dir)    POD5_DIR="$2"; shift 2 ;;
    --barcode_kit) BARCODE_KIT="$2"; shift 2 ;;
    --outdir)      OUTDIR="$2"; shift 2 ;;
    --)            shift; EXTRA=("$@"); break ;;
    -h|--help)     grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "${POD5_DIR}" ]]    || { echo "ERROR: --pod5_dir is required" >&2; exit 2; }
[[ -n "${BARCODE_KIT}" ]] || { echo "ERROR: --barcode_kit is required" >&2; exit 2; }

# --- Preflight: pin the host Dorado binary version (ADR-0005) -------------------
if [[ ! -x "${DORADO_BIN}" ]]; then
  echo "ERROR: Dorado binary not found/executable at ${DORADO_BIN}. Run bin/install_dorado.sh." >&2
  exit 1
fi
DORADO_VER="$("${DORADO_BIN}" --version 2>&1 | head -n1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [[ "${DORADO_VER}" != "${EXPECTED_DORADO}" ]]; then
  echo "ERROR: Dorado ${EXPECTED_DORADO} required, found '${DORADO_VER:-unknown}' at ${DORADO_BIN}." >&2
  echo "       CLAUDE.md / ADR-0001 pin Dorado to ${EXPECTED_DORADO}." >&2
  exit 1
fi

echo ">> Dorado ${DORADO_VER} OK. Launching Nextflow (profile: ${PROFILE})"
# Launch via the project dir (uses manifest.mainScript) so `projectDir` resolves to
# the repo root — keeps ${projectDir}/environment.yml and tools/ paths correct.
exec nextflow run "${REPO}" \
  -profile "${PROFILE}" \
  --pod5_dir "${POD5_DIR}" \
  --barcode_kit "${BARCODE_KIT}" \
  --outdir "${OUTDIR}" \
  "${EXTRA[@]}"
