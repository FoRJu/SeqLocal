#!/usr/bin/env bash
# ont_pipeline.sh — thin entry layer AND the single integrity / kill-switch chokepoint.
#
# Before doing any work it enforces the "enforced now" hardening seams (CLAUDE.md):
#   1. non-root / bfxsvc      never run as root or a human account
#   2. kill-flag              refuse to run if the local kill-flag is set
#   3. code integrity         hash the repo, compare to a recorded baseline if present
#   4. MinKNOW co-location    yield to a live flow cell (no concurrent basecalling)
#   5. Dorado version gate    assert the pinned 2.0.0 host binary
# then launches the Nextflow workflow, passing run-level provenance into the manifest.
# Service-tier routing via sample sheet is added in M3.
#
# Usage:
#   bin/ont_pipeline.sh --pod5_dir <dir> --barcode_kit <KIT> [--outdir results] \
#     [--samplesheet FILE --orders_dir DIR [--primers FILE]]   # M3 amplicon routing \
#     [--run_id ID] [--sample_id ID] [--service_tier TIER] [--site_id ID] \
#     [--instrument MinION|PromethION] [--flow_cell_id ID] [--run_uuid UUID] \
#     [-- <extra nextflow args>]
#
# With --samplesheet, demuxed barcodes are routed to their service tier (M3 amplicon:
# FAIS/WAIS). Without it, the pipeline runs M1 only (basecall + demux).
#
# Env:
#   PROFILE                    Nextflow profile (default: conda). e.g. PROFILE=docker
#   SEQLOCAL_REQUIRE_BFXSVC=1  hard-fail unless the runtime account is `bfxsvc` (prod)
#   SEQLOCAL_KILL_FLAG         kill-flag path (default: /var/lib/seqlocal/KILL)
#   SEQLOCAL_CODE_HASH         expected repo code sha256 (else /var/lib/seqlocal/code.sha256)
#   SEQLOCAL_FLOWCELL_ACTIVE=1 declare a flow cell is live -> refuse (MinKNOW yield)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DORADO_BIN="${DORADO_BIN:-${REPO}/tools/dorado/bin/dorado}"
EXPECTED_DORADO="2.0.0"
PROFILE="${PROFILE:-conda}"
SERVICE_ACCOUNT="bfxsvc"
KILL_FLAG="${SEQLOCAL_KILL_FLAG:-/var/lib/seqlocal/KILL}"
CODE_HASH_BASELINE_FILE="/var/lib/seqlocal/code.sha256"

POD5_DIR=""
BARCODE_KIT=""
OUTDIR="results"
SAMPLESHEET=""
ORDERS_DIR=""
PRIMERS=""
RUN_ID=""
SAMPLE_ID=""
SERVICE_TIER=""
SITE_ID=""
INSTRUMENT=""
FLOW_CELL_ID=""
RUN_UUID=""
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pod5_dir)     POD5_DIR="$2"; shift 2 ;;
    --barcode_kit)  BARCODE_KIT="$2"; shift 2 ;;
    --outdir)       OUTDIR="$2"; shift 2 ;;
    --samplesheet)  SAMPLESHEET="$2"; shift 2 ;;
    --orders_dir)   ORDERS_DIR="$2"; shift 2 ;;
    --primers)      PRIMERS="$2"; shift 2 ;;
    --run_id)       RUN_ID="$2"; shift 2 ;;
    --sample_id)    SAMPLE_ID="$2"; shift 2 ;;
    --service_tier) SERVICE_TIER="$2"; shift 2 ;;
    --site_id)      SITE_ID="$2"; shift 2 ;;
    --instrument)   INSTRUMENT="$2"; shift 2 ;;
    --flow_cell_id) FLOW_CELL_ID="$2"; shift 2 ;;
    --run_uuid)     RUN_UUID="$2"; shift 2 ;;
    --)             shift; EXTRA=("$@"); break ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "${POD5_DIR}" ]]    || { echo "ERROR: --pod5_dir is required" >&2; exit 2; }
[[ -n "${BARCODE_KIT}" ]] || { echo "ERROR: --barcode_kit is required" >&2; exit 2; }

# Portable sha256 of one file's CONTENT (prints the hex digest only).
sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# ===========================================================================
# Integrity / kill-switch chokepoint — runs BEFORE any pipeline work.
# This is the one place CLAUDE.md designates for image signing + the central
# kill trigger to plug in later (M6/M8); the checks below are the local stubs.
# ===========================================================================

# --- 1. Non-root / service account (CLAUDE.md: never run as root) ----------------
if [[ "${EUID}" -eq 0 ]]; then
  echo "ERROR: refusing to run as root. Use the non-privileged '${SERVICE_ACCOUNT}' account." >&2
  exit 1
fi
CURRENT_USER="$(id -un)"
if [[ "${CURRENT_USER}" != "${SERVICE_ACCOUNT}" ]]; then
  if [[ "${SEQLOCAL_REQUIRE_BFXSVC:-0}" == "1" ]]; then
    echo "ERROR: must run as '${SERVICE_ACCOUNT}' (SEQLOCAL_REQUIRE_BFXSVC=1); current user is '${CURRENT_USER}'." >&2
    exit 1
  fi
  echo ">> WARN: running as '${CURRENT_USER}', not '${SERVICE_ACCOUNT}' (dev/test ok; set SEQLOCAL_REQUIRE_BFXSVC=1 in prod)." >&2
fi

# --- 2. Kill-flag (fail-safe; M8 central trigger flips this local flag) ----------
if [[ -e "${KILL_FLAG}" ]]; then
  echo "ERROR: kill-flag present at ${KILL_FLAG}. HALTING." >&2
  echo "       Fail-safe: in-flight data is quarantined; no deliverables emitted or transmitted." >&2
  echo "       (No data is wiped and no live flow cell is aborted — see docs/security.md.)" >&2
  exit 1
fi

# --- 3. Code integrity (hash repo; compare to baseline if recorded) --------------
# Deterministic, machine-independent: per-file content hash + relative path, over the
# sorted set of git-tracked files (excludes tools/, work/, results/ — they're gitignored).
CODE_SHA256="$(
  git -C "${REPO}" ls-files | LC_ALL=C sort | while IFS= read -r f; do
    printf '%s  %s\n' "$(sha256_file "${REPO}/${f}")" "${f}"
  done | sha256_file /dev/stdin
)"
EXPECTED_CODE_HASH="${SEQLOCAL_CODE_HASH:-}"
if [[ -z "${EXPECTED_CODE_HASH}" && -f "${CODE_HASH_BASELINE_FILE}" ]]; then
  EXPECTED_CODE_HASH="$(tr -d '[:space:]' < "${CODE_HASH_BASELINE_FILE}")"
fi
INTEGRITY_VERIFIED="false"
if [[ -n "${EXPECTED_CODE_HASH}" ]]; then
  if [[ "${CODE_SHA256}" != "${EXPECTED_CODE_HASH}" ]]; then
    echo "ERROR: code integrity check FAILED. Repo hash does not match the recorded baseline." >&2
    echo "       expected ${EXPECTED_CODE_HASH}" >&2
    echo "       got      ${CODE_SHA256}" >&2
    exit 1
  fi
  INTEGRITY_VERIFIED="true"
  echo ">> Code integrity OK (${CODE_SHA256})."
else
  echo ">> WARN: no code-hash baseline recorded (set SEQLOCAL_CODE_HASH or ${CODE_HASH_BASELINE_FILE}); recording unverified. Hash: ${CODE_SHA256}" >&2
fi

# --- 4. MinKNOW co-location (never preempt instrument control) -------------------
# Stub until systemd resource slices (M8): refuse if a flow cell is declared active.
if [[ "${SEQLOCAL_FLOWCELL_ACTIVE:-0}" == "1" ]]; then
  echo "ERROR: a flow cell run is active. Analysis must yield to MinKNOW — not running concurrently." >&2
  exit 1
fi

# --- 5. Preflight: pin the host Dorado binary version (ADR-0005) -----------------
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

GIT_COMMIT="$(git -C "${REPO}" rev-parse --short HEAD 2>/dev/null || echo '')"

echo ">> Preflight OK (user=${CURRENT_USER}, dorado=${DORADO_VER}). Launching Nextflow (profile: ${PROFILE})"

# Launch via the project dir (uses manifest.mainScript = main.nf at the repo root) so
# `projectDir` resolves to the repo root — keeps ${projectDir}/{tools,environment.yml,
# python} paths correct. Run-level provenance is threaded into the manifest header.
#
# Build the arg list, appending optional metadata ONLY when non-empty: Nextflow turns a
# `--param ""` into the boolean `true`, so empty flags must be omitted (the config
# defaults to null, and the manifest header falls back cleanly).
NF_ARGS=(
  -profile "${PROFILE}"
  --pod5_dir "${POD5_DIR}"
  --barcode_kit "${BARCODE_KIT}"
  --outdir "${OUTDIR}"
  --operator "${CURRENT_USER}"
  --code_sha256 "${CODE_SHA256}"
  --integrity_verified "${INTEGRITY_VERIFIED}"
  --kill_flag_present false
)
[[ -n "${SAMPLESHEET}" ]]  && NF_ARGS+=(--samplesheet "${SAMPLESHEET}")
[[ -n "${ORDERS_DIR}" ]]   && NF_ARGS+=(--orders_dir "${ORDERS_DIR}")
[[ -n "${PRIMERS}" ]]      && NF_ARGS+=(--primers "${PRIMERS}")
[[ -n "${GIT_COMMIT}" ]]   && NF_ARGS+=(--git_commit "${GIT_COMMIT}")
[[ -n "${RUN_ID}" ]]       && NF_ARGS+=(--run_id "${RUN_ID}")
[[ -n "${SAMPLE_ID}" ]]    && NF_ARGS+=(--sample_id "${SAMPLE_ID}")
[[ -n "${SERVICE_TIER}" ]] && NF_ARGS+=(--service_tier "${SERVICE_TIER}")
[[ -n "${SITE_ID}" ]]      && NF_ARGS+=(--site_id "${SITE_ID}")
[[ -n "${INSTRUMENT}" ]]   && NF_ARGS+=(--instrument "${INSTRUMENT}")
[[ -n "${FLOW_CELL_ID}" ]] && NF_ARGS+=(--flow_cell_id "${FLOW_CELL_ID}")
[[ -n "${RUN_UUID}" ]]     && NF_ARGS+=(--run_uuid "${RUN_UUID}")

exec nextflow run "${REPO}" "${NF_ARGS[@]}" "${EXTRA[@]}"
