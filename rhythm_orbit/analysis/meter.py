"""Weak accent-based meter evidence. This is not a downbeat transcription model."""
import numpy as np


def meter_candidate(envelope: np.ndarray, beat_frames: np.ndarray) -> dict:
    if len(beat_frames) < 16:
        return {"candidate": None, "reason": "Too few beats for meter evidence"}
    accents = envelope[np.clip(beat_frames.astype(int), 0, len(envelope) - 1)]
    scale = float(np.std(accents))
    if scale < 1e-6:
        return {"candidate": None, "reason": "No stable accent contrast"}
    scores = []
    for meter in (3, 4, 5, 7):
        bars = len(accents) // meter
        if bars < 4:
            continue
        values = accents[:bars * meter].reshape(bars, meter)
        profile = values.mean(axis=0)
        phase = int(np.argmax(profile))
        contrast = (profile[phase] - np.mean(np.delete(profile, phase))) / scale
        wins = float(np.mean(np.argmax(values, axis=1) == phase))
        score = max(0., min(1., float(contrast) / 3)) * wins
        scores.append((score, meter, phase))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < .35 or (len(scores) > 1 and scores[0][0] - scores[1][0] < .12):
        return {"candidate": None, "reason": "Accent evidence ambiguous"}
    score, meter, phase = scores[0]
    return {"candidate": f"{meter}/4", "downbeat_phase": phase, "score": score,
            "status": "inferred", "reason": "Repeated accent profile only; verify by listening"}
