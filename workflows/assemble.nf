// assemble.nf — shared assembly/consensus core (M4, ADR-0010).
// per-barcode reads + expected size -> filter -> multi-assembler consensus (Autocycler) ->
// reorient (dnaapler) -> polish (dorado) -> per-base QC. Used by the plasmid tier now and,
// later, by the amplicon tier (replacing M3 Phase 1's provisional linear consensus).

include { READ_FILTER         } from '../modules/read_filter.nf'
include { AUTOCYCLER_ASSEMBLE } from '../modules/autocycler_assemble.nf'
include { DNAAPLER_REORIENT   } from '../modules/dnaapler_reorient.nf'
include { DORADO_POLISH       } from '../modules/dorado_polish.nf'
include { CONSENSUS_QC        } from '../modules/consensus_qc.nf'

workflow ASSEMBLE_CONSENSUS {
    take:
    ch_reads_size      // tuple(barcode, reads, genome_size_bp)

    main:
    ch_reads = ch_reads_size.map { bc, reads, gs -> tuple(bc, reads) }
    ch_size  = ch_reads_size.map { bc, reads, gs -> tuple(bc, gs) }

    READ_FILTER(ch_reads)

    // (barcode, filtered_reads, genome_size) for assembly
    ch_assemble_in = READ_FILTER.out.reads.join(ch_size)
        .map { bc, reads, gs -> tuple(bc, reads, gs) }
    AUTOCYCLER_ASSEMBLE(ch_assemble_in)

    DNAAPLER_REORIENT(AUTOCYCLER_ASSEMBLE.out.consensus)

    // polish needs the (filtered) reads aligned to the reoriented draft
    ch_polish_in = DNAAPLER_REORIENT.out.consensus.join(READ_FILTER.out.reads)
    DORADO_POLISH(ch_polish_in)

    // QC: polished consensus + reads + expected size
    ch_qc_in = DORADO_POLISH.out.consensus
        .join(READ_FILTER.out.reads)
        .join(ch_size)
        .map { bc, cons, reads, gs -> tuple(bc, cons, reads, gs) }
    CONSENSUS_QC(ch_qc_in)

    emit:
    consensus = DORADO_POLISH.out.consensus       // tuple(barcode, consensus.fasta)
    counts    = CONSENSUS_QC.out.counts           // tuple(barcode, counts.tsv)
    qc_fastq  = CONSENSUS_QC.out.qc_fastq          // tuple(barcode, qc.fastq)
    qc        = CONSENSUS_QC.out.qc
}
