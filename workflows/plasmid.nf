// plasmid.nf — M4 plasmid tier (tier 1): full circular consensus + per-base QC.
// Routes plasmid-tier barcodes through the shared assembly core and delivers the circular
// consensus FASTA + per-base QC FASTQ (published by ASSEMBLE_CONSENSUS to plasmid/<barcode>/).
// Annotation / insert localization / variants are the advanced tier (M5).

include { ASSEMBLE_CONSENSUS } from './assemble.nf'

workflow PLASMID {
    take:
    ch_reads_size      // tuple(barcode, reads, genome_size_bp)

    main:
    ASSEMBLE_CONSENSUS(ch_reads_size)

    emit:
    consensus = ASSEMBLE_CONSENSUS.out.consensus
    qc_fastq  = ASSEMBLE_CONSENSUS.out.qc_fastq
    qc        = ASSEMBLE_CONSENSUS.out.qc
}
