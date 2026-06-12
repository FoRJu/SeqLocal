"""ab1synth — synthesize Sanger-compatible .ab1 chromatograms from ONT consensus + pileup.

Bespoke ABIF binary writer (Biopython reads ABIF but cannot write it). See abif.py for the
encoder, trace.py for channel synthesis, synth.py for orchestration, cli.py for the CLI.
"""
__version__ = "0.1.0"

from .abif import write_abif, read_abif          # noqa: F401
from .synth import synthesize_ab1, read_consensus, read_counts, Consensus  # noqa: F401
