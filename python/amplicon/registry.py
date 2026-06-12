"""Primer registry — resolve a named primer to its sequence (two-tier, loud).

Repo-level `assets/primers.csv` provides the lab's standing primers; an order's
`customer_primers[]` override/extend them. A name with no resolvable IUPAC sequence
(unknown, or a registry row left blank) raises — never silently skipped.
"""

# IUPAC nucleotide codes allowed in a primer sequence.
IUPAC = set("ACGTRYSWKMBDHVN")


def load_registry(csv_path):
    """Parse assets/primers.csv (`name,sequence,notes`; '#' comments) -> {name: seq}.

    Blank sequences are kept (value "") so resolve() can fail loud with a useful message
    rather than the name simply being absent."""
    reg = {}
    with open(csv_path) as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(",")
            name = parts[0].strip()
            if name.lower() == "name":            # header
                continue
            seq = (parts[1].strip().upper() if len(parts) > 1 else "")
            reg[name] = seq
    return reg


def merge_customer(registry, customer_primers):
    """Return a new registry with customer primers overriding/extending the repo registry."""
    merged = dict(registry)
    for p in (customer_primers or []):
        merged[p["name"]] = p["sequence"].strip().upper()
    return merged


def resolve(name, registry):
    """Name -> uppercase IUPAC sequence. Raises (loud) on unknown / blank / non-IUPAC."""
    if name not in registry:
        raise KeyError("primer %r not in registry or customer_primers" % name)
    seq = registry[name]
    if not seq:
        raise ValueError("primer %r has no sequence (fill assets/primers.csv or supply it "
                         "as a customer primer)" % name)
    bad = set(seq) - IUPAC
    if bad:
        raise ValueError("primer %r has non-IUPAC characters: %s" % (name, sorted(bad)))
    return seq
