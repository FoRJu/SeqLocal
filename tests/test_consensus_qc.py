"""Unit tests for the M4 per-base QC + the PLASMID assay (Mac-runnable parts of M4).

The assembly/polish stages are Linux/GPU and validated on the box; here we cover the
deterministic Python: per-base quality FASTQ from pileup counts, and the PLASMID order join.
"""
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "python"))

from amplicon import qc, orders                              # noqa: E402


def comps_for(seq, support=40, noise=1):
    idx = {b: i for i, b in enumerate("ACGT")}
    rows = []
    for b in seq:
        c = [noise, noise, noise, noise]
        if b in idx:
            c[idx[b]] = support
        rows.append(tuple(c))
    return rows


class TestPerBaseQC(unittest.TestCase):
    def test_fastq_shape_and_length(self):
        seq = "ACGTACGTAA"
        fq = qc.consensus_to_qc_fastq(seq, comps_for(seq), "cons")
        lines = fq.splitlines()
        self.assertEqual(lines[0], "@cons")
        self.assertEqual(lines[1], seq)
        self.assertEqual(lines[2], "+")
        self.assertEqual(len(lines[3]), len(seq))            # one qual char per base

    def test_quality_tracks_support(self):
        # Strong support -> high Q; zero coverage -> Q0.
        strong = qc.derive_quality((40, 1, 1, 1), "A")
        weak = qc.derive_quality((1, 1, 1, 1), "A")
        none = qc.derive_quality((0, 0, 0, 0), "A")
        self.assertGreater(strong, weak)
        self.assertEqual(none, 0)
        self.assertLessEqual(strong, qc.QUAL_MAX)

    def test_determinism(self):
        seq = "ACGTACGTAA"
        c = comps_for(seq)
        self.assertEqual(qc.consensus_to_qc_fastq(seq, c, "x"),
                         qc.consensus_to_qc_fastq(seq, c, "x"))

    def test_length_mismatch_is_loud(self):
        with self.assertRaises(ValueError):
            qc.consensus_to_qc_fastq("ACGT", comps_for("ACG"), "x")


class TestPlasmidAssay(unittest.TestCase):
    """Real 'Whole Plasmid Sequencing' order CSVs route to the PLASMID tier, no primers."""
    SHEET = os.path.join(REPO, "assets/test/aa051826a.samplesheet.tsv")
    ORDERS = [os.path.join(REPO, "assets/test/orders/Order_7340017.csv"),
              os.path.join(REPO, "assets/test/orders/Order_7340018.csv")]

    def test_plasmid_join_needs_no_primers(self):
        jobs = orders.join(orders.load_samplesheet(self.SHEET), orders.load_orders(self.ORDERS))
        plz = next(j for j in jobs if j.barcode == "barcode41")
        self.assertEqual(plz.assay, "PLASMID")
        self.assertEqual((plz.sample_id, plz.dna_name), ("DO001", "A03_1"))
        self.assertIsNone(plz.single_primer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
