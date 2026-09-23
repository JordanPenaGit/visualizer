from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import time
from collections.abc import Callable


def separate(path: Path, destination: Path, cancelled: Callable[[], bool]) -> dict[str, Path]:
    """Run in a worker; drain logs to disk and terminate the child on cancellation."""
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "demucs.log").open("w+") as log:
        process = subprocess.Popen([sys.executable, "-m", "demucs", "-n", "htdemucs", "--out", str(destination), str(path)],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if cancelled():
                    raise InterruptedError("Analysis cancelled")
                time.sleep(0.15)
            if process.returncode:
                log.seek(0)
                raise RuntimeError("Demucs failed. Install the separation extra and FFmpeg; model download needs internet.\n" + log.read()[-1800:])
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    folder = destination / "htdemucs" / path.stem
    stems = {name: folder / f"{name}.wav" for name in ("drums", "bass", "vocals", "other")}
    if not all(p.is_file() for p in stems.values()):
        raise RuntimeError("Demucs completed without the expected four stems")
    return stems
