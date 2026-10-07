"""
spinner.py — Universal PLC Monitor
Animated spinner widget for loading states. Draws a rotating arc using QPainter.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen
from src.ui.theme_manager import ThemeManager


class Spinner(QWidget):
    """A custom-painted animated spinner."""

    def __init__(self, size: int = 32, color: str | None = None,
                 speed: int = 80, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._auto_color = color is None
        self._color = QColor(color) if color else QColor(ThemeManager.get_color("accent"))
        self._angle = 0
        self._spinning = False
        
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName("Loading spinner")
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(speed)
    
    def _rotate(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()
    
    def start(self) -> None:
        self._spinning = True
        self._timer.start()
        self.show()
    
    def stop(self) -> None:
        self._spinning = False
        self._timer.stop()
        self.hide()
    
    def paintEvent(self, event) -> None:
        if not self._spinning:
            return

        if self._auto_color:
            self._color = QColor(ThemeManager.get_color("accent"))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(self._color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        margin = 3
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        
        # Draw background arc (subtle)
        bg_pen = QPen(QColor(80, 90, 110, 60), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)
        
        # Draw spinning arc
        painter.setPen(pen)
        span = 90 * 16  # 90 degrees
        painter.drawArc(rect, self._angle * 16, span)
        
        painter.end()

