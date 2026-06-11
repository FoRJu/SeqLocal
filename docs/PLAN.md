# PLAN.md — Design & Build Spec

Companion to CLAUDE.md. CLAUDE.md holds the rules and locked decisions; this file
holds the design rationale, data flows, and build order. Read this to understand
*what* we're building and *in what order*. Greenfield project — nothing exists yet.

## Build order (milestones)

- **M0 — Environment.** Pin and document the toolchain BEFORE any pipeline code.
  Produce `environment.yml` (mamba/bioconda: autocycler, dnaapler, medaka, seqkit,
  minimap2, samtools, bcftools, rasusa, filtlong), a documented Dorado binary install
  (ONT tarball, not conda), and a Nextflow install. Record exact versions.
- **M1 — Basecall + demux.** Dorado (HAC v6.0 default) POD5 → FASTQ/BAM, demux by
  barcode. Verify GPU path on the RTX 4090. Output a clean per-barcode read set.
- **M2 — AB1 synthesizer (bespoke).** The one component with no off-the-shelf
  equivalent — build and unit-test it in isolation against a known consensus before
  wiring it into any tier. See "AB1 algorithm" below.
- **M3 — Amplicon tier.** Primer-anchored orientation → consensus → AB1 + FASTQ +
  FASTA + classic, plus the "single primer + 800 bp strict cutoff" mode.
- **M4 — Plasmid tier.** Assembly (benchmark wf-clone-validation vs Autocycler) →
  dnaapler reorient → polish (benchmark Medaka vs Dorado polish) → circular consensus
  + per-base QC.
- **M5 — Advanced plasmid tier.** M4 + annotation + primer-based insert localization
  + insert-vs-reference variant calls.
- **M6 — Delivery packaging.** Per-tier output bundles, naming, customer-facing QC
  report, failure policy.
- **M7 — Validation.** Run control plasmids/amplicons end-to-end; lock the two pending
  benchmarks (assembler, polisher) and record results in `.claude/memory/decisions.md`.

## Target directory structure

```
ont-pipeline/
├── CLAUDE.md
├── environment.yml
├── docs/
│   ├── PLAN.md                 # this file
│   └── abif-format-notes.md    # ABIF byte-layout reference (write during M2)
├── bin/
│   └── ont_pipeline.sh         # thin entry: barcode + sample sheet → subworkflow
├── workflows/
│   ├── main.nf                 # router on service tier
│   ├── amplicon.nf
│   ├── plasmid.nf
│   └── plasmid_advanced.nf
├── modules/                    # Nextflow DSL2 process modules
├── python/
│   └── ab1synth/               # the AB1 synthesizer package (pip-installable)
├── conf/                       # nextflow.config, container profiles
├── assets/                     # sample-sheet schema, test primers/references
├── tests/
└── .claude/
    ├── agents/                 # subagent defs (research, implementer, validator, docs)
    └── memory/
        ├── decisions.md        # ADR log — benchmark outcomes land here
        └── scratchpad.md
```

## Per-tier data flow

**Amplicon (M3):** demuxed reads → orient to defined primer → (full mode) consensus
over the amplicon via pileup; (Sanger mode) emit primer-anchored 800 bp window with
hard length/quality cutoff → AB1 synth + FASTQ + FASTA + classic.

**Plasmid (M4):** demuxed reads → SeqKit/Filtlong size+quality filter (params per tier,
aggressive for repeat-containing constructs) → Rasusa subsample → multi-assembly
consensus (NOT a single assembler — Flye concatemers) → dnaapler reorient → polish →
circular consensus FASTA + per-base QC FASTQ.

**Advanced plasmid (M5):** plasmid flow + annotation (pLannotate/Bakta) + insert
localization from customer primers + BCFtools insert-vs-reference variants → annotated
GenBank / SnapGene .dna + insert report.

## AB1 algorithm (M2 detail)

ONT has no fluorescence; synthesize the trace from read composition:

1. Align/pile up the contributing reads against the consensus.
2. For each consensus position, count A/T/G/C across the pileup and normalize to
   proportions → these become the four ABIF DATA channel intensities at that position.
3. Base call = consensus base; per-base confidence (PCON) from consensus quality.
4. Write the ABIF binary container: directory entries for PBAS (bases), PCON (quals),
   DATA1–4 (channel traces), plus required header/metadata fields.

Constraints: Biopython reads ABIF but does NOT write it — this encoder is ours.
Build a byte-layout reference in `docs/abif-format-notes.md` as you go. Unit-test by
round-tripping (write → read back with Biopython/seqret → compare bases).

## Notes carried over from planning (so they don't get lost in the move)

- "Dorado 6.0" = the v6.0 *model* generation; the Dorado *executable* is the 1.x line.
- Ubuntu 24.04 LTS now; 26.04 is blocked on NVIDIA CUDA repo support — revisit Q4 2026.
- HAC v6.0 is the throughput default; SUP only for high-value plasmid jobs.
- Two benchmarks are deliberately unresolved until M7: assembler and polisher choice.
