// DORADO_DEMUX — basecalled BAM -> per-barcode BAMs + barcoding summary.
// `--kit-name` makes demux classify (recommended 2.x path; ADR-0005). Host binary.
// Emits a run-manifest stage fragment hashing calls.bam + the per-barcode BAMs (ADR-0007).

process DORADO_DEMUX {
    tag   "demux:${params.barcode_kit}"
    label 'gpu'   // host Dorado binary (CPU work here, but same no-container rule)

    // Output files are under demux/; publish to outdir so they land at outdir/demux/.
    publishDir "${params.outdir}", mode: 'copy', pattern: 'demux/*'

    input:
    path bam

    output:
    path 'demux/*.bam'                  , emit: bams
    path 'demux/barcoding_summary.txt'  , emit: summary
    path 'demux.stage.json'             , emit: manifest
    path 'versions.yml'                 , emit: versions

    script:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    "${params.dorado_bin}" demux \\
        --kit-name ${params.barcode_kit} \\
        --emit-summary \\
        --output-dir demux \\
        "${bam}"

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    dver=\$("${params.dorado_bin}" --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)

    # Hash every demuxed BAM (sorted, deterministic) + the summary as stage outputs.
    out_args="--output demux/barcoding_summary.txt"
    for f in \$(ls demux/*.bam 2>/dev/null | sort); do
        out_args="\$out_args --output \$f"
    done

    python3 "${params.provenance_cli}" stage \\
        --name demux --tool dorado --tool-version "\$dver" \\
        --param kit=${params.barcode_kit} \\
        --input "${bam}" \$out_args \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out demux.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        kit: "${params.barcode_kit}"
    VERSIONS
    """

    stub:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    mkdir -p demux
    touch demux/${params.barcode_kit}_barcode01.bam
    touch demux/${params.barcode_kit}_barcode02.bam
    touch demux/unclassified.bam
    printf 'read_id\\tbarcode\\n' > demux/barcoding_summary.txt

    out_args="--output demux/barcoding_summary.txt"
    for f in \$(ls demux/*.bam 2>/dev/null | sort); do
        out_args="\$out_args --output \$f"
    done
    python3 "${params.provenance_cli}" stage \\
        --name demux --tool dorado --tool-version stub \\
        --param kit=${params.barcode_kit} \\
        --input "${bam}" \$out_args \\
        --started "\$started" --finished "\$started" --status ok \\
        --out demux.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
        kit: "${params.barcode_kit}"
    VERSIONS
    """
}
