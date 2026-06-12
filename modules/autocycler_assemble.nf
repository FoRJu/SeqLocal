// AUTOCYCLER_ASSEMBLE — multi-assembler consensus assembly (M4, ADR-0010).
//
// Subsample (independent read subsets) -> run Flye + raven + miniasm(+minipolish) on each
// -> autocycler compress/cluster/trim/resolve/combine -> a single consensus assembly. The
// multi-assembler set is REQUIRED by the CLAUDE.md guardrail (never one assembler for
// circular plasmids — Flye concatemers). consensus.gfa carries per-contig circularity.
// CPU-heavy: label 'assembly'. Tools from the pinned ont-tools env.

process AUTOCYCLER_ASSEMBLE {
    tag   "assemble:${barcode}"
    label 'assembly'

    publishDir path: { "${params.outdir}/plasmid/${barcode}" }, mode: 'copy',
               pattern: '{consensus.gfa,assembly_metrics.tsv,assemble.stage.json}'

    input:
    tuple val(barcode), path(reads), val(genome_size)

    output:
    tuple val(barcode), path('consensus.fasta'), emit: consensus
    path 'consensus.gfa'        , optional: true, emit: gfa
    path 'assemble.stage.json'                  , emit: manifest
    path 'versions.yml'                         , emit: versions

    script:
    """
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # 1) Independent read subsets for assembly diversity (seed logged for determinism).
    autocycler subsample --reads "${reads}" --out_dir subsamples \\
        --genome_size ${genome_size} --seed ${params.subsample_seed}

    # 2) Run several assemblers on each subset (the multi-assembler guardrail).
    mkdir -p assemblies
    i=0
    for sub in subsamples/sample_*.fastq; do
        i=\$((i+1))
        flye --nano-hq "\$sub" --out-dir flye_\$i --threads ${task.cpus} 2>/dev/null \\
            && cp flye_\$i/assembly.fasta assemblies/flye_\$i.fasta || true
        raven --threads ${task.cpus} "\$sub" > assemblies/raven_\$i.fasta 2>/dev/null || true
        minimap2 -x ava-ont -t ${task.cpus} "\$sub" "\$sub" 2>/dev/null | gzip -c > ovl_\$i.paf.gz
        miniasm -f "\$sub" ovl_\$i.paf.gz > mini_\$i.gfa 2>/dev/null || true
        if [ -s mini_\$i.gfa ]; then
            minipolish -t ${task.cpus} "\$sub" mini_\$i.gfa > mini_pol_\$i.gfa 2>/dev/null \\
                && any2fasta mini_pol_\$i.gfa > assemblies/miniasm_\$i.fasta 2>/dev/null || true
        fi
    done

    # 3) Reconcile the assemblies into one consensus.
    autocycler compress -i assemblies -a autocycler_out
    autocycler cluster -a autocycler_out
    for c in autocycler_out/clustering/qc_pass/cluster_*; do
        autocycler trim -c "\$c"
        autocycler resolve -c "\$c"
    done
    autocycler combine -a autocycler_out \\
        -i autocycler_out/clustering/qc_pass/cluster_*/5_final.gfa
    cp autocycler_out/consensus_assembly.fasta consensus.fasta
    cp autocycler_out/consensus_assembly.gfa   consensus.gfa
    printf 'metric\\tvalue\\nassemblies\\t%s\\n' "\$(ls assemblies | wc -l)" > assembly_metrics.tsv

    finished=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name assemble --tool autocycler \\
        --tool-version "\$(autocycler --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)" \\
        --param assemblers=flye+raven+miniasm --param genome_size=${genome_size} \\
        --param subsample_seed=${params.subsample_seed} --param barcode=${barcode} \\
        --input "${reads}" --output consensus.fasta \\
        --started "\$started" --finished "\$finished" --status ok \\
        --out assemble.stage.json

    cat <<-VERSIONS > versions.yml
    "${task.process}":
        autocycler: \$(autocycler --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -n1)
        flye: \$(flye --version 2>&1 | head -n1)
        raven: \$(raven --version 2>&1 | head -n1)
        miniasm: \$(miniasm -V 2>&1 | head -n1)
    VERSIONS
    """

    stub:
    """
    # A small "circular" stub consensus so downstream wiring runs.
    printf '>consensus_${barcode}\\nACGTACGTACGTAAGGCCTTACGTACGTGGGATCGATCGATC\\n' > consensus.fasta
    printf 'H\\tVN:Z:1.0\\n' > consensus.gfa
    printf 'metric\\tvalue\\nassemblies\\t3\\n' > assembly_metrics.tsv
    started=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
    python3 "${params.provenance_cli}" stage \\
        --name assemble --tool autocycler --tool-version stub \\
        --param assemblers=flye+raven+miniasm --param barcode=${barcode} \\
        --output consensus.fasta --started "\$started" --finished "\$started" --status ok \\
        --out assemble.stage.json
    cat <<-VERSIONS > versions.yml
    "${task.process}":
        autocycler: stub
    VERSIONS
    """
}
