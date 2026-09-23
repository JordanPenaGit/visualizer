from __future__ import annotations
from pathlib import Path
import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from rhythm_orbit.cache import cache_root
import hashlib


class Player(QObject):
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.media = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(0.7)
        self.media.setAudioOutput(self.output)
        self.media.errorOccurred.connect(lambda *_: self.error.emit(self.media.errorString()))

    def load(self, path: str) -> None:
        self.media.stop()
        self.media.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))

    def toggle(self) -> None:
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media.pause()
        else:
            self.media.play()


def render_stem_mix(stems: list[str], muted: set[str], cancelled=lambda: False) -> Path:
    """Build a cached mix in a worker; a single player then keeps all stems in sync."""
    all_stems = sorted(set(stems))
    identity = repr([(p, Path(p).stat().st_mtime_ns) for p in all_stems]) + repr(sorted(muted))
    target = cache_root() / ("mix-" + hashlib.sha256(identity.encode()).hexdigest() + ".wav")
    if target.is_file():
        return target
    handles = [sf.SoundFile(p) for p in all_stems]
    temporary = target.with_suffix(".partial.wav")
    try:
        first = handles[0]
        if any(f.samplerate != first.samplerate or f.channels != first.channels or len(f) != len(first) for f in handles):
            raise ValueError("Stem formats or lengths do not match")
        with sf.SoundFile(temporary, "w", samplerate=first.samplerate, channels=first.channels, subtype="FLOAT") as output:
            while True:
                if cancelled():
                    raise InterruptedError("Mix cancelled")
                blocks = [f.read(65536, dtype="float32", always_2d=True) for f in handles]
                if not len(blocks[0]):
                    break
                mix = np.zeros_like(blocks[0])
                for path, block in zip(all_stems, blocks):
                    if path not in muted:
                        mix += block
                output.write(np.clip(mix, -1, 1))
        temporary.replace(target)
        return target
    finally:
        for handle in handles:
            handle.close()
        temporary.unlink(missing_ok=True)
