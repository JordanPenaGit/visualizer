"""Conservative multi-bar repetition and evenly spaced pulse candidates."""
from math import gcd
import numpy as np
from rhythm_orbit.models import InstrumentTrack, RhythmicPattern


def find_patterns(tracks: list[InstrumentTrack], boundaries: list[float]) -> list[RhythmicPattern]:
    results: list[RhythmicPattern] = []
    for track in tracks:
        times = np.array([e.timestamp for e in track.events])
        for i in range(len(boundaries) - 3):
            windows = []
            for j in range(i, i + 3):
                a, b = boundaries[j:j + 2]
                windows.append((times[(times >= a) & (times < b)] - a) / (b - a))
            n = len(windows[0])
            if n < 2 or n > 32 or any(len(w) != n for w in windows):
                continue
            error = max(float(np.max(np.abs(w - windows[0]))) for w in windows[1:])
            if error > 0.045:
                continue
            gaps = np.diff(np.r_[windows[0], windows[0][0] + 1])
            regular = bool(np.max(np.abs(gaps - 1 / n)) < min(0.04, 0.25 / n))
            results.append(RhythmicPattern(track.name, boundaries[i], boundaries[i + 3], n,
                                            max(0.0, 1 - error / 0.045),
                                            "Even pulse candidate across 3 measures" if regular else "Repeating onset pattern across 3 measures"))
            break
    regulars = [p for p in results if p.description.startswith("Even")]
    for i, p in enumerate(regulars):
        for q in regulars[i + 1:]:
            if abs(p.start_time - q.start_time) > 0.01 or abs(p.end_time - q.end_time) > 0.01:
                continue
            divisor = gcd(p.pulse_count, q.pulse_count)
            a, b = p.pulse_count // divisor, q.pulse_count // divisor
            if min(a, b) > 1:
                results.append(RhythmicPattern(f"{p.instrument} × {q.instrument}", p.start_time,
                    p.end_time, p.pulse_count, min(p.confidence, q.confidence),
                    "Possible polyrhythm; pulse ratio is not a meter estimate", f"{a}:{b}"))
    return results
