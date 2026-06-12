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
include { PLASMID         } from './workflows/plasmid.nf'

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

    // ---- Service-tier routing (M3/M4) ---------------------------------------
    // With --samplesheet, dispatch each demuxed barcode to its service tier by the order's
    // assay: FAIS/WAIS -> amplicon (M3), PLASMID -> plasmid (M4). Barcodes absent from the
    // sheet (controls/unused) are dropped. This Groovy parse only ROUTES; python/amplicon
    // does the authoritative order validation inside the tier.
    if (params.samplesheet) {
        def sheet = file(params.samplesheet, checkIfExists: true)
        def route = buildRoute(sheet, file(params.orders_dir, checkIfExists: true))

        ch_amplicon = BASECALL_DEMUX.out.fastq
            .filter { bc, fq -> route[bc]?.assay in ['FAIS', 'WAIS'] }
        ch_plasmid = BASECALL_DEMUX.out.fastq
            .filter { bc, fq -> route[bc]?.assay == 'PLASMID' }
            .map    { bc, fq -> tuple(bc, fq, route[bc].size_bp) }

        AMPLICON(
            ch_amplicon,
            sheet,
            file(params.orders_dir),
            file(params.primers, checkIfExists: true)
        )
        PLASMID(ch_plasmid)
    }
}

// Parse the real VirtuizeBio intake (sample-sheet TSV + multi-section order CSVs) into
// barcode -> [assay, size_bp]. Routing-only; python/amplicon is authoritative inside tiers.
// size_bp is 0 when the order doesn't declare a size (estimated from reads in assembly).
def assayFromService(String st) {
    def k = st.toLowerCase()
    if (k.contains('whole plasmid')) return 'PLASMID'
    if (k.contains('wais')) return 'WAIS'
    if (k.contains('fais')) return 'FAIS'
    return null
}

def buildRoute(sheet, ordersDir) {
    // order_id -> [assay, sizes: dna_name -> size_bp]
    def orders = [:]
    ordersDir.listFiles()
        .findAll { it.name.startsWith('Order_') && it.name.endsWith('.csv') }
        .each { f ->
            def lines = f.readLines()
            def orderId = null; def assay = null; def hdrIdx = -1
            lines.eachWithIndex { ln, i ->
                def c = ln.split(',', -1)
                def key = c[0].trim()
                if (key == 'Order No' && c.size() > 1) orderId = c[1].trim()
                else if (key == 'Service Type' && c.size() > 1) assay = assayFromService(c[1].trim())
                else if (key.startsWith('Samples') && key.contains('(') && hdrIdx < 0) hdrIdx = i + 1
            }
            def sizes = [:]
            if (hdrIdx >= 0 && hdrIdx < lines.size()) {
                def hdr = lines[hdrIdx].split(',', -1).collect { it.trim() }
                def dnaCol = hdr.indexOf('DNA Name')
                def sizeCol = hdr.findIndexOf { it.contains('Size (Kb)') }
                ((hdrIdx + 1)..<lines.size()).each { r ->
                    def c = lines[r].split(',', -1)
                    if (dnaCol >= 0 && dnaCol < c.size() && c[dnaCol].trim()) {
                        def sz = (sizeCol >= 0 && sizeCol < c.size()) ? c[sizeCol].trim() : '-'
                        sizes[c[dnaCol].trim()] = (sz && sz != '-') ? ((sz.toDouble() * 1000) as long) : 0L
                    }
                }
            }
            if (orderId) orders[orderId] = [assay: assay, sizes: sizes]
        }

    def lines = sheet.readLines()
    def hdrIdx = lines.findIndexOf { it.split('\t', -1)[0].trim() == 'Well' }
    def hdr = lines[hdrIdx].split('\t', -1).collect { it.trim() }
    def bcCol = hdr.indexOf('Barcode'); def snCol = hdr.indexOf('Sample Name'); def ordCol = hdr.indexOf('Order')
    def route = [:]
    ((hdrIdx + 1)..<lines.size()).each { i ->
        def c = lines[i].split('\t', -1)
        if (c.size() > ordCol) {
            def bc = c[bcCol].trim(); def sn = c[snCol].trim(); def ord = c[ordCol].trim()
            def parts = ord.split('#').findAll { it }
            if (sn && ord && parts.size() >= 2) {
                def o = orders[parts[1]]
                if (o) route[bc] = [assay: o.assay, size_bp: (o.sizes[sn] ?: 0L)]
            }
        }
    }
    return route
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
