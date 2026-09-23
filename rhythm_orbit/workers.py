from __future__ import annotations
from collections.abc import Callable
from threading import Event
from typing import Any
from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    progress = Signal(int, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[..., Any], parent=None):
        super().__init__(parent)
        self.task = task
        self.cancellation = Event()

    def run(self) -> None:
        try:
            result = self.task(self.progress.emit, self.cancellation.is_set)
            if not self.cancellation.is_set():
                self.result.emit(result)
        except InterruptedError:
            self.failed.emit("Analysis cancelled")
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        self.cancellation.set()
