from __future__ import annotations
from bisect import bisect_left
import math
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget, QToolTip
from rhythm_orbit.models import SongAnalysis, RhythmEvent, InstrumentTrack


def point(center: QPointF, radius: float, phase: float) -> QPointF:
    angle = math.tau * phase - math.pi / 2
    return QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle))


def event_details(event: RhythmEvent) -> str:
    minutes, seconds = divmod(event.timestamp, 60)
    return (f"{event.instrument}  ·  {event.status.upper()}\n"
            f"{int(minutes):02}:{seconds:06.3f}  ·  Measure {event.measure or 'pickup'}  ·  Beat {event.beat:.2f}\n"
            f"{event.subdivision}\nTiming offset {event.offset_ms:+.1f} ms\n"
            f"Strength {event.strength:.2f}  ·  Confidence score {event.confidence:.0%}")


class CircularView(QWidget):
    event_selected = Signal(object)
    ring_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.analysis: SongAnalysis | None = None
        self.position = 0.0
        self.count = 1
        self.mode = "Instrument rings"
        self.hidden: set[str] = set()
        self.solo: str | None = None
        self.selected: str | None = None
        self.options = {"Events": True, "Subdivisions": True, "Labels": True, "Geometry": True, "Alignments": True}
        self.hits: list[tuple[QPointF, RhythmEvent]] = []
        self.rings: list[tuple[float, str]] = []
        self._timestamps: dict[str, list[float]] = {}
        self.center = QPointF()

    def set_analysis(self, analysis: SongAnalysis) -> None:
        self.analysis = analysis
        self.hidden.clear()
        self.solo = None
        self.selected = None
        self._timestamps = {t.name: [e.timestamp for e in t.events] for t in analysis.instruments}
        self.update()

    def visible_tracks(self) -> list[InstrumentTrack]:
        if not self.analysis:
            return []
        tracks = [t for t in self.analysis.instruments if t.name not in self.hidden and (not self.solo or t.name == self.solo)]
        if self.mode == "Drum view":
            tracks = [t for t in tracks if any(s in t.name.lower() for s in ("kick", "snare", "hat", "cymbal", "tom", "percussion", "clave"))]
        if self.mode == "Polyrhythm":
            names = {p.instrument for p in self.analysis.rhythmic_patterns if p.ratio is None}
            tracks = [t for t in tracks if t.name in names]
        return tracks

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.center = QPointF(self.width() / 2, self.height() / 2)
        outer = min(self.width(), self.height()) / 2 - 34
        gradient = QRadialGradient(self.center, outer * 1.4)
        gradient.setColorAt(0, QColor("#172329"))
        gradient.setColorAt(1, QColor("#0d141b"))
        painter.fillRect(self.rect(), gradient)
        self.hits.clear()
        self.rings.clear()
        if not self.analysis:
            painter.setPen(QColor("#8b9ba9"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open an audio file to explore its rhythm")
            return
        start, end = self.analysis.window(self.position, self.count)
        span = max(end - start, .001)
        tracks = self.visible_tracks()
        if not tracks:
            painter.setPen(QColor("#8b9ba9"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No layers in this view")
            return
        minimal = self.mode == "Minimal"
        geometry_radius = outer * (.60 if self.mode == "Geometry" else .40)
        spacing = (outer - geometry_radius - 18) / max(1, len(tracks))
        # Global tick marks use the actual beat timestamps, including tempo changes.
        if self.options["Subdivisions"] and not minimal:
            for beat in self.analysis.beats:
                if start <= beat < end:
                    phase = (beat - start) / span
                    painter.setPen(QPen(QColor("#34414b"), 1))
                    painter.drawLine(point(self.center, geometry_radius + 10, phase), point(self.center, outer + 13, phase))
                    for divisor in range(1, 4):
                        following = bisect_left(self.analysis.beats, beat) + 1
                        if following < len(self.analysis.beats):
                            t = beat + (self.analysis.beats[following] - beat) * divisor / 4
                            if t < end:
                                painter.setPen(QPen(QColor("#26343d"), 1))
                                p = (t - start) / span
                                painter.drawLine(point(self.center, outer + 6, p), point(self.center, outer + 10, p))
        alignment_events: list[tuple[float, int, QPointF]] = []
        for index, track in enumerate(tracks):
            radius = outer - index * spacing
            self.rings.append((radius, track.name))
            times = self._timestamps[track.name]
            lo, hi = bisect_left(times, start), bisect_left(times, end)
            events = track.events[lo:hi]
            active = any(0 <= self.position - e.timestamp < .11 for e in events)
            color = QColor(track.color)
            ring_color = QColor(color)
            ring_color.setAlpha(155 if active else 70 if self.selected == track.name else 38)
            painter.setPen(QPen(ring_color, 3 if active else 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.center, radius, radius)
            # Equal sectors only when the observed attacks themselves are evenly spaced.
            phases = [(e.timestamp - start) / span for e in events]
            gaps = [b - a for a, b in zip(phases, phases[1:] + ([phases[0] + 1] if phases else []))]
            regular = len(phases) >= 2 and max(abs(g - 1 / len(phases)) for g in gaps) < min(.035, .25 / len(phases))
            if regular and self.options["Subdivisions"] and not minimal:
                sector_color = QColor(color)
                sector_color.setAlpha(65)
                painter.setPen(QPen(sector_color, 1))
                for phase in phases:
                    painter.drawLine(point(self.center, radius - spacing * .35, phase), point(self.center, radius + spacing * .35, phase))
            nodes: list[QPointF] = []
            for e, phase in zip(events, phases):
                pos = point(self.center, radius, phase)
                node = point(self.center, geometry_radius - index * 2, phase)
                nodes.append(node)
                alignment_events.append((e.timestamp, index, node))
                flash = 0 <= self.position - e.timestamp < .11
                if self.options["Events"]:
                    fill = QColor(color)
                    fill.setAlpha(int(90 + e.confidence * 165))
                    size = 2.5 + e.strength * 2.5
                    if flash:
                        glow = QColor(color)
                        glow.setAlpha(45)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(glow)
                        painter.drawEllipse(pos, size * 3, size * 3)
                        size += 2
                        if regular and not minimal:
                            sector = QColor(color)
                            sector.setAlpha(100)
                            painter.setPen(QPen(sector, max(3, spacing * .3)))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            rect = QRectF(self.center.x() - radius, self.center.y() - radius, radius * 2, radius * 2)
                            painter.drawArc(rect, int((90 - phase * 360) * 16), int(-360 / len(phases) * 16))
                    painter.setPen(QPen(fill, 1.5))
                    painter.setBrush(fill if e.status in ("detected", "demo") else QColor("#0d141b"))
                    painter.drawEllipse(pos, size, size)
                    self.hits.append((pos, e))
                if flash and self.options["Geometry"] and not minimal:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    painter.drawEllipse(node, 5, 5)
            if len(nodes) > 1 and self.options["Geometry"] and not minimal:
                line = QColor(color)
                line.setAlpha(125 if self.mode == "Geometry" else 80)
                painter.setPen(QPen(line, 1.1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath(nodes[0])
                for node in nodes[1:]:
                    path.lineTo(node)
                painter.drawPath(path)
            if self.options["Labels"] and not minimal:
                painter.setPen(color)
                painter.setFont(QFont("Sans Serif", 8))
                label = f"{index + 1:02}"
                painter.drawText(QRectF(self.center.x() - 13, self.center.y() - radius - 18, 26, 15), Qt.AlignmentFlag.AlignCenter, label)
        if self.options["Alignments"] and not minimal:
            alignment_events.sort(key=lambda entry: entry[0])
            painter.setPen(QPen(QColor("#e7eee9"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for a, b in zip(alignment_events, alignment_events[1:]):
                if b[0] - a[0] <= .025 and a[1] != b[1]:
                    painter.drawEllipse(a[2], 5, 5)
        # No independent animation clock: the caller supplies QMediaPlayer.position().
        phase = max(0, min(1, (self.position - start) / span))
        tip = point(self.center, outer + 22, phase)
        painter.setPen(QPen(QColor("#d4eee4"), 1.5))
        painter.drawLine(point(self.center, geometry_radius * .22, phase), tip)
        painter.setBrush(QColor("#d4eee4"))
        painter.drawEllipse(tip, 3, 3)
        if not minimal:
            painter.setPen(QColor("#8496a3"))
            painter.setFont(QFont("Sans Serif", 9))
            painter.drawText(QRectF(12, self.height() - 28, self.width() - 24, 20), Qt.AlignmentFlag.AlignCenter,
                             "12 o’clock = window start     ·     time moves clockwise")
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        for pos, rhythm_event in self.hits:
            if (pos - event.position()).manhattanLength() < 13:
                QToolTip.showText(event.globalPosition().toPoint(), event_details(rhythm_event), self)
                return
        QToolTip.hideText()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        for pos, rhythm_event in self.hits:
            if (pos - event.position()).manhattanLength() < 13:
                self.event_selected.emit(rhythm_event)
                return
        distance = math.hypot(event.position().x() - self.center.x(), event.position().y() - self.center.y())
        if self.rings:
            radius, name = min(self.rings, key=lambda r: abs(r[0] - distance))
            if abs(radius - distance) < 14:
                self.selected = name
                self.ring_selected.emit(name)
                self.update()
