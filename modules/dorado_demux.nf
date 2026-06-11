// DORADO_DEMUX — basecalled BAM -> per-barcode BAMs + summary.
// `--kit-name` makes demux classify (recommended 2.x path; ADR-0005). Host binary.
// Dorado 2.0.0 writes a NESTED output tree under --output-dir (keyed by run id), and
// `--emit-summary` writes `sequencing_summary.txt` to the root of that dir. So the BAMs
// are matched recursively (demux/**/*.bam) and the summary is demux/sequencing_summary.txt.
// Emits a run-manifest stage fragment hashing calls.bam + all demuxed BAMs + summary (ADR-0007).

process DORADO_DEMUX {
    tag   "demux:${params.barcode_kit}"
    label 'gpu'   // host Dorado binary (CPU work here, but same no-container rule)

    // Publish the whole demux tree (nested bams + summary) under outdir/demux/.
    publishDir "${params.outdir}", mode: 'copy', pattern: 'demux/**'

    input:
    path bam

    output:
    path 'demux/**/*.bam'                 , emit: bams
    path 'demux/sequencing_summary.txt'   , emit: summary
    path 'demux.stage.json'               , emit: manifest
    path 'versions.yml'                   , emit: versions

    script:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    "${params.dorado_bin}" demux \\
        --kit-name ${params.barcode_kit} \\
        --emit-summary \\
        --output-dir demux \\
        "${bam}"

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    dver=\$("${params.dorado_bin}" --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)

    # Hash whatever dorado actually produced (sorted, deterministic): the summary at the
    # output-dir root + every BAM anywhere in the nested tree. Glob-based so a layout
    # change can't silently reference a missing path.
    out_args=""
    for f in demux/sequencing_summary.txt \$(find demux -name '*.bam' | sort); do
        [ -e "\$f" ] && out_args="\$out_args --output \$f"
    done

    python3 "${params.provenance_cli}" stage \\
        --name demux --tool dorado --tool-version "\$dver" \\
        --param kit=${params.barcode_kit} \\
        --input "${bam}" \$out_args \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out demux.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: \$("${params.dorado_bin}" --version 2>&1 | head -n1)
        kit: "${params.barcode_kit}"
    VERSIONS
    """

    stub:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    # Mirror dorado's nested layout: bams under demux/<run>/, summary at demux/ root.
    mkdir -p demux/stubrun
    touch demux/stubrun/${params.barcode_kit}_barcode01.bam
    touch demux/stubrun/${params.barcode_kit}_barcode02.bam
    touch demux/stubrun/unclassified.bam
    printf 'read_id\\tbarcode\\n' > demux/sequencing_summary.txt

    out_args=""
    for f in demux/sequencing_summary.txt \$(find demux -name '*.bam' | sort); do
        [ -e "\$f" ] && out_args="\$out_args --output \$f"
    done
    python3 "${params.provenance_cli}" stage \\
        --name demux --tool dorado --tool-version stub \\
        --param kit=${params.barcode_kit} \\
        --input "${bam}" \$out_args \\
        --started "\$started" --finished "\$started" --status ok \\
        --out demux.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        dorado: stub
        kit: "${params.barcode_kit}"
    VERSIONS
    """
}
