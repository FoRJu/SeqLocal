"""Unit tests for the run-manifest emitter (python/provenance/manifest.py).

Stdlib `unittest` only — no new dependency, runs on the Mac's system python3.
    python3 -m unittest discover -s tests        # or: python3 tests/test_manifest.py
Covers: sha256 correctness, stage/header/merge assembly, schema validation, the
failed-stage halt rule, and byte-for-byte determinism (the CLAUDE.md requirement).
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

# Import the package from python/ without installing it.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "python"))

from provenance import manifest as m  # noqa: E402


def write(path, data=b"x"):
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def load(path):
    with open(path) as fh:
        return json.load(fh)


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class TestHashing(unittest.TestCase):
    def test_sha256_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(os.path.join(d, "f"), b"hello world")
            self.assertEqual(m.sha256(p), hashlib.sha256(b"hello world").hexdigest())

    def test_infer_format_handles_gz(self):
        self.assertEqual(m._infer_format("x/y.fastq.gz"), "fastq")
        self.assertEqual(m._infer_format("a.ab1"), "ab1")
        self.assertEqual(m._infer_format("a.unknownext"), "other")


class TestCli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.pod5 = write(os.path.join(self.d, "in.pod5"), b"pod5data")
        self.bam = write(os.path.join(self.d, "calls.bam"), b"bamdata")

    def _stage(self, out, status="ok", started="2026-06-11T00:00:00Z"):
        m.main([
            "stage", "--name", "basecall", "--tool", "dorado",
            "--tool-version", "2.0.0", "--model", "hac@v6.0",
            "--param", "device=cuda:0", "--input", self.pod5,
            "--output", self.bam, "--started", started,
            "--finished", "2026-06-11T00:01:00Z", "--status", status,
            "--out", out,
        ])

    def _header(self, out):
        m.main([
            "header", "--run-id", "r1", "--sample-id", "barcode01",
            "--operator", "bfxsvc", "--git-commit", "abc1234",
            "--code-sha256", "deadbeef", "--code-hash-verified", "false",
            "--kill-flag-present", "false",
            "--created-utc", "2026-06-11T00:00:00Z", "--out", out,
        ])

    def test_stage_hashes_inputs_and_outputs(self):
        out = os.path.join(self.d, "s.json")
        self._stage(out)
        block = load(out)
        self.assertEqual(block["inputs"][0]["sha256"], m.sha256(self.pod5))
        self.assertEqual(block["outputs"][0]["sha256"], m.sha256(self.bam))
        self.assertEqual(block["params"], {"device": "cuda:0"})

    def test_merge_produces_valid_manifest(self):
        hdr = os.path.join(self.d, "h.json")
        stg = os.path.join(self.d, "s.json")
        out = os.path.join(self.d, "run-manifest.json")
        self._header(hdr)
        self._stage(stg)
        m.main(["merge", "--header", hdr, "--stage", stg,
                "--deliverable", self.bam, "--out", out])
        man = load(out)
        m.validate(man)  # raises SystemExit on any violation
        self.assertEqual(len(man["stages"]), 1)
        self.assertEqual(man["deliverables"][0]["format"], "bam")
        self.assertEqual(man["operator"], "bfxsvc")

    def test_failed_stage_halts_merge(self):
        hdr = os.path.join(self.d, "h.json")
        stg = os.path.join(self.d, "s.json")
        out = os.path.join(self.d, "run-manifest.json")
        self._header(hdr)
        self._stage(stg, status="failed")
        with self.assertRaises(SystemExit):
            m.main(["merge", "--header", hdr, "--stage", stg, "--out", out])

    def test_validate_rejects_bad_service_tier(self):
        hdr = os.path.join(self.d, "h.json")
        self._header(hdr)
        man = load(hdr)
        man["service_tier"] = "not_a_tier"
        with self.assertRaises(SystemExit):
            m.validate(man)

    def test_merge_is_byte_deterministic(self):
        # Same inputs + pinned timestamps -> byte-identical manifest on repeat runs.
        hdr = os.path.join(self.d, "h.json")
        stg = os.path.join(self.d, "s.json")
        self._header(hdr)
        self._stage(stg)
        a = os.path.join(self.d, "a.json")
        b = os.path.join(self.d, "b.json")
        m.main(["merge", "--header", hdr, "--stage", stg,
                "--deliverable", self.bam, "--out", a])
        m.main(["merge", "--header", hdr, "--stage", stg,
                "--deliverable", self.bam, "--out", b])
        self.assertEqual(read_bytes(a), read_bytes(b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
