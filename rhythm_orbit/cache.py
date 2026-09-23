from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
from rhythm_orbit.models import SongAnalysis

VERSION = 1


def cache_root() -> Path:
    base = Path(os.environ.get("RHYTHM_ORBIT_CACHE", Path.home() / ".cache" / "rhythm-orbit"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def audio_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class AnalysisCache:
    def __init__(self, root: Path | None = None):
        self.root = root or cache_root() / "analysis"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str, meter: int, separate: bool) -> Path:
        return self.root / f"v{VERSION}-{digest}-{meter}-{int(separate)}.json"

    def load(self, digest: str, meter: int, separate: bool) -> SongAnalysis | None:
        try:
            result = SongAnalysis.from_dict(json.loads(self.path(digest, meter, separate).read_text()))
            if any(t.stem and not Path(t.stem).is_file() for t in result.instruments):
                return None
            return result
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, result: SongAnalysis, separate: bool) -> None:
        target = self.path(result.audio_hash, result.meter, separate)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.root, delete=False, encoding="utf-8") as stream:
            json.dump(result.to_dict(), stream, allow_nan=False)
            temp = Path(stream.name)
        temp.replace(target)
