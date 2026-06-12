// PRIMER_REGION — resolve the order, match primers, extract the FAIS/WAIS window, render AB1.
// Runs `python -m amplicon` (logic + ab1synth) against the per-barcode consensus + counts.
// A primer that can't be located writes <barcode>.qc.json with status primer_not_found and
// emits NO AB1 (recognized QC outcome, exit 0). Real intake errors (unknown order, bad
// sample sheet) fail the process loudly. ont-tools env (python + biopython).

process PRIMER_REGION {
    tag   "region:${barcode}"
    label 'samtools'

    publishDir path: { "${params.outdir}/amplicon/${barcode}" }, mode: 'copy',
               pattern: '{*.ab1,*.fasta,*.fastq,*.qc.json,*.stage.json}'

    input:
    tuple val(barcode), path(consensus), path(counts)
    path samplesheet
    path orders_dir
    path primers

    output:
    tuple val(barcode), path("${barcode}.ab1"), optional: true, emit: ab1
    path "${barcode}.qc.json"                                 , emit: qc
    path "${barcode}.stage.json", optional: true              , emit: manifest

    script:
    """
    order_args=""
    for f in ${orders_dir}/*.csv; do
        [ -e "\$f" ] && order_args="\$order_args --order \$f"
    done

    PYTHONPATH="${params.python_dir}" python3 -m amplicon \\
        --barcode ${barcode} \\
        --consensus "${consensus}" --counts "${counts}" \\
        --samplesheet "${samplesheet}" \$order_args --primers "${primers}" \\
        --max-mismatch-frac ${params.max_mismatch_frac} \\
        --out ${barcode} --manifest-out ${barcode}.stage.json
    """

    stub:
    """
    order_args=""
    for f in ${orders_dir}/*.csv; do
        [ -e "\$f" ] && order_args="\$order_args --order \$f"
    done
    PYTHONPATH="${params.python_dir}" python3 -m amplicon \\
        --barcode ${barcode} \\
        --consensus "${consensus}" --counts "${counts}" \\
        --samplesheet "${samplesheet}" \$order_args --primers "${primers}" \\
        --max-mismatch-frac ${params.max_mismatch_frac} \\
        --out ${barcode} --manifest-out ${barcode}.stage.json
    """
}
