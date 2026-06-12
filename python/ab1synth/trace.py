"""Synthesize four ABIF trace channels from per-position base composition.

ONT has no fluorescence, so the chromatogram is built from the read pileup: at each
consensus position the A/C/G/T proportions become the four channel intensities at that
base's peak. Peaks sit on an evenly spaced grid and are rendered as fixed-width Gaussians
summed into the channels — a synthetic but well-formed trace that Sanger viewers display.

Deterministic: fixed constants, no RNG, integer output. Same composition in → same trace.
"""
import math

# Channel/base order. MUST match the FWO_ tag written by the synthesizer.
BASE_ORDER = "ACGT"

# Trace geometry (fixed for determinism + a clean, viewer-friendly chromatogram).
SAMPLES_PER_BASE = 12     # grid spacing between peak centers
PEAK_SIGMA = 2.2          # Gaussian width (samples); ~half-overlap with neighbors
PEAK_AMPLITUDE = 1000     # channel intensity at proportion 1.0 (well within int16)
_GAUSS_RADIUS = int(math.ceil(4 * PEAK_SIGMA))   # truncate the Gaussian past this
_INT16_MAX = 32767


def peak_locations(nbase):
    """Peak (base-call) x-position for each of `nbase` positions, in trace samples."""
    half = SAMPLES_PER_BASE // 2
    return [i * SAMPLES_PER_BASE + half for i in range(nbase)]


def synthesize(compositions, consensus):
    """Build the four trace channels + peak locations.

    Args:
      compositions: list of (a, c, g, t) raw counts, one per consensus position.
      consensus:    consensus bases (str), same length as `compositions`. Used as the
                    fallback peak at zero-coverage positions so the called base still shows.

    Returns (channels, ploc):
      channels: dict base -> list[int] (one int16 series per base in BASE_ORDER)
      ploc:     list[int] peak center positions (len == nbase)
    """
    nbase = len(consensus)
    if len(compositions) != nbase:
        raise ValueError(
            "compositions/consensus length mismatch: %d vs %d" % (len(compositions), nbase))

    ploc = peak_locations(nbase)
    ntrace = nbase * SAMPLES_PER_BASE if nbase else 0
    channels = {b: [0] * ntrace for b in BASE_ORDER}

    for i, base in enumerate(consensus):
        amps = _channel_amplitudes(compositions[i], base)
        center = ploc[i]
        for b, amp in amps.items():
            if amp <= 0:
                continue
            _add_gaussian(channels[b], center, amp, ntrace)

    # Clip to int16 where overlapping tails summed past the max.
    for b in channels:
        ch = channels[b]
        for j in range(len(ch)):
            if ch[j] > _INT16_MAX:
                ch[j] = _INT16_MAX
    return channels, ploc


def _channel_amplitudes(counts, base):
    """Per-channel peak amplitude for one position from (a,c,g,t) counts.

    Zero coverage falls back to a full-amplitude peak on the consensus base (deterministic),
    so a called base is never rendered as a flat/blank trace."""
    total = sum(counts)
    if total <= 0:
        amps = {b: 0 for b in BASE_ORDER}
        if base in amps:
            amps[base] = PEAK_AMPLITUDE
        return amps
    return {
        b: int(round(PEAK_AMPLITUDE * counts[idx] / total))
        for idx, b in enumerate(BASE_ORDER)
    }


def _add_gaussian(channel, center, amp, ntrace):
    """Add a truncated Gaussian of height `amp` centered at `center` into `channel`."""
    lo = max(0, center - _GAUSS_RADIUS)
    hi = min(ntrace - 1, center + _GAUSS_RADIUS)
    inv = 1.0 / (2.0 * PEAK_SIGMA * PEAK_SIGMA)
    for x in range(lo, hi + 1):
        d = x - center
        channel[x] += int(round(amp * math.exp(-(d * d) * inv)))
