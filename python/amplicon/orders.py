"""Load + validate the per-run sample sheet and per-order records, and join them.

Sample sheet (`barcode,sample_id,order_id`) ties a demuxed barcode to its sample + order;
the order record (order.schema.json) carries assay + primers + sizes. Validation is loud
and hand-rolled (stdlib only — mirrors assets/*.schema.json; no jsonschema dependency,
consistent with python/provenance). Produces one SampleJob per sample-sheet row.
"""
import csv
import json
from collections import namedtuple

ASSAYS = {"FAIS", "WAIS", "PLASMID"}

# A resolved unit of work: one barcode -> one sample -> its assay + primer names.
SampleJob = namedtuple(
    "SampleJob",
    "barcode sample_id order_id assay single_primer primer_f primer_r size_kb customer_primers")


def load_samplesheet(path):
    """Parse samplesheet.csv -> [{barcode, sample_id, order_id}], validated (loud)."""
    rows = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"barcode", "sample_id", "order_id"}
        missing_cols = required - set(h.strip() for h in (reader.fieldnames or []))
        if missing_cols:
            raise ValueError("samplesheet missing columns: %s" % sorted(missing_cols))
        for n, row in enumerate(reader, 2):
            rec = {k: (row.get(k) or "").strip() for k in required}
            for k, v in rec.items():
                if not v:
                    raise ValueError("samplesheet line %d: empty %s" % (n, k))
            rows.append(rec)
    if not rows:
        raise ValueError("samplesheet has no rows: %s" % path)
    return rows


def load_order(path):
    """Load + validate one order record JSON against order.schema.json's rules (loud)."""
    with open(path) as fh:
        order = json.load(fh)
    for key in ("order_id", "assay", "samples"):
        if key not in order:
            raise ValueError("order %s missing required key: %s" % (path, key))
    if order["assay"] not in ASSAYS:
        raise ValueError("order %s: assay %r not in %s"
                         % (order["order_id"], order["assay"], sorted(ASSAYS)))
    if not isinstance(order["samples"], list) or not order["samples"]:
        raise ValueError("order %s: samples must be a non-empty list" % order["order_id"])
    for s in order["samples"]:
        if not s.get("sample_id"):
            raise ValueError("order %s: a sample row is missing sample_id" % order["order_id"])
    return order


def load_orders(paths):
    """Load several order records -> {order_id: order}; loud on duplicate order_id."""
    orders = {}
    for p in paths:
        o = load_order(p)
        if o["order_id"] in orders:
            raise ValueError("duplicate order_id %s" % o["order_id"])
        orders[o["order_id"]] = o
    return orders


def _sample_in_order(order, sample_id):
    for s in order["samples"]:
        if s["sample_id"] == sample_id:
            return s
    return None


def join(samplesheet_rows, orders):
    """Join sample-sheet rows with their orders -> [SampleJob]; loud on any mismatch.

    Phase 1 supports FAIS (single_primer) and WAIS with F&R primers. A WAIS row with no
    primers (insert-inference) is rejected here — that mode is deferred to M3 Phase 2."""
    jobs = []
    for row in samplesheet_rows:
        oid = row["order_id"]
        if oid not in orders:
            raise ValueError("samplesheet references unknown order_id %s (sample %s)"
                             % (oid, row["sample_id"]))
        order = orders[oid]
        s = _sample_in_order(order, row["sample_id"])
        if s is None:
            raise ValueError("sample %s not found in order %s" % (row["sample_id"], oid))
        assay = order["assay"]
        single = s.get("single_primer")
        pf, pr = s.get("primer_f"), s.get("primer_r")
        if assay == "FAIS":
            if not single:
                raise ValueError("FAIS sample %s (order %s) needs single_primer"
                                 % (s["sample_id"], oid))
        elif assay == "WAIS":
            if not (pf and pr):
                raise ValueError(
                    "WAIS sample %s (order %s) needs both primer_f and primer_r; "
                    "no-primer insert-inference is M3 Phase 2" % (s["sample_id"], oid))
        # PLASMID (tier 1): no primers — full circular consensus.
        jobs.append(SampleJob(
            barcode=row["barcode"], sample_id=row["sample_id"], order_id=oid, assay=assay,
            single_primer=single, primer_f=pf, primer_r=pr, size_kb=s.get("size_kb"),
            customer_primers=order.get("customer_primers", [])))
    return jobs
