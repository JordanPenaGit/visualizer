"""Map to a beat grid without moving the observed attacks."""
from bisect import bisect_right
from rhythm_orbit.models import RhythmEvent

SUBDIVISIONS = ((1, "1/4"), (2, "1/8"), (3, "1/8 triplet"), (4, "1/16"),
                (6, "1/16 triplet"), (8, "1/32"), (5, "quintuplet"), (7, "septuplet"))


def quantize(event: RhythmEvent, beats: list[float], meter: int) -> None:
    if len(beats) < 2 or event.timestamp < beats[0] or event.timestamp >= beats[-1]:
        event.subdivision = "outside tracked beat grid"
        return
    index = bisect_right(beats, event.timestamp) - 1
    span = beats[index + 1] - beats[index]
    phase = (event.timestamp - beats[index]) / span
    event.measure = index // meter + 1
    event.beat = index % meter + 1 + phase
    # Prefer simple grids, but preserve the residual timing in all cases.
    tolerance = min(0.045, span * 0.09)
    event.subdivision = "off-grid"
    best_offset = None
    for divisor, name in SUBDIVISIONS:
        offset = (phase - round(phase * divisor) / divisor) * span
        if best_offset is None or abs(offset) < abs(best_offset):
            best_offset = offset
        if abs(offset) <= tolerance:
            event.subdivision = name + " (nearest grid)"
            best_offset = offset
            break
    event.offset_ms = float(best_offset or 0) * 1000


def measure_boundaries(beats: list[float], duration: float, meter: int) -> list[float]:
    boundaries = beats[::meter]
    if not boundaries or boundaries[0] > 0.001:
        boundaries = [0.0] + boundaries
    boundaries = [v for v in boundaries if v < duration]
    return boundaries + [duration]
