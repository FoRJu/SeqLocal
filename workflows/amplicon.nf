// amplicon.nf — M3 Phase 1 amplicon tier subworkflow.
// per-barcode reads -> provisional consensus -> pileup counts -> primer match / region
// extraction (FAIS/WAIS) -> AB1 + FASTA + FASTQ + per-sample QC. Consumed by main.nf when
// --samplesheet is given. The consensus step is a provisional seam (ADR-0009); the real
// assembler/circularization arrives at M3 Phase 2 / M4.

include { AMPLICON_CONSENSUS } from '../modules/amplicon_consensus.nf'
include { PILEUP_COUNTS      } from '../modules/pileup_counts.nf'
include { PRIMER_REGION      } from '../modules/primer_region.nf'

workflow AMPLICON {
    take:
    ch_fastq        // tuple(barcode, reads.fastq.gz) — barcodes already filtered to the sheet
    samplesheet     // path
    orders_dir      // path (directory of order *.json)
    primers         // path (repo primer registry CSV)

    main:
    AMPLICON_CONSENSUS(ch_fastq)

    // (barcode, consensus, reads) for the pileup
    ch_cons_reads = AMPLICON_CONSENSUS.out.consensus.join(ch_fastq)
    PILEUP_COUNTS(ch_cons_reads)

    // (barcode, consensus, counts) for primer match + region + AB1
    ch_cc = AMPLICON_CONSENSUS.out.consensus.join(PILEUP_COUNTS.out.counts)
    PRIMER_REGION(ch_cc, samplesheet, orders_dir, primers)

    emit:
    ab1 = PRIMER_REGION.out.ab1
    qc  = PRIMER_REGION.out.qc
}
