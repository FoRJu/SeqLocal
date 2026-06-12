# amplicon-orders.md — order intake for the amplicon tier (M3)

How VirtuizeBio FAIS/WAIS orders become pipeline inputs. **The pipeline never parses the
order PDFs** — a transcription/LIMS step produces structured records; the PDF stays the
human artifact. Two assays today (FAIS, WAIS); WAIS insert-inference (no primers) is M3
Phase 2.

## Inputs

| Input | What | Schema |
|-------|------|--------|
| `samplesheet.csv` | per run: `barcode,sample_id,order_id` | `assets/samplesheet.schema.json` |
| order record JSON (one per order) | assay + per-sample primers + sizes | `assets/order.schema.json` |
| `assets/primers.csv` | repo primer registry `name,sequence,notes` | — |

Customer-supplied primers travel in the order's `customer_primers[]` and override/extend
the repo registry. A primer name with no resolvable sequence (unknown, or a blank registry
row) **fails loud**.

## PDF column → record field mapping

| PDF (assay) | PDF column | Record field |
|-------------|-----------|--------------|
| FAIS | `Primers` | `samples[].single_primer` |
| FAIS | `Plasmid Size (Kb)` | `samples[].size_kb` |
| WAIS | `F Primer` | `samples[].primer_f` |
| WAIS | `R Primer` | `samples[].primer_r` |
| WAIS | `Amplicon/Insert Size (Kb)` | `samples[].size_kb` |
| both | `Sample ID` / `DNA Name` | `samples[].sample_id` / `dna_name` |

Primer **orientation comes from how it matches the consensus** (which strand), not the
`-F`/`-R`/`-Rev`/`-For` suffix in the name.

## Examples (transcribed from the sample orders)

FAIS — `7340110.json`:
```json
{ "order_id": "7340110", "assay": "FAIS",
  "samples": [ { "sample_id": "BH_1", "single_primer": "Lucy-F" } ] }
```

WAIS (F&R primers) — `7340118.json`:
```json
{ "order_id": "7340118", "assay": "WAIS",
  "samples": [ { "sample_id": "SAC001", "primer_f": "NA-3", "primer_r": "HA-Rev" } ] }
```

WAIS (insert, no primers) — `7340073`: **M3 Phase 2** (identify insert vs backbone). Such a
record (a WAIS sample with no `primer_f`/`primer_r`) is rejected by the loader today.

## What the tier does (per barcode)

1. **Consensus** (provisional, ADR-0009): reads → reference-free linear consensus.
2. **Pileup counts**: realign reads → `pos,A,C,G,T` TSV (the SNP/indel signal → AB1 peaks).
3. **Primer match + region** (`python/amplicon`):
   - **FAIS**: locate the single primer → 800 bp downstream of its 3′ end (in the matched
     strand's direction).
   - **WAIS**: locate forward + reverse primers → the region between them (RC-aware).
   - **Not found** → `<barcode>.qc.json` with `status: primer_not_found` ("possible wrong
     primer selected") and **no AB1**.
4. **AB1 + FASTA + FASTQ** via `python/ab1synth`, plus a per-sample stage fragment.

## Run

```bash
bin/ont_pipeline.sh --pod5_dir <dir> --barcode_kit <KIT> --outdir results \
  --samplesheet samplesheet.csv --orders_dir orders/ [--primers assets/primers.csv]
```
Without `--samplesheet` the pipeline behaves as M1 (basecall + demux only).
Outputs land in `results/amplicon/<barcode>/`.
