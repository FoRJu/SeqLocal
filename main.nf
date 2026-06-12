#!/usr/bin/env nextflow
// main.nf — ONT pipeline entry. M1: basecall + demux → per-barcode BAM + FASTQ + QC.
// Lives at the repo root so `projectDir` resolves to the repo root (and ${projectDir}
// tooling paths — dorado_bin, models, conda env, provenance_cli — are correct).
// Service-tier routing (amplicon/plasmid/advanced) is added in M3; this entry currently
// runs only the BASECALL_DEMUX subworkflow.

nextflow.enable.dsl = 2

include { DORADO_BASECALL } from './modules/dorado_basecall.nf'
include { DORADO_DEMUX    } from './modules/dorado_demux.nf'
include { BAM_TO_FASTQ    } from './modules/bam_to_fastq.nf'
include { DEMUX_QC        } from './modules/demux_qc.nf'
include { MANIFEST_MERGE  } from './modules/manifest_merge.nf'
include { AMPLICON        } from './workflows/amplicon.nf'

// ---- Param validation -------------------------------------------------------
def required(name, value) {
    if (value == null || value.toString().trim() == '') {
        exit 1, "ERROR: --${name} is required. See docs/RUNNING.md."
    }
}

workflow {
    required('pod5_dir', params.pod5_dir)
    required('barcode_kit', params.barcode_kit)

    if (!workflow.stubRun && !file(params.dorado_bin).exists()) {
        exit 1, "ERROR: Dorado binary not found at ${params.dorado_bin}. Run bin/install_dorado.sh."
    }

    BASECALL_DEMUX(file(params.pod5_dir, checkIfExists: true))

    // ---- Service-tier routing (M3) ------------------------------------------
    // With --samplesheet, route the demuxed per-barcode reads to their service tier.
    // Phase 1: the amplicon tier (FAIS/WAIS). Barcodes absent from the sheet (controls,
    // unused) are dropped here rather than failing downstream.
    if (params.samplesheet) {
        def sheet = file(params.samplesheet, checkIfExists: true)
        def wanted = sheet.readLines()
            .drop(1)                                  // header
            .findAll { it?.trim() }
            .collect { it.split(',')[0].trim() }      // barcode column
            .toSet()

        ch_routed = BASECALL_DEMUX.out.fastq.filter { barcode, fq -> wanted.contains(barcode) }

        AMPLICON(
            ch_routed,
            sheet,
            file(params.orders_dir, checkIfExists: true),
            file(params.primers, checkIfExists: true)
        )
    }
}

// ---- Subworkflow ------------------------------------------------------------
workflow BASECALL_DEMUX {
    take:
    pod5_dir

    main:
    ch_versions = Channel.empty()

    DORADO_BASECALL(pod5_dir)
    ch_versions = ch_versions.mix(DORADO_BASECALL.out.versions)

    DORADO_DEMUX(DORADO_BASECALL.out.bam)
    ch_versions = ch_versions.mix(DORADO_DEMUX.out.versions)

    // Fan out per-barcode BAMs to (barcode_id, bam); drop unclassified from FASTQ export.
    // Dorado 2.0.0 names demuxed BAMs like `<flowcell>_pass_barcode05_<runid>_..bam`
    // (and `..._unclassified_..`), so extract the clean barcode/unclassified token by
    // regex rather than using the whole filename.
    ch_per_barcode = DORADO_DEMUX.out.bams
        .flatten()
        .map { bam ->
            def mt = (bam.name =~ /barcode\d+|unclassified/)
            def label = mt.find() ? mt.group() : bam.simpleName
            tuple(label, bam)
        }
        .filter { barcode, bam -> barcode != 'unclassified' }

    BAM_TO_FASTQ(ch_per_barcode)
    ch_versions = ch_versions.mix(BAM_TO_FASTQ.out.versions.first())

    // QC over ALL barcodes (including unclassified). bams is already one list of
    // per-barcode files (single demux task), so pass it straight in — no .collect().
    DEMUX_QC(DORADO_DEMUX.out.bams, DORADO_DEMUX.out.summary)
    ch_versions = ch_versions.mix(DEMUX_QC.out.versions)

    // Collate provenance.
    ch_versions
        .collectFile(name: 'versions.yml', storeDir: "${params.outdir}/pipeline_info", sort: true)

    // Run manifest (ADR-0007): stage fragments hashed at each boundary + per-barcode
    // deliverables -> one schema-validated run-manifest.json. run_id defaults to the
    // Nextflow run name when the entrypoint did not supply one.
    def run_id = params.run_id ?: workflow.runName
    ch_stage_fragments = DORADO_BASECALL.out.manifest
        .mix(DORADO_DEMUX.out.manifest)
        .collect()
    ch_deliverables = BAM_TO_FASTQ.out.fastq
        .map { barcode, fq -> fq }
        .collect()

    MANIFEST_MERGE(run_id, ch_stage_fragments, ch_deliverables)

    emit:
    fastq      = BAM_TO_FASTQ.out.fastq
    readcounts = DEMUX_QC.out.readcounts
    manifest   = MANIFEST_MERGE.out.manifest
    versions   = ch_versions
}
