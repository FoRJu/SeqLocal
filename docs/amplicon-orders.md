# amplicon-orders.md — run intake (sample sheet + order detail)

How a VirtuizeBio run is described to the pipeline. **The pipeline never parses the order
PDFs** — it reads the real LIMS exports below. Parser: `python/amplicon/orders.py`
(authoritative); `main.nf` does a light routing parse.

## 1. Sample sheet — TSV (tab-delimited, despite a `.csv` name)

A metadata preamble, then a header row beginning `Well`, then 96 barcode rows (most empty):

```
Run ID   Operator  Machine  Library ID
aa051826a  FF
Plate ID   Operator  Plate Barcode  Barcode Type  ...
aa051826a  FF                        RBK96
Well  Barcode    Sample Name  Order                 Sample Type ... Reference Name
A05   barcode33  pYZ5020C1    ZhonggangHou#7340018#
A06   barcode41  A03_1        DanielOng#7340017#
...
```

- Only rows with a non-empty **`Sample Name`** and **`Order`** are processed; the rest are
  unused wells.
- **`Order` = `Customer#orderid#`** — the order id is the field between the `#`s.
- **`Sample Name` is the construct name** and equals the order's **`DNA Name`** (the join key).

## 2. Order detail — multi-section CSV (one per order, `Order_<id>.csv`)

```
Service Order
Order No,7340017
...
Order Information
Service Type,Whole Plasmid Sequencing
...
Samples (6)
#,Sample ID,DNA Name,Copy number,Conc range,Conc (ng/ul),Plasmid Size (Kb),Vector origin,Notes
1,DO001,A03_1,low copy,20-400 ng/ul,-,-,-,-
...
```

- **`Service Type` → assay:** `Whole Plasmid Sequencing → PLASMID`, `WAIS → WAIS`,
  `FAIS → FAIS` (case-insensitive; loud on unknown).
- The **`Samples (N)`** table is keyed by **`DNA Name`**. Columns are detected by name, by
  assay:
  - **PLASMID:** `Sample ID`, `DNA Name`, `Plasmid Size (Kb)` (often `-` → size estimated
    from reads at assembly).
  - **WAIS:** `F Primer`, `R Primer`, `Insert Size (Kb)`.  *(inferred from the WAIS PDF until
    a real WAIS order CSV is seen.)*
  - **FAIS:** `Primers`, `Plasmid Size (Kb)`.  *(inferred from the FAIS PDF.)*
- `-`/blank → `None`.

## 3. Join + routing

`orders.py` joins on **`(order_id, Sample Name == DNA Name)`** → one `SampleJob` per
populated barcode, carrying `assay`, primer names (FAIS→single, WAIS→F&R, PLASMID→none),
`size_kb`, the order `sample_id` (customer label), and `dna_name`. Loud on: malformed
`Order`, unknown order, unmatched sample name, missing required primers.

`main.nf` routes by assay: **`FAIS|WAIS → amplicon`** (M3), **`PLASMID → plasmid`** (M4).
Barcodes not in the sheet are dropped.

## 4. Primer registry (amplicon tiers)

Named primers resolve from `assets/primers.csv` (repo) + any customer primers; unknown/blank
→ loud. See `docs/RUNNING.md` and the FAIS/WAIS flow in this repo's amplicon tier.

## Run

```bash
bin/ont_pipeline.sh --pod5_dir <dir> --barcode_kit <KIT> --outdir results \
  --samplesheet aa051826a.csv --orders_dir orders/   # orders/ holds Order_<id>.csv
```
Without `--samplesheet`, the pipeline runs M1 (basecall + demux) only. Fixtures live in
`assets/test/` (real `aa051826a` sheet + `Order_7340017/18.csv`) and `assets/test/stub/`.
