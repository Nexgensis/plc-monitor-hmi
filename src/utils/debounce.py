"""
debounce.py — Universal PLC Monitor
Debounce utility for reducing unnecessary signal emissions on fast-typing inputs.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal, QObject


class DebouncedSignal(QObject):
    """Emits a signal after a delay, resetting on each new emission."""
    triggered = pyqtSignal()

    def __init__(self, delay_ms: int = 200, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.triggered.emit)

    def emit(self) -> None:
        self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()

    @property
    def is_pending(self) -> bool:
        return self._timer.isActive()
