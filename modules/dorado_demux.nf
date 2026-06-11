// DORADO_DEMUX — basecalled BAM -> per-barcode BAMs + barcoding summary.
// `--kit-name` makes demux classify (recommended 2.x path; ADR-0005). Host binary.

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
    path 'versions.yml'                 , emit: versions

    script:
    """
    "${params.dorado_bin}" demux \\
        --kit-name ${params.barcode_kit} \\
        --emit-summary \\
        --output-dir demux \\
        "${bam}"

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        kit: "${params.barcode_kit}"
    VERSIONS
    """

    stub:
    """
    mkdir -p demux
    touch demux/${params.barcode_kit}_barcode01.bam
    touch demux/${params.barcode_kit}_barcode02.bam
    touch demux/unclassified.bam
    printf 'read_id\\tbarcode\\n' > demux/barcoding_summary.txt
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
        kit: "${params.barcode_kit}"
    VERSIONS
    """
}
