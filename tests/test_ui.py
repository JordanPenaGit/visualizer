import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from rhythm_orbit.ui.main_window import MainWindow
from rhythm_orbit.visualization.circular_view import point


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_clockwise_mapping():
    center = QPointF(100, 100)
    assert point(center, 50, 0).y() == pytest.approx(50)
    assert point(center, 50, .25).x() == pytest.approx(150)
    assert point(center, 50, .5).y() == pytest.approx(150)


def test_native_ui_events_modes_visibility_and_seek(app, tmp_path, monkeypatch):
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path))
    window = MainWindow()
    window.show()
    QTest.qWait(150)
    assert window.analysis.demo
    assert len(window.view.hits) == 19
    pos, event = window.view.hits[2]
    QTest.mouseClick(window.view, Qt.MouseButton.LeftButton, pos=pos.toPoint())
    assert event.instrument in window.inspector.text()
    item = window.track_list.item(0)
    item.setCheckState(Qt.CheckState.Unchecked)
    assert "Hi-hat" in window.view.hidden
    window.track_list.setCurrentRow(1)
    window.solo_button.click()
    assert [t.name for t in window.view.visible_tracks()] == ["Kick"]
    window.solo_button.click()
    window.move_track(-1)
    assert window.analysis.instruments[0].name == "Kick"
    window.window_count.setCurrentIndex(2)
    assert window.view.count == 4
    for mode in ("Polyrhythm", "Geometry", "Drum view", "Minimal"):
        window.mode.setCurrentText(mode)
        app.processEvents()
        assert not window.view.grab().isNull()
    window.player.media.setPosition(4500)
    window.tick()
    assert window.view.position == pytest.approx(4.5, abs=.05)
    assert "03" in window.position_label.text()
    window.navigate(1)
    assert window.player.media.position() == 6000
    window.close()
    app.processEvents()


def test_cancel_and_close_waits_for_worker(app, tmp_path, monkeypatch):
    from threading import Event
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path))
    window = MainWindow()
    window.show()
    entered = Event()
    def task(progress, cancelled):
        entered.set()
        while not cancelled():
            Event().wait(.01)
        raise InterruptedError("Analysis cancelled")
    window.start_work(task, lambda _: None)
    for _ in range(100):
        QTest.qWait(10)
        if entered.is_set():
            break
    assert entered.is_set()
    assert window.cancel_button.isEnabled()
    window.close()
    for _ in range(100):
        QTest.qWait(10)
        if window.worker is None:
            break
    assert window.worker is None
    assert not window.isVisible()


def test_analysis_worker_replaces_demo_with_real_results(app, tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("RHYTHM_ORBIT_CACHE", str(tmp_path))
    window = MainWindow()
    window.show()
    window.local_path = Path(window.analysis.source)
    window.run_analysis()
    for _ in range(3000):
        QTest.qWait(10)
        if window.worker is None:
            break
    assert window.worker is None
    assert not window.analysis.demo
    assert window.analysis.instruments[0].name == "Mix onsets"
    assert window.progress.value() == 100
    window.close()
