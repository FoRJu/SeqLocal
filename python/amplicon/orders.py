"""Load + validate the real VirtuizeBio run intake and join it into per-barcode jobs.

Two real formats (see docs/amplicon-orders.md):
- **Sample sheet** — TSV (tab-delimited, despite a .csv name), with a metadata preamble, a
  header row beginning `Well`, then 96 barcode rows (most empty). Populated rows carry a
  `Sample Name` and an `Order` of the form `Customer#orderid#`.
- **Order detail** — multi-section CSV: `Order No,<id>`, `Service Type,<name>`, and a
  `Samples (N)` table (`#,Sample ID,DNA Name,…`).

Join key: the sample sheet `Sample Name` equals the order's **DNA Name** (not Sample ID).
Validation is loud and hand-rolled (stdlib `csv`; no jsonschema dep).
"""
import csv
from collections import namedtuple

# Service Type (order header) -> internal assay.
SERVICE_TYPE_TO_ASSAY = {
    "whole plasmid sequencing": "PLASMID",
    "wais": "WAIS",
    "fais": "FAIS",
}
ASSAYS = set(SERVICE_TYPE_TO_ASSAY.values())

# One unit of work: a barcode -> its sample -> assay + primer names + size.
SampleJob = namedtuple(
    "SampleJob",
    "barcode sample_id dna_name order_id customer assay "
    "single_primer primer_f primer_r size_kb customer_primers")


# --------------------------------------------------------------------------- sample sheet
def load_samplesheet(path):
    """Parse the run sample-sheet TSV -> [{barcode, sample_name, order_id, customer}].

    Skips the metadata preamble and empty barcodes; loud on a malformed `Order`."""
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))

    header_idx = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Well"), None)
    if header_idx is None:
        raise ValueError("sample sheet %s: no header row beginning 'Well'" % path)
    cols = {name.strip(): i for i, name in enumerate(rows[header_idx])}
    for need in ("Barcode", "Sample Name", "Order"):
        if need not in cols:
            raise ValueError("sample sheet %s: missing column %r" % (path, need))

    out = []
    for r in rows[header_idx + 1:]:
        if not r:
            continue
        def cell(name):
            i = cols[name]
            return r[i].strip() if i < len(r) else ""
        barcode, sample_name, order = cell("Barcode"), cell("Sample Name"), cell("Order")
        if not (sample_name and order):       # unused well
            continue
        parts = [p for p in order.split("#") if p != ""]
        if len(parts) < 2:
            raise ValueError("sample sheet %s: malformed Order %r (want Customer#orderid#)"
                             % (path, order))
        out.append({"barcode": barcode, "sample_name": sample_name,
                    "order_id": parts[1], "customer": parts[0]})
    if not out:
        raise ValueError("sample sheet %s: no populated barcodes" % path)
    return out


# --------------------------------------------------------------------------- order detail
def _assay_from_service_type(service_type, path):
    key = service_type.strip().lower()
    for needle, assay in SERVICE_TYPE_TO_ASSAY.items():
        if needle in key:
            return assay
    raise ValueError("order %s: unknown Service Type %r" % (path, service_type))


def _num_or_none(v):
    v = (v or "").strip()
    if v in ("", "-"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _val_or_none(v):
    v = (v or "").strip()
    return None if v in ("", "-") else v


def load_order(path):
    """Parse one multi-section order CSV -> normalized order dict.

    Returns {order_id, assay, service_type, samples: {dna_name: {sample_id, dna_name,
    size_kb, primer_f, primer_r, single_primer}}}."""
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))

    order_id = service_type = None
    sample_hdr_idx = None
    for i, r in enumerate(rows):
        if not r:
            continue
        key = r[0].strip()
        if key == "Order No" and len(r) > 1:
            order_id = r[1].strip()
        elif key == "Service Type" and len(r) > 1:
            service_type = r[1].strip()
        elif key.startswith("Samples") and "(" in key:   # "Samples (6)"
            sample_hdr_idx = i + 1
            break
    if not order_id:
        raise ValueError("order %s: missing 'Order No'" % path)
    if not service_type:
        raise ValueError("order %s: missing 'Service Type'" % path)
    assay = _assay_from_service_type(service_type, path)
    if sample_hdr_idx is None or sample_hdr_idx >= len(rows):
        raise ValueError("order %s: no 'Samples (N)' section" % path)

    hdr = {name.strip(): j for j, name in enumerate(rows[sample_hdr_idx])}
    if "Sample ID" not in hdr or "DNA Name" not in hdr:
        raise ValueError("order %s: Samples header missing Sample ID / DNA Name" % path)
    size_col = next((c for c in hdr if "Size (Kb)" in c), None)   # Plasmid/Insert Size

    samples = {}
    for r in rows[sample_hdr_idx + 1:]:
        if not r or not r[hdr["Sample ID"]].strip():
            continue
        def cell(name):
            j = hdr.get(name)
            return r[j].strip() if (j is not None and j < len(r)) else ""
        dna = cell("DNA Name")
        samples[dna] = {
            "sample_id": cell("Sample ID"),
            "dna_name": dna,
            "size_kb": _num_or_none(cell(size_col) if size_col else ""),
            "primer_f": _val_or_none(cell("F Primer")),
            "primer_r": _val_or_none(cell("R Primer")),
            "single_primer": _val_or_none(cell("Primers")),
        }
    if not samples:
        raise ValueError("order %s: no sample rows" % path)
    return {"order_id": order_id, "assay": assay, "service_type": service_type,
            "samples": samples}


def load_orders(paths):
    """Load several order CSVs -> {order_id: order}; loud on duplicate order_id."""
    orders = {}
    for p in paths:
        o = load_order(p)
        if o["order_id"] in orders:
            raise ValueError("duplicate order_id %s" % o["order_id"])
        orders[o["order_id"]] = o
    return orders


# --------------------------------------------------------------------------- join
def join(samplesheet_rows, orders):
    """Join sample-sheet rows to their orders (Sample Name == DNA Name) -> [SampleJob]."""
    jobs = []
    for row in samplesheet_rows:
        oid = row["order_id"]
        if oid not in orders:
            raise ValueError("sample sheet references unknown order_id %s (barcode %s)"
                             % (oid, row["barcode"]))
        order = orders[oid]
        s = order["samples"].get(row["sample_name"])
        if s is None:
            raise ValueError("sample name %r (barcode %s) not found in order %s by DNA Name"
                             % (row["sample_name"], row["barcode"], oid))
        assay = order["assay"]
        if assay == "FAIS" and not s["single_primer"]:
            raise ValueError("FAIS sample %s (order %s) has no primer" % (s["sample_id"], oid))
        if assay == "WAIS" and not (s["primer_f"] and s["primer_r"]):
            raise ValueError(
                "WAIS sample %s (order %s) needs F & R primers; no-primer insert-inference "
                "is M3 Phase 2" % (s["sample_id"], oid))
        # PLASMID: no primers required.
        jobs.append(SampleJob(
            barcode=row["barcode"], sample_id=s["sample_id"], dna_name=s["dna_name"],
            order_id=oid, customer=row["customer"], assay=assay,
            single_primer=s["single_primer"], primer_f=s["primer_f"], primer_r=s["primer_r"],
            size_kb=s["size_kb"], customer_primers=[]))
    return jobs
