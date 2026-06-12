// CONSENSUS_QC — per-base QC + size/depth check for the polished consensus (M4).
// Realign reads -> pileup counts (reused by the AB1 path) -> per-base QC FASTQ
// (python/amplicon/qc.py) and a size-vs-expected / depth QC record. The final
// consensus.fasta deliverable is published by DORADO_POLISH; this adds the QC FASTQ.

process CONSENSUS_QC {
    tag   "consensus_qc:${barcode}"
    label 'samtools'

    publishDir path: { "${params.outdir}/plasmid/${barcode}" }, mode: 'copy',
               pattern: '{*.qc.fastq,*.qc.json,counts.tsv}'

    input:
    tuple val(barcode), path(consensus), path(reads), val(genome_size)

    output:
    tuple val(barcode), path("${barcode}.qc.fastq"), emit: qc_fastq
    path "${barcode}.qc.json"                       , emit: qc
    tuple val(barcode), path('counts.tsv')          , emit: counts
    path 'versions.yml'                             , emit: versions

    script:
    """
    minimap2 -ax map-ont -t ${task.cpus} "${consensus}" "${reads}" 2>/dev/null \\
        | samtools sort -@ ${task.cpus} -o aln.bam -
    samtools index aln.bam
    samtools mpileup -f "${consensus}" aln.bam 2>/dev/null \\
        | python3 "${params.amplicon_cli_dir}/pileup.py" "${consensus}" > counts.tsv

    PYTHONPATH="${params.python_dir}" python3 -m amplicon.qc \\
        --consensus "${consensus}" --counts counts.tsv --out ${barcode} --name ${barcode}

    len=\$(grep -v '^>' "${consensus}" | tr -d '\\n' | wc -c | tr -d ' ')
    depth=\$(samtools depth -a aln.bam 2>/dev/null | awk '{s+=\$3; n++} END{printf "%.1f", (n? s/n : 0)}')
    expected=${genome_size}
    python3 - "${barcode}" "\$len" "\$depth" "\$expected" > ${barcode}.qc.json <<'PY'
    import json, sys
    bc, length, depth, expected = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
    ratio = (length / expected) if expected else None
    status = "ok" if (ratio is None or 0.8 <= ratio <= 1.25) else "size_warn"
    print(json.dumps({"barcode": bc, "consensus_length": length, "mean_depth": depth,
                      "expected_bp": expected, "length_ratio": ratio, "status": status},
                     sort_keys=True, indent=2))
    PY

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: \$(samtools --version | head -n1 | sed 's/samtools //')
    VERSIONS
    """

    stub:
    """
    n=\$(grep -v '^>' "${consensus}" | tr -d '\\n' | wc -c | tr -d ' ')
    printf 'pos\\tA\\tC\\tG\\tT\\n' > counts.tsv
    i=0; while [ \$i -lt \$n ]; do printf '%s\\t30\\t1\\t1\\t1\\n' "\$i" >> counts.tsv; i=\$((i+1)); done
    PYTHONPATH="${params.python_dir}" python3 -m amplicon.qc \\
        --consensus "${consensus}" --counts counts.tsv --out ${barcode} --name ${barcode}
    printf '{"barcode":"${barcode}","status":"ok"}\\n' > ${barcode}.qc.json
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: stub
    VERSIONS
    """
}
