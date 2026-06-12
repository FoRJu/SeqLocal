// PILEUP_COUNTS — (consensus, reads) -> per-position A/C/G/T counts TSV for the AB1.
// Realigns the reads to the consensus and turns the pileup into the counts python/ab1synth
// consumes (this is the "SNP/indel captured -> AB1 double-peaks" path). ont-tools env.

process PILEUP_COUNTS {
    tag   "pileup:${barcode}"
    label 'samtools'

    publishDir path: { "${params.outdir}/amplicon/${barcode}" }, mode: 'copy', pattern: 'counts.tsv'

    input:
    tuple val(barcode), path(consensus), path(reads)

    output:
    tuple val(barcode), path('counts.tsv'), emit: counts
    path 'versions.yml'                   , emit: versions

    script:
    """
    minimap2 -a -x map-ont "${consensus}" "${reads}" 2>/dev/null \\
        | samtools sort -@ ${task.cpus} -o aln.bam -
    samtools index aln.bam
    samtools mpileup -f "${consensus}" aln.bam 2>/dev/null \\
        | python3 "${params.amplicon_cli_dir}/pileup.py" "${consensus}" > counts.tsv

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        minimap2: \$(minimap2 --version)
        samtools: \$(samtools --version | head -n1 | sed 's/samtools //')
    VERSIONS
    """

    stub:
    """
    # One flat-coverage row per consensus base so counts length == consensus length.
    n=\$(grep -v '^>' "${consensus}" | tr -d '\\n' | wc -c | tr -d ' ')
    printf 'pos\\tA\\tC\\tG\\tT\\n' > counts.tsv
    i=0
    while [ \$i -lt \$n ]; do printf '%s\\t10\\t1\\t1\\t1\\n' "\$i" >> counts.tsv; i=\$((i+1)); done
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: stub
    VERSIONS
    """
}
