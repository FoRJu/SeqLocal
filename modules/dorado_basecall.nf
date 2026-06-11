// DORADO_BASECALL — POD5 directory -> unaligned BAM (canonical, carries metadata).
// Runs the host Dorado 2.0.0 binary on the GPU (ADR-0005). Basecall is kit-free;
// barcode classification happens in DORADO_DEMUX.

process DORADO_BASECALL {
    tag   "basecall:${params.basecall_model}"
    label 'gpu'

    publishDir "${params.outdir}/basecall", mode: 'copy', pattern: 'calls.bam'

    input:
    path pod5_dir

    output:
    path 'calls.bam'    , emit: bam
    path 'versions.yml' , emit: versions

    script:
    def trim = params.no_trim ? '--no-trim' : ''
    """
    "${params.dorado_bin}" basecaller \\
        ${params.basecall_model} \\
        "${pod5_dir}" \\
        --device ${params.cuda_device} \\
        --models-directory "${params.dorado_models_dir}" \\
        ${trim} \\
        > calls.bam

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        model: "${params.basecall_model}"
    VERSIONS
    """

    stub:
    """
    touch calls.bam
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
        model: "${params.basecall_model}"
    VERSIONS
    """
}
