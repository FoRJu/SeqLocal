#!/usr/bin/env bash
# ont_pipeline.sh — thin entry layer: barcode + sample sheet → service-tier subworkflow.
#
# SCAFFOLD ONLY (M0). Routing logic is implemented in M1+ (see docs/PLAN.md).
# This stub exists so the directory tree matches PLAN.md and the entrypoint path is
# stable. Do not add pipeline logic here without a plan-mode approval (CLAUDE.md).
set -euo pipefail

usage() {
  cat <<'EOF'
ont_pipeline.sh (scaffold — not yet implemented)

Planned usage:
  ont_pipeline.sh --samplesheet <sheet.csv> --barcode <BCxx> [--tier plasmid|plasmid_advanced|amplicon]

Routes a barcode through its service-tier Nextflow subworkflow (workflows/main.nf).
Implemented starting in M1 (basecall + demux). See docs/PLAN.md.
EOF
}

usage
exit 0
