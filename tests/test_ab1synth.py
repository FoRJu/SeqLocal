"""Unit tests for the AB1 synthesizer (python/ab1synth/).

Stdlib `unittest`. The authoritative round-trip check uses Biopython (the canonical ABIF
reader) and is skipped where it isn't installed; the structural + determinism checks use
the package's own stdlib reader and run everywhere.

    python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "python"))

from ab1synth import abif, synth                       # noqa: E402
from ab1synth.trace import SAMPLES_PER_BASE, BASE_ORDER  # noqa: E402

try:
    from Bio import SeqIO
    HAVE_BIO = True
except ImportError:
    HAVE_BIO = False


def comps_for(seq, support=40, noise=1):
    """Per-position (a,c,g,t) counts strongly supporting each consensus base."""
    idx = {b: i for i, b in enumerate("ACGT")}
    rows = []
    for b in seq:
        c = [noise, noise, noise, noise]
        if b in idx:
            c[idx[b]] = support
        rows.append(tuple(c))
    return rows


class TestAbif(unittest.TestCase):
    def test_write_read_roundtrip(self):
        tags = [
            abif.char_tag("PBAS", 2, b"ACGT"),
            abif.short_tag("PLOC", 2, [1, 2, 3, 4]),
            abif.char_tag("FWO_", 1, "ACGT"),          # 4 bytes -> inline
        ]
        d = abif.read_abif(abif.write_abif(tags))
        self.assertEqual(d[("PBAS", 2)], b"ACGT")
        self.assertEqual(d[("PLOC", 2)], (1, 2, 3, 4))
        self.assertEqual(d[("FWO_", 1)], b"ACGT")      # inline payload survived

    def test_marker_and_version(self):
        blob = abif.write_abif([abif.char_tag("PBAS", 2, b"AC")])
        self.assertEqual(blob[:4], b"ABIF")
        self.assertEqual(abif.read_abif(blob)["_version"], abif.ABIF_VERSION)

    def test_duplicate_tag_rejected(self):
        with self.assertRaises(ValueError):
            abif.write_abif([abif.char_tag("PBAS", 2, b"A"), abif.char_tag("PBAS", 2, b"C")])

    def test_short_range_checked(self):
        with self.assertRaises(ValueError):
            abif.short_tag("DATA", 1, [40000])         # out of int16 range


class TestSynth(unittest.TestCase):
    def setUp(self):
        self.seq = "ACGTACGTACGTAAGGCCTTACGTACGT"
        self.cons = synth.Consensus("amp", self.seq)
        self.comps = comps_for(self.seq)

    def _ab1(self, **kw):
        return synth.synthesize_ab1(self.cons, self.comps, **kw)

    def test_structural_tags_present(self):
        d = abif.read_abif(self._ab1()["ab1"])
        for key in [("PBAS", 2), ("PCON", 2), ("FWO_", 1), ("PLOC", 2)]:
            self.assertIn(key, d)
        for n in (9, 10, 11, 12):                      # analyzed channels
            self.assertIn(("DATA", n), d)
        self.assertEqual(d[("PBAS", 2)], self.seq.encode())
        self.assertEqual(d[("FWO_", 1)], BASE_ORDER.encode())
        # channel length == nbase * samples_per_base; PLOC has one entry per base
        self.assertEqual(len(d[("DATA", 9)]), len(self.seq) * SAMPLES_PER_BASE)
        self.assertEqual(len(d[("PLOC", 2)]), len(self.seq))

    def test_determinism_byte_identical(self):
        self.assertEqual(self._ab1()["ab1"], self._ab1()["ab1"])

    def test_window_extracts_subregion(self):
        r = self._ab1(window=(4, 12))
        self.assertEqual(r["region"], (4, 12))
        self.assertEqual(abif.read_abif(r["ab1"])[("PBAS", 2)], self.seq[4:12].encode())

    def test_max_len_hard_cutoff(self):
        r = self._ab1(window=(4, 28), max_len=6)
        self.assertEqual(r["region"], (4, 10))         # start + max_len

    def test_min_qual_truncates(self):
        # One weak base mid-sequence -> region truncates there under a high threshold.
        comps = comps_for(self.seq)
        comps[10] = (1, 1, 1, 1)                        # ~25% support -> low Phred
        r = synth.synthesize_ab1(self.cons, comps, min_qual=10)
        self.assertEqual(r["region"][1], 10)

    def test_fastq_consensus_uses_supplied_quals(self):
        cons = synth.Consensus("amp", "ACGT", quals=[30, 31, 32, 33])
        r = synth.synthesize_ab1(cons, comps_for("ACGT"))
        self.assertEqual(list(abif.read_abif(r["ab1"])[("PCON", 2)]), [30, 31, 32, 33])

    def test_loud_failures(self):
        with self.assertRaises(ValueError):                       # empty consensus
            synth.synthesize_ab1(synth.Consensus("x", ""), [])
        with self.assertRaises(ValueError):                       # length mismatch
            synth.synthesize_ab1(self.cons, self.comps[:-1])
        with self.assertRaises(ValueError):                       # non-ACGTN
            synth.synthesize_ab1(synth.Consensus("x", "ACXT"), comps_for("ACXT"))
        with self.assertRaises(ValueError):                       # window out of bounds
            self._ab1(window=(0, len(self.seq) + 5))

    @unittest.skipUnless(HAVE_BIO, "Biopython not installed")
    def test_biopython_roundtrip(self):
        import io
        r = self._ab1()
        rec = SeqIO.read(io.BytesIO(r["ab1"]), "abi")
        self.assertEqual(str(rec.seq), self.seq)
        pq = rec.letter_annotations["phred_quality"]
        self.assertEqual(len(pq), len(self.seq))
        self.assertTrue(all(0 <= q < 128 for q in pq))            # decode-safe

    @unittest.skipUnless(HAVE_BIO, "Biopython not installed")
    def test_biopython_roundtrip_window(self):
        import io
        r = self._ab1(window=(2, 20))
        rec = SeqIO.read(io.BytesIO(r["ab1"]), "abi")
        self.assertEqual(str(rec.seq), self.seq[2:20])


class TestParsing(unittest.TestCase):
    def test_read_counts_skips_header(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write("pos\tA\tC\tG\tT\n0\t10\t0\t0\t0\n1\t0\t9\t1\t0\n")
            path = fh.name
        rows = synth.read_counts(path)
        os.unlink(path)
        self.assertEqual(rows, [(10, 0, 0, 0), (0, 9, 1, 0)])

    def test_read_consensus_fastq(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".fq", delete=False) as fh:
            fh.write("@amp\nACGT\n+\nIIII\n")           # 'I' = Phred 40
            path = fh.name
        c = synth.read_consensus(path)
        os.unlink(path)
        self.assertEqual(c.seq, "ACGT")
        self.assertEqual(c.quals, [40, 40, 40, 40])


if __name__ == "__main__":
    unittest.main(verbosity=2)
