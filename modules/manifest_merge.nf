// MANIFEST_MERGE — assemble the run manifest (ADR-0007).
// Builds the run-level header from params (supplied by bin/ont_pipeline.sh, the integrity
// chokepoint) and merges it with the per-stage fragments + per-barcode deliverables into
// a single schema-validated run-manifest.json. Runs python via the ont-tools env (label
// samtools). No stub block: under -stub-run this still runs the real merge on the staged
// stub fragments, so the structural test actually produces+validates a manifest.

process MANIFEST_MERGE {
    tag   'manifest'
    label 'samtools'

    publishDir "${params.outdir}/pipeline_info", mode: 'copy', pattern: 'run-manifest.json'

    input:
    val  run_id
    path stages          // collected *.stage.json fragments
    path deliverables     // collected per-barcode *.fastq.gz (hashed here)

    output:
    path 'run-manifest.json', emit: manifest

    script:
    """
    python3 "${params.provenance_cli}" header \\
        --run-id "${run_id}" \\
        --sample-id "${params.sample_id ?: ''}" \\
        --service-tier "${params.service_tier ?: ''}" \\
        --site-id "${params.site_id ?: ''}" \\
        --instrument "${params.instrument ?: ''}" \\
        --flow-cell-id "${params.flow_cell_id ?: ''}" \\
        --run-uuid "${params.run_uuid ?: ''}" \\
        --operator "${params.operator ?: ''}" \\
        --git-commit "${params.git_commit ?: ''}" \\
        --code-sha256 "${params.code_sha256 ?: ''}" \\
        --code-hash-verified ${params.integrity_verified} \\
        --kill-flag-present ${params.kill_flag_present} \\
        --out header.json

    # Shell globs sort alphabetically -> basecall.stage.json before demux.stage.json,
    # giving a stable stage order even when stub timestamps tie.
    stage_args=""
    for f in *.stage.json; do [ -e "\$f" ] && stage_args="\$stage_args --stage \$f"; done
    deliv_args=""
    for f in *.fastq.gz; do [ -e "\$f" ] && deliv_args="\$deliv_args --deliverable \$f"; done

    python3 "${params.provenance_cli}" merge \\
        --header header.json \$stage_args \$deliv_args \\
        --out run-manifest.json
    """
}
