#!/usr/bin/env nextflow
// main.nf — ONT pipeline entry. M1: basecall + demux → per-barcode BAM + FASTQ + QC.
// Service-tier routing (amplicon/plasmid/advanced) is added in M3; this entry currently
// runs only the BASECALL_DEMUX subworkflow.

nextflow.enable.dsl = 2

include { DORADO_BASECALL } from '../modules/dorado_basecall.nf'
include { DORADO_DEMUX    } from '../modules/dorado_demux.nf'
include { BAM_TO_FASTQ    } from '../modules/bam_to_fastq.nf'
include { DEMUX_QC        } from '../modules/demux_qc.nf'

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
    ch_per_barcode = DORADO_DEMUX.out.bams
        .flatten()
        .map { bam -> tuple(bam.simpleName, bam) }
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

    emit:
    fastq      = BAM_TO_FASTQ.out.fastq
    readcounts = DEMUX_QC.out.readcounts
    versions   = ch_versions
}
