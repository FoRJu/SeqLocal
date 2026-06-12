"""amplicon — order-driven primer matching + region extraction for the amplicon tier (M3).

Resolves named primers (registry.py), locates them in a consensus (match.py), and extracts
the FAIS/WAIS window (region.py) that python/ab1synth renders to an .ab1. Orders/sample
sheet intake in orders.py. Deterministic; the consensus is produced upstream (M3 Phase 2).
"""
__version__ = "0.1.0"

from .match import find_primer, revcomp                          # noqa: F401
from .region import fais_region, wais_region, orient_counts      # noqa: F401
from .registry import load_registry, merge_customer, resolve     # noqa: F401
from .orders import load_samplesheet, load_orders, join, SampleJob  # noqa: F401
