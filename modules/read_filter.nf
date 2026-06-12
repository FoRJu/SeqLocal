// READ_FILTER — length/quality filter the per-barcode reads before assembly (M4).
// filtlong from the pinned ont-tools env. Params are per-tier (aggressive filtering for
// repeat-containing constructs is a CLAUDE.md guardrail).

process READ_FILTER {
    tag   "filter:${barcode}"
    label 'samtools'

    input:
    tuple val(barcode), path(reads)

    output:
    tuple val(barcode), path('filtered.fastq.gz'), emit: reads
    path 'versions.yml'                          , emit: versions

    script:
    """
    filtlong --min_length ${params.filter_min_len} \\
        --keep_percent ${params.filter_keep_percent} \\
        "${reads}" 2>/dev/null | gzip -c > filtered.fastq.gz

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        filtlong: \$(filtlong --version | sed 's/Filtlong //')
    VERSIONS
    """

    stub:
    """
    zcat -f "${reads}" 2>/dev/null | gzip -c > filtered.fastq.gz || echo | gzip -c > filtered.fastq.gz
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        filtlong: stub
    VERSIONS
    """
}
