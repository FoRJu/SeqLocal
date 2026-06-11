// DORADO_BASECALL — POD5 directory -> unaligned BAM (canonical, carries metadata).
// Runs the host Dorado 2.0.0 binary on the GPU (ADR-0005). Basecall is kit-free;
// barcode classification happens in DORADO_DEMUX.
// Emits a run-manifest stage fragment hashing the POD5 inputs + calls.bam (ADR-0007).

process DORADO_BASECALL {
    tag   "basecall:${params.basecall_model}"
    label 'gpu'

    publishDir "${params.outdir}/basecall", mode: 'copy', pattern: 'calls.bam'

    input:
    path pod5_dir

    output:
    path 'calls.bam'           , emit: bam
    path 'basecall.stage.json' , emit: manifest
    path 'versions.yml'        , emit: versions

    script:
    def trim = params.no_trim ? '--no-trim' : ''
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    "${params.dorado_bin}" basecaller \\
        ${params.basecall_model} \\
        "${pod5_dir}" \\
        --device ${params.cuda_device} \\
        --models-directory "${params.dorado_models_dir}" \\
        ${trim} \\
        > calls.bam

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    dver=\$("${params.dorado_bin}" --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)

    # Hash every POD5 file in the input dir (sorted, deterministic) as stage inputs.
    in_args=""
    for f in \$(ls "${pod5_dir}"/*.pod5 2>/dev/null | sort); do
        in_args="\$in_args --input \$f"
    done

    python3 "${params.provenance_cli}" stage \\
        --name basecall --tool dorado --tool-version "\$dver" \\
        --model "${params.basecall_model}" \\
        --param device=${params.cuda_device} --param no_trim=${params.no_trim} \\
        \$in_args --output calls.bam \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out basecall.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        model: "${params.basecall_model}"
    VERSIONS
    """

    stub:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    touch calls.bam
    python3 "${params.provenance_cli}" stage \\
        --name basecall --tool dorado --tool-version stub \\
        --model "${params.basecall_model}" \\
        --param device=${params.cuda_device} --param no_trim=${params.no_trim} \\
        --output calls.bam \\
        --started "\$started" --finished "\$started" --status ok \\
        --out basecall.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
        model: "${params.basecall_model}"
    VERSIONS
    """
}
