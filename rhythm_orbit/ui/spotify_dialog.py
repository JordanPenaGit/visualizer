from __future__ import annotations
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QPixmap, QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListWidget, QLabel
from rhythm_orbit.spotify.client import search, artwork
from rhythm_orbit.workers import Worker


class SpotifyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spotify · song identification")
        self.resize(620, 520)
        self.worker: Worker | None = None
        self._closing = False
        self.tracks: list[dict] = []
        self.art_index: int | None = None
        layout = QVBoxLayout(self)
        intro = QLabel("Find a song on Spotify")
        intro.setObjectName("title")
        layout.addWidget(intro)
        notice = QLabel("Spotify identifies the song. Open a local audio file in Rhythm Orbit for detailed analysis.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Track URL, spotify:track: URI, or song / artist")
        self.go = QPushButton("Search")
        self.go.clicked.connect(self.lookup)
        self.query.returnPressed.connect(self.lookup)
        row.addWidget(self.query, 1)
        row.addWidget(self.go)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.currentRowChanged.connect(self.select)
        layout.addWidget(self.results, 1)
        details = QHBoxLayout()
        self.art = QLabel()
        self.art.setFixedSize(72, 72)
        self.info = QLabel("Metadata supplied by Spotify")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setWordWrap(True)
        details.addWidget(self.art)
        details.addWidget(self.info, 1)
        layout.addLayout(details)
        self.open = QPushButton("Open selected song in Spotify")
        self.open.setEnabled(False)
        self.open.clicked.connect(self.open_track)
        layout.addWidget(self.open)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def lookup(self) -> None:
        if self.worker or not self.query.text().strip():
            return
        query = self.query.text().strip()
        self.art_index = None
        self.go.setEnabled(False)
        self.status.setText("Searching Spotify…")
        self.worker = Worker(lambda *_: search(query), self)
        self.worker.result.connect(self.loaded)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.done_work)
        self.worker.start()

    def loaded(self, tracks: list[dict]) -> None:
        self.tracks = tracks
        self.results.clear()
        for t in tracks:
            self.results.addItem(f"{t['title']}  ·  {t['artist']}")
        self.status.setText(f"{len(tracks)} results · local audio required for analysis")
        if tracks:
            self.results.setCurrentRow(0)

    def done_work(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.go.setEnabled(True)
        if self._closing:
            self.reject()
        elif self.results.currentRow() >= 0 and self.results.currentRow() != self.art_index:
            self.select(self.results.currentRow())

    def select(self, index: int) -> None:
        self.art.clear()
        self.open.setEnabled(index >= 0)
        if index < 0:
            return
        t = self.tracks[index]
        self.info.setText(f"{t['title']}\n{t['artist']} · {t['album']}\n{int(t['duration'] // 60)}:{int(t['duration'] % 60):02} · Spotify")
        if t["artwork"] and not self.worker:
            self.art_index = index
            self.go.setEnabled(False)
            self.worker = Worker(lambda *_: (index, artwork(t["artwork"])), self)
            self.worker.result.connect(self.show_art)
            self.worker.failed.connect(lambda _: self.status.setText("Artwork unavailable; song metadata is available"))
            self.worker.finished.connect(self.done_work)
            self.worker.start()

    def show_art(self, result: tuple[int, bytes]) -> None:
        if result[0] == self.results.currentRow():
            pixmap = QPixmap()
            pixmap.loadFromData(result[1])
            self.art.setPixmap(pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def open_track(self) -> None:
        index = self.results.currentRow()
        if index >= 0:
            QDesktopServices.openUrl(QUrl(self.tracks[index]["url"]))

    def reject(self) -> None:
        if self.worker:
            self._closing = True
            self.worker.cancel()
            self.status.setText("Closing after the current request completes…")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker:
            event.ignore()
            self.reject()
        else:
            event.accept()
