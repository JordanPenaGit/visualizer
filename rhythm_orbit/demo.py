"""An explicitly labeled, deterministic 3:4 fixture with matching synthesized audio."""
from pathlib import Path
import numpy as np
import soundfile as sf
from rhythm_orbit.models import InstrumentTrack, RhythmEvent, SongAnalysis
from rhythm_orbit.analysis.quantization import quantize
from rhythm_orbit.analysis.patterns import find_patterns
from rhythm_orbit.cache import cache_root


def create_demo() -> SongAnalysis:
    sr, tempo, measures = 22050, 120, 16
    bar = 2.0
    duration = measures * bar
    source = cache_root() / "demo-3-against-4-v1.wav"
    spec = [("Hi-hat", "#70dcc8", [i / 4 for i in range(8)], 6500),
            ("Kick", "#ffae75", [0, .5, 1, 1.5], 60),
            ("Snare", "#b29bff", [.5, 1.5], 190),
            ("Three-pulse clave", "#e1cd80", [0, 2 / 3, 4 / 3], 1600),
            ("Bass", "#f08bb5", [0, 1], 110)]
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    beats = [i * .5 for i in range(measures * 4 + 1)]
    boundaries = [i * bar for i in range(measures + 1)]
    tracks = []
    for name, color, offsets, frequency in spec:
        events = []
        for measure in range(measures):
            for offset in offsets:
                timestamp = measure * bar + offset
                event = RhythmEvent(timestamp, name, .85, 1.0, "demo")
                quantize(event, beats, 4)
                events.append(event)
                t = np.arange(int(sr * .13)) / sr
                tone = np.sin(2 * np.pi * frequency * t) * np.exp(-t * (55 if frequency > 1000 else 25))
                start = round(timestamp * sr)
                end = min(len(audio), start + len(tone))
                audio[start:end] += (0.16 * tone[:end - start]).astype(np.float32)
        tracks.append(InstrumentTrack(name, color, events, 1.0))
    if not source.is_file():
        sf.write(source, audio, sr)
    return SongAnalysis("Three against four", str(source), duration, tempo, beats, boundaries, tracks,
                        meter_status="4/4 · authored demo", rhythmic_patterns=find_patterns(tracks, boundaries),
                        demo=True, warnings=["Synthesized demonstration. Events are authored, not detected from a song."])
