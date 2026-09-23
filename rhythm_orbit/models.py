from __future__ import annotations

from dataclasses import asdict, dataclass, field
from bisect import bisect_right
from typing import Any


@dataclass
class RhythmEvent:
    timestamp: float
    instrument: str
    strength: float
    confidence: float
    status: str = "detected"
    duration: float = 0.0
    measure: int = 0
    beat: float = 0.0
    subdivision: str = "unmapped"
    offset_ms: float = 0.0


@dataclass
class InstrumentTrack:
    name: str
    color: str
    events: list[RhythmEvent] = field(default_factory=list)
    confidence: float = 0.0
    stem: str | None = None


@dataclass
class RhythmicPattern:
    instrument: str
    start_time: float
    end_time: float
    pulse_count: int
    confidence: float
    description: str
    ratio: str | None = None
    status: str = "inferred"


@dataclass
class SongAnalysis:
    title: str
    source: str
    duration: float
    tempo: float
    beats: list[float]
    measures: list[float]
    instruments: list[InstrumentTrack]
    meter: int = 4
    meter_status: str = "user-selected grouping; downbeats unverified"
    rhythmic_patterns: list[RhythmicPattern] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    audio_hash: str = ""
    demo: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SongAnalysis:
        data = dict(data)
        data["instruments"] = [InstrumentTrack(**{**t, "events": [RhythmEvent(**e) for e in t["events"]]}) for t in data["instruments"]]
        data["rhythmic_patterns"] = [RhythmicPattern(**p) for p in data.get("rhythmic_patterns", [])]
        return cls(**data)

    def measure_index(self, timestamp: float) -> int:
        return max(0, min(len(self.measures) - 2, bisect_right(self.measures, timestamp) - 1))

    def window(self, timestamp: float, count: int) -> tuple[float, float]:
        index = self.measure_index(timestamp)
        start = (index // count) * count
        return self.measures[start], self.measures[min(start + count, len(self.measures) - 1)]
