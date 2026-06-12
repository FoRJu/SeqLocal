// DNAAPLER_REORIENT — canonically reorient circular contigs (M4).
// "Inconsistent circular start positions" is a CLAUDE.md guardrail: always reorient final
// circular contigs with dnaapler so every delivery is consistently oriented. Non-circular
// input passes through unchanged. dnaapler from the pinned ont-tools env.

process DNAAPLER_REORIENT {
    tag   "reorient:${barcode}"
    label 'samtools'

    input:
    tuple val(barcode), path(consensus)

    output:
    tuple val(barcode), path('reoriented.fasta'), emit: consensus
    path 'versions.yml'                         , emit: versions

    script:
    """
    if dnaapler all -i "${consensus}" -o dnaapler_out -p reorient -t ${task.cpus} 2>/dev/null \\
        && [ -s dnaapler_out/reorient_reoriented.fasta ]; then
        cp dnaapler_out/reorient_reoriented.fasta reoriented.fasta
    else
        # Not circular / dnaapler found no canonical gene — keep the input as-is.
        cp "${consensus}" reoriented.fasta
    fi

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dnaapler: \$(dnaapler --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)
    VERSIONS
    """

    stub:
    """
    cp "${consensus}" reoriented.fasta
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dnaapler: stub
    VERSIONS
    """
}
