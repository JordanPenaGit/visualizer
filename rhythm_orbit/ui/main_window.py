from __future__ import annotations
from bisect import bisect_right
from pathlib import Path
from collections.abc import Callable
import json
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QListWidget, QListWidgetItem, QFrame, QSlider, QProgressBar, QFileDialog,
    QSpinBox, QScrollArea, QSplitter)
from rhythm_orbit.models import SongAnalysis, RhythmEvent
from rhythm_orbit.audio import Player, render_stem_mix
from rhythm_orbit.analysis.analyzer import analyze
from rhythm_orbit.demo import create_demo
from rhythm_orbit.workers import Worker
from rhythm_orbit.visualization.circular_view import CircularView, event_details
from rhythm_orbit.ui.theme import STYLE
from rhythm_orbit.ui.spotify_dialog import SpotifyDialog


def label(text: str, name: str = "muted") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(text: str, action: Callable, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(action)
    return widget


def timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02}:{seconds % 60:05.2f}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rhythm Orbit")
        self.resize(1340, 940)
        self.setMinimumSize(1060, 740)
        self.setStyleSheet(STYLE)
        self.analysis: SongAnalysis | None = None
        self.local_path: Path | None = None
        self.worker: Worker | None = None
        self.close_requested = False
        self._pending_position: int | None = None
        self._resume = False
        self.player = Player(self)
        self.player.error.connect(self.show_error)
        self.player.media.mediaStatusChanged.connect(self.media_status)
        self.player.media.playbackStateChanged.connect(self.playback_state)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.addWidget(label("◉  RHYTHM ORBIT", "brand"))
        brand.addWidget(label("THE SHAPE OF TIME", "eyebrow"))
        header.addLayout(brand)
        header.addStretch()
        self.demo_button = button("Demo session", self.load_demo)
        self.spotify_button = button("Spotify lookup", self.spotify)
        self.open_button = button("＋ Open audio", self.open_audio, True)
        for widget in (self.demo_button, self.spotify_button, self.open_button):
            header.addWidget(widget)
        layout.addLayout(header)
        song = QFrame()
        song.setObjectName("panel")
        song_layout = QHBoxLayout(song)
        song_layout.setContentsMargins(20, 14, 20, 14)
        song_info = QVBoxLayout()
        self.badge = label("DEMO SESSION", "eyebrow")
        self.title = label("Three against four", "title")
        self.subtitle = label("Synthesized rhythm study · 16 measures")
        self.subtitle.setWordWrap(True)
        song_info.addWidget(self.badge)
        song_info.addWidget(self.title)
        song_info.addWidget(self.subtitle)
        song_layout.addLayout(song_info, 1)
        self.tempo_label = label("120\nBPM", "title")
        self.position_label = label("01\nMEASURE", "title")
        self.beat_label = label("1.00\nBEAT", "title")
        for widget in (self.tempo_label, self.position_label, self.beat_label):
            widget.setMinimumWidth(108)
            widget.setStyleSheet("font-size: 18px;")
            song_layout.addWidget(widget)
        layout.addWidget(song)
        analysis_bar = QHBoxLayout()
        analysis_bar.addWidget(label("ANALYSIS", "eyebrow"))
        analysis_bar.addWidget(label("Measure grouping"))
        self.meter = QComboBox()
        self.meter.addItems(["3/4", "4/4", "5/4", "7/4"])
        self.meter.setCurrentIndex(1)
        analysis_bar.addWidget(self.meter)
        self.separate = QCheckBox("Separate stems with Demucs")
        self.separate.setToolTip("Requires the optional separation extra. The first run downloads a large model.")
        analysis_bar.addWidget(self.separate)
        analysis_bar.addStretch()
        self.cancel_button = button("Cancel", self.cancel_work)
        self.cancel_button.setEnabled(False)
        analysis_bar.addWidget(self.cancel_button)
        self.analyze_button = button("Analyze", self.run_analysis, True)
        self.analyze_button.setEnabled(False)
        analysis_bar.addWidget(self.analyze_button)
        layout.addLayout(analysis_bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 12, 0)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Instrument rings", "Polyrhythm", "Drum view", "Geometry", "Minimal"])
        self.mode.currentTextChanged.connect(self.change_mode)
        toolbar.addWidget(self.mode)
        toolbar.addStretch()
        toolbar.addWidget(label("WINDOW"))
        self.window_count = QComboBox()
        self.window_count.addItems(["1 measure", "2 measures", "4 measures", "8 measures"])
        self.window_count.currentIndexChanged.connect(self.change_window)
        toolbar.addWidget(self.window_count)
        left_layout.addLayout(toolbar)
        self.view = CircularView()
        self.view.event_selected.connect(self.inspect_event)
        self.view.ring_selected.connect(self.select_ring)
        left_layout.addWidget(self.view, 1)
        self.window_label = label("MEASURE 01  /  16")
        left_layout.addWidget(self.window_label)
        options = QHBoxLayout()
        for name in self.view.options:
            check = QCheckBox(name)
            check.setChecked(True)
            check.toggled.connect(lambda value, key=name: self.set_option(key, value))
            options.addWidget(check)
        left_layout.addLayout(options)
        split.addWidget(left)
        sidebar = QFrame()
        sidebar.setObjectName("panel")
        sidebar.setMinimumWidth(300)
        sidebar.setMaximumWidth(380)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 16, 18, 16)
        side.setSpacing(7)
        side.addWidget(label("RHYTHMIC LAYERS", "eyebrow"))
        side.addWidget(label("Check to show · select to inspect"))
        self.track_list = QListWidget()
        self.track_list.setMinimumHeight(130)
        self.track_list.itemChanged.connect(self.visibility_changed)
        self.track_list.currentRowChanged.connect(self.track_selected)
        side.addWidget(self.track_list, 1)
        tools = QHBoxLayout()
        self.solo_button = button("Solo view", self.solo)
        self.solo_button.setCheckable(True)
        tools.addWidget(self.solo_button)
        tools.addWidget(button("↑", lambda: self.move_track(-1)))
        tools.addWidget(button("↓", lambda: self.move_track(1)))
        side.addLayout(tools)
        self.mute_button = button("Mute stem", self.mute)
        self.mute_button.setEnabled(False)
        self.mute_button.setToolTip("Drum candidates share one drum stem; muting any one mutes that entire stem.")
        side.addWidget(self.mute_button)
        side.addWidget(label("EVENT INSPECTOR", "eyebrow"))
        self.inspector = label("Click an event to inspect its timing,\nstrength and confidence score.")
        self.inspector.setMinimumHeight(82)
        self.inspector.setWordWrap(True)
        self.inspector.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.inspector)
        side.addWidget(label("PATTERN NOTES", "eyebrow"))
        self.patterns = label("")
        self.patterns.setWordWrap(True)
        self.patterns.setMinimumHeight(52)
        side.addWidget(self.patterns)
        self.export_button = button("Export analysis JSON", self.export)
        side.addWidget(self.export_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(sidebar)
        split.addWidget(scroll)
        split.setStretchFactor(0, 1)
        split.setSizes([850, 330])
        layout.addWidget(split, 1)
        transport = QFrame()
        transport.setObjectName("panel")
        transport_layout = QVBoxLayout(transport)
        transport_layout.setContentsMargins(18, 12, 18, 12)
        transport_layout.setSpacing(12)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.sliderReleased.connect(self.seek_released)
        transport_layout.addWidget(self.seek)
        playback = QHBoxLayout()
        self.play_button = button("▶  Play", self.player.toggle, True)
        self.play_button.setMinimumWidth(95)
        self.stop_button = button("■", self.player.media.stop)
        playback.addWidget(self.play_button)
        playback.addWidget(self.stop_button)
        playback.addWidget(button("‹ Measure", lambda: self.navigate(-1)))
        playback.addWidget(button("Measure ›", lambda: self.navigate(1)))
        self.clock = label("00:00.00 / 00:32.00", "title")
        self.clock.setStyleSheet("font-size: 16px; font-family: monospace;")
        playback.addWidget(self.clock)
        playback.addStretch()
        playback.addWidget(label("Go to"))
        self.measure_jump = QSpinBox()
        self.measure_jump.setRange(1, 16)
        self.measure_jump.editingFinished.connect(self.jump_measure)
        playback.addWidget(self.measure_jump)
        playback.addWidget(label("Vol"))
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setFixedWidth(90)
        volume.setRange(0, 100)
        volume.setValue(70)
        volume.valueChanged.connect(lambda v: self.player.output.setVolume(v / 100))
        playback.addWidget(volume)
        transport_layout.addLayout(playback)
        layout.addWidget(transport)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = label("Ready")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        QShortcut(QKeySequence("Space"), self, activated=self.player.toggle)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_audio)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.muted_stems: set[str] = set()
        self.load_demo()

    def load_demo(self) -> None:
        if self.worker:
            return
        self.local_path = None
        self.load_analysis(create_demo())
        self.analyze_button.setEnabled(False)

    def load_analysis(self, analysis: SongAnalysis) -> None:
        self.analysis = analysis
        self.muted_stems.clear()
        self._pending_position = None
        self.player.load(analysis.source)
        self.view.position = 0
        self.view.set_analysis(analysis)
        self.title.setText(analysis.title)
        self.badge.setText("DEMO SESSION · AUTHORED EVENTS" if analysis.demo else "LOCAL AUDIO · ANALYSIS")
        self.subtitle.setText(analysis.meter_status)
        self.meter.setCurrentText(f"{analysis.meter}/4")
        self.tempo_label.setText(f"{analysis.tempo:.1f}\nBPM")
        self.seek.setRange(0, round(analysis.duration * 1000))
        pickup = int(analysis.beats[0] > .001)
        self.measure_jump.setRange(0 if pickup else 1, len(analysis.measures) - 1 - pickup)
        self.measure_jump.setSpecialValueText("Pickup" if pickup else "")
        self.track_list.blockSignals(True)
        self.track_list.clear()
        for index, track in enumerate(analysis.instruments):
            item = QListWidgetItem(f"{index + 1:02}  {track.name}   ·   {len(track.events)}")
            item.setData(Qt.ItemDataRole.UserRole, track.name)
            item.setForeground(QColor(track.color))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.track_list.addItem(item)
        self.track_list.blockSignals(False)
        self.solo_button.setChecked(False)
        self.mute_button.setEnabled(False)
        self.inspector.setText("Click an event to inspect its timing,\nstrength and confidence score.")
        ratios = [f"{p.ratio}  ·  {p.instrument}" for p in analysis.rhythmic_patterns if p.ratio]
        self.patterns.setText("\n".join(ratios[:3]) if ratios else ("Repeating patterns found; no supported pulse ratio." if analysis.rhythmic_patterns else "No stable repeating relationship found."))
        self.patterns.setToolTip("\n".join(f"{p.instrument}: {p.description} ({p.confidence:.0%})" for p in analysis.rhythmic_patterns))
        self.status.setText("  ".join(analysis.warnings))
        self.export_button.setEnabled(True)

    def open_audio(self) -> None:
        if self.worker:
            return
        name, _ = QFileDialog.getOpenFileName(self, "Open local audio", "", "Audio (*.wav *.mp3 *.flac *.m4a *.ogg *.aac *.aiff *.aif *.opus);;All files (*)")
        if name:
            self.local_path = Path(name)
            self._pending_position = None
            self.muted_stems.clear()
            self.analysis = None
            self.view.analysis = None
            self.view.update()
            self.track_list.clear()
            self.title.setText(self.local_path.stem)
            self.badge.setText("LOCAL AUDIO · READY TO ANALYZE")
            self.subtitle.setText("Choose a measure grouping and click Analyze")
            self.tempo_label.setText("—\nBPM")
            self.position_label.setText("—\nMEASURE")
            self.beat_label.setText("—\nBEAT")
            self.patterns.setText("Analyze this file to inspect rhythmic relationships.")
            self.inspector.setText("No events analyzed yet.")
            self.window_label.setText("No beat grid analyzed yet")
            self.mute_button.setEnabled(False)
            self.status.setText("Local audio ready. Analysis runs in the background.")
            self.export_button.setEnabled(False)
            self.player.load(name)
            self.analyze_button.setEnabled(True)

    def run_analysis(self) -> None:
        if not self.local_path or self.worker:
            return
        path, meter, separate = self.local_path, int(self.meter.currentText().split("/")[0]), self.separate.isChecked()
        self.start_work(lambda progress, cancel: analyze(path, meter, separate, progress, cancel), self.load_analysis)

    def start_work(self, task: Callable, result: Callable) -> None:
        self.worker = Worker(task, self)
        self.worker.progress.connect(self.report_progress)
        self.worker.result.connect(result)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.finished_work)
        self.set_busy(True)
        self.worker.start()

    def set_busy(self, value: bool) -> None:
        for widget in (self.demo_button, self.open_button, self.analyze_button, self.meter, self.separate, self.mute_button):
            widget.setEnabled(not value)
        self.analyze_button.setEnabled(not value and self.local_path is not None)
        self.cancel_button.setEnabled(value)
        if not value:
            self.track_selected(self.track_list.currentRow())

    def report_progress(self, amount: int, message: str) -> None:
        self.progress.setValue(amount)
        self.status.setText(message)

    def finished_work(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        if self.close_requested:
            self.close()

    def cancel_work(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status.setText("Cancelling after the current analysis stage…")
            self.cancel_button.setEnabled(False)

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.progress.setValue(0)

    def tick(self) -> None:
        position = self.player.media.position() / 1000
        duration = self.analysis.duration if self.analysis else self.player.media.duration() / 1000
        self.clock.setText(f"{timestamp(position)} / {timestamp(duration)}")
        if not self.seek.isSliderDown():
            self.seek.setRange(0, max(1, round(duration * 1000)))
            self.seek.setValue(round(position * 1000))
        self.view.position = position
        if self.analysis:
            analysis = self.analysis
            measure = analysis.measure_index(position)
            first = analysis.beats[0]
            pickup = first > .001
            number = measure if pickup else measure + 1
            self.position_label.setText(f"{number:02}\nMEASURE" if number else "Pickup\nMEASURE")
            index = max(0, min(len(analysis.beats) - 2, bisect_right(analysis.beats, position) - 1))
            span = analysis.beats[index + 1] - analysis.beats[index]
            fraction = (position - analysis.beats[index]) / max(span, .001)
            beat = index % analysis.meter + 1 + fraction
            self.beat_label.setText(f"{beat:.2f}\nBEAT" if position >= first else "—\nBEAT")
            start, end = analysis.window(position, self.view.count)
            self.window_label.setText(f"WINDOW  {timestamp(start)} — {timestamp(end)}   ·   {analysis.meter}/4 GROUPING   ·   SUBDIVISION {int(max(0, fraction) * 4) + 1}/4 OF BEAT")
        self.view.update()

    def playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText("Ⅱ  Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "▶  Play")

    def seek_released(self) -> None:
        self.player.media.setPosition(self.seek.value())

    def navigate(self, delta: int) -> None:
        if self.analysis:
            index = self.analysis.measure_index(self.player.media.position() / 1000)
            index = max(0, min(len(self.analysis.measures) - 2, index + delta))
            self.player.media.setPosition(round(self.analysis.measures[index] * 1000))
            self.tick()

    def jump_measure(self) -> None:
        if self.analysis:
            pickup = int(self.analysis.beats[0] > .001)
            index = self.measure_jump.value() - 1 + pickup
            self.player.media.setPosition(round(self.analysis.measures[index] * 1000))
            self.tick()

    def change_mode(self, mode: str) -> None:
        self.view.mode = mode
        self.view.update()

    def change_window(self, index: int) -> None:
        self.view.count = (1, 2, 4, 8)[index]
        self.view.update()

    def set_option(self, key: str, value: bool) -> None:
        self.view.options[key] = value
        self.view.update()

    def inspect_event(self, event: RhythmEvent) -> None:
        self.inspector.setText(event_details(event))

    def select_ring(self, name: str) -> None:
        for index in range(self.track_list.count()):
            if self.track_list.item(index).data(Qt.ItemDataRole.UserRole) == name:
                self.track_list.setCurrentRow(index)
                break

    def visibility_changed(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.view.hidden.discard(name)
        else:
            self.view.hidden.add(name)
        self.view.update()

    def track_selected(self, index: int) -> None:
        if not self.analysis or index < 0:
            self.mute_button.setEnabled(False)
            return
        track = self.analysis.instruments[index]
        self.view.selected = track.name
        self.solo_button.setChecked(self.view.solo == track.name)
        self.mute_button.setEnabled(bool(track.stem) and self.worker is None)
        self.mute_button.setText("Unmute stem" if track.stem in self.muted_stems else "Mute stem")
        self.view.update()

    def solo(self) -> None:
        item = self.track_list.currentItem()
        self.view.solo = item.data(Qt.ItemDataRole.UserRole) if item and self.solo_button.isChecked() else None
        self.solo_button.setChecked(self.view.solo is not None)
        self.view.update()

    def move_track(self, delta: int) -> None:
        index = self.track_list.currentRow()
        if not self.analysis or not 0 <= index + delta < len(self.analysis.instruments) or index < 0:
            return
        self.analysis.instruments[index], self.analysis.instruments[index + delta] = self.analysis.instruments[index + delta], self.analysis.instruments[index]
        self.track_list.blockSignals(True)
        item = self.track_list.takeItem(index)
        self.track_list.insertItem(index + delta, item)
        for n, track in enumerate(self.analysis.instruments):
            self.track_list.item(n).setText(f"{n + 1:02}  {track.name}   ·   {len(track.events)}")
        self.track_list.setCurrentRow(index + delta)
        self.track_list.blockSignals(False)
        self.track_selected(index + delta)

    def mute(self) -> None:
        index = self.track_list.currentRow()
        if not self.analysis or index < 0 or self.worker:
            return
        stem = self.analysis.instruments[index].stem
        if not stem:
            return
        desired = self.muted_stems ^ {stem}
        stems = list(self.analysis.metadata.get("stems", {}).values()) or list({t.stem for t in self.analysis.instruments if t.stem})
        self.report_progress(10, "Preparing synchronized stem mix…")
        self.start_work(lambda _, cancel: (render_stem_mix(stems, desired, cancel), desired), self.apply_mix)

    def apply_mix(self, result: tuple[Path, set[str]]) -> None:
        path, muted = result
        self.muted_stems = muted
        position = self.player.media.position()
        self._resume = self.player.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.load(str(path))
        self._pending_position = position
        self.status.setText("Stem mix ready. Drum candidates share the same drum stem.")
        self.progress.setValue(100)

    def media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia) and self._pending_position is not None:
            position = self._pending_position
            self._pending_position = None
            self.player.media.setPosition(position)
            if self._resume:
                self.player.media.play()

    def spotify(self) -> None:
        dialog = SpotifyDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def export(self) -> None:
        if self.analysis:
            name, _ = QFileDialog.getSaveFileName(self, "Export analysis", "rhythm-analysis.json", "JSON (*.json)")
            if name:
                try:
                    Path(name).write_text(json.dumps(self.analysis.to_dict(), indent=2, allow_nan=False), encoding="utf-8")
                    self.status.setText(f"Analysis exported to {name}")
                except OSError as exc:
                    self.show_error(str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker:
            self.close_requested = True
            self.cancel_work()
            event.ignore()
        else:
            self.player.media.stop()
            event.accept()
