// BAM_TO_FASTQ — per-barcode unaligned BAM -> gzipped FASTQ for downstream tiers.
// samtools from the pinned ont-tools conda env (label samtools; ADR-0006).

process BAM_TO_FASTQ {
    tag   "fastq:${barcode}"
    label 'samtools'

    publishDir "${params.outdir}/fastq", mode: 'copy', pattern: '*.fastq.gz'

    input:
    tuple val(barcode), path(bam)

    output:
    tuple val(barcode), path("${barcode}.fastq.gz"), emit: fastq
    path 'versions.yml'                            , emit: versions

    script:
    """
    samtools fastq -@ ${task.cpus} "${bam}" | gzip -c > "${barcode}.fastq.gz"

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: \$(samtools --version | head -n1 | sed 's/samtools //')
    VERSIONS
    """

    stub:
    """
    echo | gzip -c > "${barcode}.fastq.gz"
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: stub
    VERSIONS
    """
}
