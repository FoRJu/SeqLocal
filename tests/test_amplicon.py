"""Unit tests for the amplicon tier logic (python/amplicon/).

Deterministic, stdlib `unittest`; no GPU/assembler. The end-to-end CLI test round-trips the
AB1 through Biopython where available (skipped otherwise).
"""
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "python"))

from amplicon import match, region, registry, orders        # noqa: E402
from amplicon.match import revcomp                            # noqa: E402
from amplicon.pileup import count_bases                       # noqa: E402

try:
    from Bio import SeqIO                                     # noqa: F401
    HAVE_BIO = True
except ImportError:
    HAVE_BIO = False

# Synthetic consensus: LEFT + Fprimer(+) + INSERT + revcomp(Rprimer)(=> R matches '-') + RIGHT
FP = "ACGTACGTAC"
RP = "TTTTGGGGCC"
INSERT = "AAATTTCCCGGGAAATTTCCC"
CONS = "GGGGG" + FP + INSERT + revcomp(RP) + "CCCCC"
#         0..4    5..14        15..35          36..45        46..50
FP_END = 5 + len(FP)            # 15
RP_START = FP_END + len(INSERT)  # 36


def write(path, text):
    with open(path, "w") as fh:
        fh.write(text)
    return path


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def counts_tsv(path, seq):
    idx = {b: i for i, b in enumerate("ACGT")}
    lines = ["pos\tA\tC\tG\tT"]
    for i, b in enumerate(seq):
        c = [1, 1, 1, 1]
        if b in idx:
            c[idx[b]] = 40
        lines.append("%d\t%d\t%d\t%d\t%d" % (i, c[0], c[1], c[2], c[3]))
    return write(path, "\n".join(lines) + "\n")


class TestMatch(unittest.TestCase):
    def test_forward_exact(self):
        h = match.find_primer(CONS, FP)
        self.assertEqual((h.start, h.end, h.strand, h.mismatches), (5, 15, "+", 0))

    def test_reverse_strand(self):
        h = match.find_primer(CONS, RP)               # revcomp(RP) is planted -> '-'
        self.assertEqual((h.start, h.end, h.strand, h.mismatches), (RP_START, RP_START + 10, "-", 0))

    def test_mismatch_tolerated_and_capped(self):
        primer = "ACGTACGTAC"
        cons = "TTTT" + "ACGTAAGTAC" + "TTTT"          # 1 mismatch at the planted site
        self.assertIsNotNone(match.find_primer(cons, primer, max_mismatch_frac=0.10))  # cap=1
        self.assertIsNone(match.find_primer(cons, primer, max_mismatch_frac=0.0))      # cap=0

    def test_iupac_primer(self):
        # R = A/G ; matches the A in the consensus.
        h = match.find_primer("TTTTACGTTTTT", "RCGT")
        self.assertIsNotNone(h)
        self.assertEqual(h.strand, "+")

    def test_not_found(self):
        self.assertIsNone(match.find_primer(CONS, "GGGGGGGGGGGGGGGGGG"))


class TestRegion(unittest.TestCase):
    def test_fais_forward_downstream(self):
        r = region.fais_region(CONS, FP, downstream=10)
        self.assertTrue(r.ok)
        self.assertEqual((r.start, r.end, r.revcomp), (FP_END, FP_END + 10, False))
        self.assertEqual(r.seq, CONS[FP_END:FP_END + 10])

    def test_fais_reverse_is_revcomped(self):
        r = region.fais_region(CONS, RP, downstream=10)   # RP matches '-'
        self.assertTrue(r.ok)
        self.assertEqual((r.start, r.end, r.revcomp), (RP_START - 10, RP_START, True))
        self.assertEqual(r.seq, revcomp(CONS[RP_START - 10:RP_START]))

    def test_fais_not_found(self):
        r = region.fais_region(CONS, "GGGGGGGGGGGGGGGG")
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "primer_not_found")
        self.assertIsNone(r.seq)

    def test_wais_between_primers(self):
        r = region.wais_region(CONS, FP, RP)
        self.assertTrue(r.ok)
        self.assertEqual((r.start, r.end, r.revcomp), (FP_END, RP_START, False))
        self.assertEqual(r.seq, INSERT)

    def test_wais_reverse_oriented_consensus(self):
        rc = revcomp(CONS)
        r = region.wais_region(rc, FP, RP)               # now F matches '-', R matches '+'
        self.assertTrue(r.ok)
        self.assertTrue(r.revcomp)
        self.assertEqual(r.seq, INSERT)                  # recovered in forward orientation

    def test_wais_primer_not_found(self):
        r = region.wais_region(CONS, FP, "GGGGGGGGGGGGGGGG")
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "primer_not_found")
        self.assertIn("reverse", r.message)

    def test_wais_same_strand_orientation_fail(self):
        # Two primers that both match the '+' strand -> orientation error.
        r = region.wais_region(CONS, FP, "GGGGG")
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "primer_orientation")

    def test_orient_counts_revcomp(self):
        counts = [(1, 2, 3, 4), (5, 6, 7, 8)]            # (A,C,G,T) rows
        out = region.orient_counts(counts, 0, 2, True)
        # reversed + complement: row2 -> (T,G,C,A)=(8,7,6,5); row1 -> (4,3,2,1)
        self.assertEqual(out, [(8, 7, 6, 5), (4, 3, 2, 1)])


class TestPileup(unittest.TestCase):
    def test_match_symbols_resolve_to_ref(self):
        self.assertEqual(count_bases("..,", "A"), {"A": 3, "C": 0, "G": 0, "T": 0})

    def test_markers_and_indels_skipped(self):
        # ^I<.> read-start+match, C mismatch, +2AA insertion skipped, g mismatch, $ end
        self.assertEqual(count_bases("..,^I.C+2AAg$", "A"), {"A": 4, "C": 1, "G": 1, "T": 0})
        # '*' gap skipped, -1N deletion skipped, '.' resolves to ref T
        self.assertEqual(count_bases("A*-1N.", "T"), {"A": 1, "C": 0, "G": 0, "T": 1})


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.csv = write(os.path.join(self.d, "primers.csv"),
                         "name,sequence,notes\nLucy-F,ACGTACGT,ok\nEmpty-P,,todo\n")

    def test_resolve_ok(self):
        r = registry.load_registry(self.csv)
        self.assertEqual(registry.resolve("Lucy-F", r), "ACGTACGT")

    def test_unknown_and_blank_are_loud(self):
        r = registry.load_registry(self.csv)
        with self.assertRaises(KeyError):
            registry.resolve("Nope", r)
        with self.assertRaises(ValueError):
            registry.resolve("Empty-P", r)               # present but blank

    def test_customer_override(self):
        r = registry.merge_customer(registry.load_registry(self.csv),
                                    [{"name": "Lucy-F", "sequence": "tttt"}])
        self.assertEqual(registry.resolve("Lucy-F", r), "TTTT")


class TestOrders(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.ss = write(os.path.join(self.d, "ss.csv"),
                        "barcode,sample_id,order_id\nbarcode01,BH_1,7340110\nbarcode02,SAC001,7340118\n")
        write(os.path.join(self.d, "fais.json"), json.dumps({
            "order_id": "7340110", "assay": "FAIS",
            "samples": [{"sample_id": "BH_1", "single_primer": "Lucy-F"}]}))
        write(os.path.join(self.d, "wais.json"), json.dumps({
            "order_id": "7340118", "assay": "WAIS",
            "samples": [{"sample_id": "SAC001", "primer_f": "NA-3", "primer_r": "HA-Rev"}]}))
        self.orders = orders.load_orders([os.path.join(self.d, "fais.json"),
                                          os.path.join(self.d, "wais.json")])

    def test_join_fais_and_wais(self):
        jobs = orders.join(orders.load_samplesheet(self.ss), self.orders)
        by_bc = {j.barcode: j for j in jobs}
        self.assertEqual(by_bc["barcode01"].assay, "FAIS")
        self.assertEqual(by_bc["barcode01"].single_primer, "Lucy-F")
        self.assertEqual((by_bc["barcode02"].primer_f, by_bc["barcode02"].primer_r), ("NA-3", "HA-Rev"))

    def test_unknown_order_is_loud(self):
        ss = write(os.path.join(self.d, "bad.csv"),
                   "barcode,sample_id,order_id\nbarcode01,BH_1,9999999\n")
        with self.assertRaises(ValueError):
            orders.join(orders.load_samplesheet(ss), self.orders)

    def test_wais_without_primers_rejected(self):
        write(os.path.join(self.d, "noprimer.json"), json.dumps({
            "order_id": "7340073", "assay": "WAIS",
            "samples": [{"sample_id": "ZHC001"}]}))
        ss = write(os.path.join(self.d, "ip.csv"),
                   "barcode,sample_id,order_id\nbarcode03,ZHC001,7340073\n")
        o = orders.load_orders([os.path.join(self.d, "noprimer.json")])
        with self.assertRaises(ValueError):
            orders.join(orders.load_samplesheet(ss), o)


class TestCliEndToEnd(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cons = write(os.path.join(self.d, "c.fa"), ">cons\n" + CONS + "\n")
        self.counts = counts_tsv(os.path.join(self.d, "p.tsv"), CONS)
        self.primers = write(os.path.join(self.d, "primers.csv"),
                             "name,sequence,notes\nNA-3,%s,f\nHA-Rev,%s,r\n" % (FP, RP))
        self.ss = write(os.path.join(self.d, "ss.csv"),
                        "barcode,sample_id,order_id\nbarcode01,SAC001,7340118\n")
        self.order = write(os.path.join(self.d, "o.json"), json.dumps({
            "order_id": "7340118", "assay": "WAIS",
            "samples": [{"sample_id": "SAC001", "primer_f": "NA-3", "primer_r": "HA-Rev"}]}))

    def _run(self, out):
        from amplicon.cli import main
        main(["--barcode", "barcode01", "--consensus", self.cons, "--counts", self.counts,
              "--samplesheet", self.ss, "--order", self.order, "--primers", self.primers,
              "--out", out])

    def test_wais_emits_ab1_and_qc(self):
        out = os.path.join(self.d, "SAC001")
        self._run(out)
        qc = load_json(out + ".qc.json")
        self.assertEqual(qc["status"], "ok")
        self.assertEqual(qc["region"]["length"], len(INSERT))
        self.assertTrue(os.path.exists(out + ".ab1"))

    @unittest.skipUnless(HAVE_BIO, "Biopython not installed")
    def test_ab1_region_matches_insert(self):
        out = os.path.join(self.d, "SAC001")
        self._run(out)
        import io
        rec = SeqIO.read(io.BytesIO(read_bytes(out + ".ab1")), "abi")
        self.assertEqual(str(rec.seq), INSERT)

    def test_primer_not_found_writes_qc_no_ab1(self):
        primers = write(os.path.join(self.d, "bad.csv"),
                        "name,sequence,notes\nNA-3,%s,f\nHA-Rev,%s,r\n" % (FP, "GGGGGGGGGGGGGGGG"))
        out = os.path.join(self.d, "fail")
        from amplicon.cli import main
        main(["--barcode", "barcode01", "--consensus", self.cons, "--counts", self.counts,
              "--samplesheet", self.ss, "--order", self.order, "--primers", primers, "--out", out])
        qc = load_json(out + ".qc.json")
        self.assertEqual(qc["status"], "primer_not_found")
        self.assertFalse(os.path.exists(out + ".ab1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
