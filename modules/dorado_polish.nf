// DORADO_POLISH — polish the reoriented consensus with the dorado 2.0.0 host binary (M4).
// dorado polish is ONT's high-accuracy assembly polisher (ADR-0010; sidesteps the
// bioconda-medaka issues in ADR-0003). GPU path: host binary, no container, maxForks 1,
// cuda:0 (same rules as DORADO_BASECALL, label 'gpu'). Reads are aligned to the draft
// first, then polished. GPU polishing is NOT byte-deterministic — the manifest records what
// was produced (per the basecall caveat); the downstream CPU AB1 path stays byte-identical.

process DORADO_POLISH {
    tag   "polish:${barcode}"
    label 'gpu'

    publishDir path: { "${params.outdir}/plasmid/${barcode}" }, mode: 'copy',
               pattern: '{consensus.fasta,polish.stage.json}'

    input:
    tuple val(barcode), path(draft), path(reads)

    output:
    tuple val(barcode), path('consensus.fasta'), emit: consensus
    path 'polish.stage.json'                   , emit: manifest
    path 'versions.yml'                        , emit: versions

    script:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    minimap2 -ax map-ont -t ${task.cpus} "${draft}" "${reads}" 2>/dev/null \\
        | samtools sort -@ ${task.cpus} -o aln.bam -
    samtools index aln.bam

    # dorado polish: positional args are (in_aln_bam, in_draft_fastx). --bacteria optimises
    # for plasmids/bacteria; --models-directory finds or auto-downloads the polish model.
    "${params.dorado_bin}" polish \\
        --device ${params.cuda_device} \\
        --bacteria \\
        --models-directory "${params.dorado_models_dir}" \\
        aln.bam "${draft}" > consensus.fasta

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name polish --tool dorado \\
        --tool-version "\$("${params.dorado_bin}" --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)" \\
        --param device=${params.cuda_device} --param barcode=${barcode} \\
        --input "${draft}" --output consensus.fasta \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out polish.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        minimap2: \$(minimap2 --version)
    VERSIONS
    """

    stub:
    """
    cp "${draft}" consensus.fasta
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name polish --tool dorado --tool-version stub \\
        --param device=${params.cuda_device} --param barcode=${barcode} \\
        --input "${draft}" --output consensus.fasta \\
        --started "\$started" --finished "\$started" --status ok \\
        --out polish.stage.json
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
    VERSIONS
    """
}
