import math
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from rhythm_orbit.models import RhythmEvent, InstrumentTrack, SongAnalysis
from rhythm_orbit.analysis.quantization import quantize, measure_boundaries
from rhythm_orbit.analysis.patterns import find_patterns
from rhythm_orbit.cache import AnalysisCache, audio_hash
from rhythm_orbit.spotify.client import track_id


def test_quantization_preserves_swing_and_offsets():
    beats = [i * .5 for i in range(17)]
    event = RhythmEvent(.347, "hat", .8, .7)
    quantize(event, beats, 4)
    assert event.timestamp == .347
    assert event.measure == 1
    assert event.beat == pytest.approx(1.694)
    assert "triplet" in event.subdivision
    assert event.offset_ms == pytest.approx(13.6666667)


def test_measure_boundary_and_tempo_change():
    beats = [0, .5, 1, 1.5, 2, 2.4, 2.8, 3.2, 3.6]
    event = RhythmEvent(2.2, "kick", .9, .8)
    quantize(event, beats, 4)
    assert event.measure == 2 and event.beat == pytest.approx(1.5)
    assert event.offset_ms == pytest.approx(0)
    assert measure_boundaries(beats, 3.6, 4) == [0, 2, 3.6]


def test_pickup_and_unmapped_tail():
    beats = [.2, .7, 1.2, 1.7, 2.2]
    event = RhythmEvent(.1, "mix", .8, .5)
    quantize(event, beats, 4)
    assert event.measure == 0 and "outside" in event.subdivision
    event = RhythmEvent(2.5, "mix", .8, .5)
    quantize(event, beats, 4)
    assert event.measure == 0
    assert measure_boundaries(beats, 2.5, 4) == [0, .2, 2.2, 2.5]


def track(pulses, name):
    return InstrumentTrack(name, "#fff", [RhythmEvent(bar * 2 + i * 2 / pulses, name, 1, 1) for bar in range(4) for i in range(pulses)])


def test_repeated_3_against_4_is_candidate_not_meter():
    patterns = find_patterns([track(3, "three"), track(4, "four")], [0, 2, 4, 6, 8])
    ratios = [p for p in patterns if p.ratio]
    assert len(ratios) == 1 and ratios[0].ratio == "3:4"
    assert ratios[0].status == "inferred"
    assert "not a meter" in ratios[0].description


def test_straight_subdivision_is_not_polyrhythm():
    assert not any(p.ratio for p in find_patterns([track(4, "kick"), track(8, "hat")], [0, 2, 4, 6, 8]))


def test_single_measure_does_not_claim_repetition():
    assert find_patterns([track(3, "three")], [0, 2]) == []


def test_cache_roundtrip_invalidation_and_corrupt_file(tmp_path):
    cache = AnalysisCache(tmp_path)
    result = SongAnalysis("Song", "/song.wav", 2, 120, [0, .5, 1, 1.5, 2], [0, 2], [track(4, "kick")], audio_hash="a" * 64)
    cache.save(result, False)
    assert cache.load(result.audio_hash, 4, False).to_dict() == result.to_dict()
    assert cache.load(result.audio_hash, 3, False) is None
    assert cache.load(result.audio_hash, 4, True) is None
    cache.path(result.audio_hash, 4, False).write_text("{broken")
    assert cache.load(result.audio_hash, 4, False) is None


def test_audio_hash_is_content_based(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(b"first")
    b.write_bytes(b"first")
    assert audio_hash(a) == audio_hash(b)
    b.write_bytes(b"other")
    assert audio_hash(a) != audio_hash(b)


def test_spotify_identifiers_are_validated():
    identifier = "4uLU6hMCjMI75M1A2tKUQC"
    assert track_id(f"https://open.spotify.com/track/{identifier}?si=abc") == identifier
    assert track_id(f"spotify:track:{identifier}") == identifier
    assert track_id(f"https://evil.test/track/{identifier}") is None
    assert track_id("artist song") is None


def test_real_click_track_analysis_and_cache(tmp_path, monkeypatch):
    from rhythm_orbit.analysis.analyzer import analyze
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path / "cache"))
    sr = 22050
    y = np.zeros(sr * 12, dtype=np.float32)
    pulse = np.sin(2 * np.pi * 700 * np.arange(1000) / sr) * np.exp(-np.arange(1000) / 100)
    for t in np.arange(.25, 12, .5):
        index = round(t * sr)
        y[index:index + len(pulse)] += pulse[:len(y) - index]
    source = tmp_path / "120bpm.wav"
    sf.write(source, y, sr)
    stages = []
    result = analyze(source, progress=lambda n, s: stages.append(n))
    assert 115 < result.tempo < 125
    events = result.instruments[0].events
    assert 21 <= len(events) <= 25
    assert np.mean([min(abs(e.timestamp - t) for t in np.arange(.25, 12, .5)) for e in events]) < .06
    assert result.instruments[0].name == "Mix onsets"
    assert not result.demo
    assert stages[-1] == 100
    cached = analyze(source)
    assert cached.to_dict() == result.to_dict()


def test_silence_fails_without_invented_beats(tmp_path, monkeypatch):
    from rhythm_orbit.analysis.analyzer import analyze
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path / "cache"))
    source = tmp_path / "silence.wav"
    sf.write(source, np.zeros(44100), 22050)
    with pytest.raises(ValueError, match="silent"):
        analyze(source)


def test_cancel_before_loading(tmp_path):
    from rhythm_orbit.analysis.analyzer import analyze
    with pytest.raises(InterruptedError):
        analyze(tmp_path / "missing.wav", cancelled=lambda: True)


def test_muted_mix_has_only_unmuted_samples(tmp_path, monkeypatch):
    from rhythm_orbit.audio import render_stem_mix
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path / "cache"))
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    sf.write(a, np.ones((100, 2)) * .2, 22050, subtype="FLOAT")
    sf.write(b, np.ones((100, 2)) * .3, 22050, subtype="FLOAT")
    mixed, sr = sf.read(render_stem_mix([str(a), str(b)], {str(a)}))
    assert np.allclose(mixed, .3)
    silent, _ = sf.read(render_stem_mix([str(a), str(b)], {str(a), str(b)}))
    assert np.all(silent == 0)


def test_meter_requires_accent_evidence():
    from rhythm_orbit.analysis.meter import meter_candidate
    frames = np.arange(60)
    clear_three = np.tile([4., 1., 1.], 20)
    candidate = meter_candidate(clear_three, frames)
    assert candidate["candidate"] == "3/4"
    assert candidate["status"] == "inferred"
    assert meter_candidate(np.ones(60), frames)["candidate"] is None


def test_separation_failure_does_not_fabricate_stems(tmp_path, monkeypatch):
    from rhythm_orbit.separation.demucs_runner import separate
    class FailedProcess:
        returncode = 1
        def poll(self):
            return 1
    monkeypatch.setattr("rhythm_orbit.separation.demucs_runner.subprocess.Popen", lambda *a, **k: FailedProcess())
    with pytest.raises(RuntimeError, match="Demucs failed"):
        separate(tmp_path / "music.wav", tmp_path / "output", lambda: False)


def test_missing_spotify_credentials_are_actionable(monkeypatch):
    from rhythm_orbit.spotify.client import search
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    with pytest.raises(ValueError, match="SPOTIPY_CLIENT_ID"):
        search("song")
