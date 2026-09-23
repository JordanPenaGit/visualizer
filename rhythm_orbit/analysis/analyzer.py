from __future__ import annotations
from pathlib import Path
from collections.abc import Callable
import numpy as np
from rhythm_orbit.models import SongAnalysis, InstrumentTrack, RhythmEvent
from rhythm_orbit.cache import AnalysisCache, audio_hash, cache_root
from rhythm_orbit.analysis.quantization import quantize, measure_boundaries
from rhythm_orbit.analysis.patterns import find_patterns
from rhythm_orbit.analysis.meter import meter_candidate

COLORS = {"Hi-hat candidate": "#70dcc8", "Kick candidate": "#ffae75", "Snare candidate": "#b29bff",
          "Percussion (unclassified)": "#8ca7c7", "Bass": "#f08bb5", "Vocals": "#e1cd80", "Other": "#83b5ee",
          "Mix onsets": "#70dcc8"}


def onset_events(y: np.ndarray, sr: int, name: str, drums: bool = False) -> list[RhythmEvent]:
    import librosa
    hop = 256
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop)
    scale = float(np.percentile(env[env > 0], 95)) if np.any(env > 0) else 1.0
    events = []
    for frame in frames:
        timestamp = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        strength = float(np.clip(env[frame] / max(scale, 1e-9), 0, 1))
        label, confidence, status = name, min(0.9, 0.4 + 0.5 * strength), "detected"
        if confidence < .6:
            status = "uncertain"
        if drums:
            # Broad-band heuristics only. Overlapping hits cannot be reliably split.
            start = max(0, int(timestamp * sr) - hop)
            sample = y[start:start + int(0.08 * sr)]
            if len(sample) < 16:
                continue
            spectrum = np.abs(np.fft.rfft(sample * np.hanning(len(sample)))) ** 2
            frequencies = np.fft.rfftfreq(len(sample), 1 / sr)
            total = float(spectrum.sum()) + 1e-12
            low = float(spectrum[frequencies < 180].sum()) / total
            mid = float(spectrum[(frequencies >= 180) & (frequencies < 3500)].sum()) / total
            high = float(spectrum[frequencies >= 5000].sum()) / total
            label, confidence, status = "Percussion (unclassified)", 0.3, "uncertain"
            if low > 0.7:
                label, confidence = "Kick candidate", 0.55 + 0.2 * low
            elif high > 0.65:
                label, confidence = "Hi-hat candidate", 0.5 + 0.2 * high
            elif mid > 0.65 and high > 0.12:
                label, confidence = "Snare candidate", 0.5 + 0.15 * mid
            if "candidate" in label:
                status = "inferred"
        events.append(RhythmEvent(timestamp, label, strength, confidence, status))
    return events


def analyze(path: Path, meter: int = 4, use_separation: bool = False,
            progress: Callable[[int, str], None] = lambda *_: None,
            cancelled: Callable[[], bool] = lambda: False, force: bool = False) -> SongAnalysis:
    import librosa

    def stage(percent: int, message: str) -> None:
        if cancelled():
            raise InterruptedError("Analysis cancelled")
        progress(percent, message)

    if meter not in (3, 4, 5, 7):
        raise ValueError("Choose 3, 4, 5, or 7 quarter-note beats per measure")
    stage(2, "Checking audio cache…")
    digest = audio_hash(path)
    cache = AnalysisCache()
    cached = None if force else cache.load(digest, meter, use_separation)
    if cached:
        cached.source = str(path.resolve())
        cached.title = path.stem
        stage(100, "Restored cached analysis")
        return cached
    stage(8, "Loading audio…")
    y, sr = librosa.load(path, sr=22050, mono=True)
    duration = len(y) / sr
    if duration < 1 or not np.all(np.isfinite(y)):
        raise ValueError("Please choose a valid audio file at least one second long")
    warnings = ["Meter is the selected grouping; the first tracked beat is only an assumed downbeat.",
                "Confidence values are heuristic scores, not calibrated probabilities."]
    stage(18, "Detecting tempo and beats…")
    if np.max(np.abs(y)) < 1e-5:
        raise ValueError("This file is silent; no reliable rhythmic events can be detected")
    envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    tempo, frames = librosa.beat.beat_track(onset_envelope=envelope, sr=sr, hop_length=256, trim=False)
    tempo = float(np.asarray(tempo).reshape(-1)[0])
    meter_evidence = meter_candidate(envelope, frames)
    if meter_evidence["candidate"]:
        warnings.append(f"Accent-based meter candidate: {meter_evidence['candidate']}; selected grouping retained. Verify by listening.")
    beats = [float(t) for t in librosa.frames_to_time(frames, sr=sr, hop_length=256) if t < duration]
    if len(beats) < 2 or tempo <= 0:
        raise ValueError("A stable beat grid could not be found. Try a longer, more percussive recording")
    # A final extrapolated grid point maps the tail; it is not an observed beat.
    step = float(np.median(np.diff(beats)))
    while beats[-1] < duration:
        beats.append(beats[-1] + step)
    boundaries = measure_boundaries(beats, duration, meter)
    tracks: list[InstrumentTrack] = []
    stems: dict[str, Path] = {}
    if use_separation:
        from rhythm_orbit.separation.demucs_runner import separate
        stage(30, "Separating stems… first run may download the Demucs model")
        stems = separate(path, cache_root() / "stems" / digest, cancelled)
        for index, (name, stem) in enumerate(stems.items()):
            stage(55 + index * 8, f"Analyzing {name}…")
            stem_y, _ = librosa.load(stem, sr=sr, mono=True)
            events = onset_events(stem_y, sr, name.title(), drums=name == "drums")
            labels = sorted({e.instrument for e in events}) or ["Percussion (unclassified)" if name == "drums" else name.title()]
            for label in labels:
                group = [e for e in events if e.instrument == label]
                tracks.append(InstrumentTrack(label, COLORS.get(label, "#83b5ee"), group,
                                              float(np.mean([e.confidence for e in group])) if group else 0, str(stem)))
        warnings.append("Drum labels are spectral candidates. Cymbals, toms and overlapping hits may remain unclassified.")
    else:
        stage(50, "Detecting attacks in the full mix…")
        events = onset_events(y, sr, "Mix onsets")
        tracks.append(InstrumentTrack("Mix onsets", COLORS["Mix onsets"], events,
                                      float(np.mean([e.confidence for e in events])) if events else 0))
        warnings.append("Full-mix attacks are not instrument identifications. Enable Demucs to analyze separated layers.")
    stage(88, "Mapping events to the beat grid…")
    for track in tracks:
        for event in track.events:
            quantize(event, beats, meter)
    stage(94, "Finding repeating patterns…")
    patterns = find_patterns(tracks, boundaries)
    result = SongAnalysis(path.stem, str(path.resolve()), duration, tempo, beats, boundaries, tracks,
                          meter=meter, rhythmic_patterns=patterns, warnings=warnings, audio_hash=digest,
                          metadata={"meter_evidence": meter_evidence, "stems": {name: str(p) for name, p in stems.items()},
                                    "beat_method": "librosa dynamic-programming estimate; tail extrapolated",
                                    "downbeats": [b for b in beats[::meter] if b < duration],
                                    "downbeat_status": "inferred from selected grouping"})
    cache.save(result, use_separation)
    stage(100, "Analysis ready")
    return result
