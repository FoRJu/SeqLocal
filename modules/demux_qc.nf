// DEMUX_QC — per-barcode read-count QC over the demuxed BAMs.
// Emits a TSV (barcode, reads, status) and flags barcodes below the warn threshold.
// samtools from the pinned ont-tools conda env (label samtools).

process DEMUX_QC {
    tag   'demux_qc'
    label 'samtools'

    publishDir "${params.outdir}/qc", mode: 'copy', pattern: 'readcounts.tsv'

    input:
    path bams      // all per-barcode BAMs (collected)
    path summary   // barcoding_summary.txt (published alongside; kept for provenance)

    output:
    path 'readcounts.tsv', emit: readcounts
    path 'versions.yml'  , emit: versions

    script:
    def min = params.min_reads_per_barcode
    """
    printf 'barcode\\treads\\tstatus\\n' > readcounts.tsv
    for b in ${bams}; do
        name=\$(basename "\$b" .bam)
        n=\$(samtools view -c "\$b")
        status=PASS
        if [ "\$n" -lt ${min} ]; then
            status=LOW
            echo "WARN: \$name has \$n reads (< ${min})" >&2
        fi
        printf '%s\\t%s\\t%s\\n' "\$name" "\$n" "\$status" >> readcounts.tsv
    done

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: \$(samtools --version | head -n1 | sed 's/samtools //')
    VERSIONS
    """

    stub:
    """
    printf 'barcode\\treads\\tstatus\\n' > readcounts.tsv
    printf '%s\\t%s\\t%s\\n' '${params.barcode_kit}_barcode01' '1000' 'PASS' >> readcounts.tsv
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: stub
    VERSIONS
    """
}
