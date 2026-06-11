#!/usr/bin/env bash
# sync.sh — push the working tree from this Mac to the Ubuntu GPU box (fast loop).
#
# One-directional (Mac → box): the Mac is the editing source, the box is the runtime.
# Configure the destination once in an untracked .sync.env at repo root:
#     SYNC_DEST="user@ont-box:~/SeqLocal"
# See docs/DEV_WORKFLOW.md.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

# Load destination (env var wins; else .sync.env).
if [[ -z "${SYNC_DEST:-}" && -f .sync.env ]]; then
  # shellcheck disable=SC1091
  source .sync.env
fi
if [[ -z "${SYNC_DEST:-}" ]]; then
  echo "!! SYNC_DEST not set. Create .sync.env:" >&2
  echo '   echo '\''SYNC_DEST="user@ont-box:~/SeqLocal"'\'' > .sync.env' >&2
  exit 1
fi

# Exclude heavy/gitignored paths and local-only config. --delete keeps the box's
# code tree a mirror of the Mac's (does NOT touch excluded dirs like results/).
rsync -avz --delete \
  --exclude '.git' \
  --exclude '.sync.env' \
  --exclude 'tools/' \
  --exclude 'work/' \
  --exclude 'results/' \
  --exclude '.nextflow*' \
  --exclude '__pycache__/' \
  --exclude '*.pod5' \
  --exclude '*.fast5' \
  --exclude '*.bam' \
  --exclude '.DS_Store' \
  "${@:-}" \
  ./ "${SYNC_DEST}/"

echo ">> Synced ${REPO} → ${SYNC_DEST}"
