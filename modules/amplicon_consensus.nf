// AMPLICON_CONSENSUS — per-barcode reads -> a single consensus FASTA.
//
// PROVISIONAL (M3 Phase 1, ADR-0009): reference-free, linear. Longest read as draft
// backbone -> realign all reads (minimap2 map-ont) -> samtools consensus. NO de novo
// assembler and NO circularization yet; the real assembler (Flye/Autocycler/
// wf-clone-validation, the M7 benchmark) drops in HERE at Phase 2/M4. The interface is
// fixed: reads -> consensus.fasta. Tools (seqkit/minimap2/samtools) are the pinned
// ont-tools env (label samtools).

process AMPLICON_CONSENSUS {
    tag   "consensus:${barcode}"
    label 'samtools'

    publishDir path: { "${params.outdir}/amplicon/${barcode}" }, mode: 'copy', pattern: 'consensus.fa'

    input:
    tuple val(barcode), path(reads)

    output:
    tuple val(barcode), path('consensus.fa'), emit: consensus
    path 'consensus.stage.json'             , emit: manifest
    path 'versions.yml'                     , emit: versions

    script:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Draft = the single longest read (provisional reference-free backbone).
    seqkit sort --by-length --reverse "${reads}" | seqkit head -n 1 | seqkit seq > draft.fa

    # Realign all reads to the draft and call a consensus.
    minimap2 -a -x map-ont draft.fa "${reads}" 2>/dev/null \\
        | samtools sort -@ ${task.cpus} -o draft.sorted.bam -
    samtools index draft.sorted.bam
    samtools consensus -f fasta -o consensus.fa draft.sorted.bam
    # Normalize the FASTA header for downstream determinism.
    seqkit replace -p '.*' -r 'consensus_${barcode}' consensus.fa > consensus.tmp && mv consensus.tmp consensus.fa

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name amplicon_consensus --tool samtools-consensus \\
        --tool-version "\$(samtools --version | head -n1 | sed 's/samtools //')" \\
        --param method=provisional_linear --param barcode=${barcode} \\
        --input "${reads}" --output consensus.fa \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out consensus.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        seqkit: \$(seqkit version | sed 's/seqkit //')
        minimap2: \$(minimap2 --version)
        samtools: \$(samtools --version | head -n1 | sed 's/samtools //')
    VERSIONS
    """

    stub:
    """
    # Stub consensus with clean non-palindromic primer sites: StubF(+) ... revcomp(StubR)(-).
    printf '>consensus_${barcode}\\nTTTAAACCCGGGATCGATCGATCAAATGCATGCAA\\n' > consensus.fa
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name amplicon_consensus --tool samtools-consensus --tool-version stub \\
        --param method=provisional_linear --param barcode=${barcode} \\
        --output consensus.fa --started "\$started" --finished "\$started" --status ok \\
        --out consensus.stage.json
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        samtools: stub
    VERSIONS
    """
}
