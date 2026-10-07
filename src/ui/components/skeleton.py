"""
skeleton.py — Universal PLC Monitor
Skeleton loader widgets for showing placeholder content during data loading.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QLinearGradient


class SkeletonBar(QWidget):
    """A single animated skeleton bar placeholder."""
    
    def __init__(self, width: int = 200, height: int = 16, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._offset = 0.0
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.setInterval(50)
        
        self._anim = QPropertyAnimation(self, b"skeleton_offset")
        self._anim.setDuration(1200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
    
    def _get_offset(self) -> float:
        return self._offset
    
    def _set_offset(self, val: float) -> None:
        self._offset = val
        self.update()
    
    skeleton_offset = pyqtProperty(float, _get_offset, _set_offset)
    
    def start_animation(self) -> None:
        self._anim.start()
    
    def stop_animation(self) -> None:
        self._anim.stop()
    
    def paintEvent(self, event) -> None:
        from src.ui.theme_manager import ThemeManager

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        base_color = QColor(ThemeManager.get_color("border"))
        if ThemeManager.current() == "dark":
            highlight_color = base_color.lighter(135)
        else:
            highlight_color = base_color.darker(110)
        
        gradient = QLinearGradient(0, 0, self.width(), 0)
        pos = self._offset
        gradient.setColorAt(max(0, pos - 0.3), base_color)
        gradient.setColorAt(pos, highlight_color)
        gradient.setColorAt(min(1.0, pos + 0.3), base_color)
        
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        painter.end()


class SkeletonCard(QFrame):
    """A card-shaped skeleton placeholder with multiple bars."""
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(100)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        self._bars = []
        
        # Title bar
        bar = SkeletonBar(140, 14)
        layout.addWidget(bar)
        self._bars.append(bar)
        
        # Subtitle bar
        bar = SkeletonBar(100, 10)
        layout.addWidget(bar)
        self._bars.append(bar)
        
        layout.addSpacing(10)
        
        # Content bars
        for w in [180, 160, 200, 120]:
            bar = SkeletonBar(w, 12)
            layout.addWidget(bar)
            self._bars.append(bar)
        
        layout.addStretch()
    
    def start(self) -> None:
        for bar in self._bars:
            bar.start_animation()
    
    def stop(self) -> None:
        for bar in self._bars:
            bar.stop_animation()


class SkeletonTable(QFrame):
    """A table-shaped skeleton placeholder."""
    
    def __init__(self, rows: int = 5, cols: int = 4, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(rows * 40 + 40)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)
        
        self._bars = []
        
        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        for _ in range(cols):
            bar = SkeletonBar(80, 14)
            header_row.addWidget(bar)
            self._bars.append(bar)
        layout.addLayout(header_row)
        
        layout.addSpacing(8)
        
        # Data rows
        for _ in range(rows):
            row = QHBoxLayout()
            row.setSpacing(10)
            for j in range(cols):
                w = 100 if j == 0 else 60 + (j * 20)
                bar = SkeletonBar(w, 12)
                row.addWidget(bar)
                self._bars.append(bar)
            layout.addLayout(row)
            layout.addSpacing(4)
        
        layout.addStretch()
    
    def start(self) -> None:
        for bar in self._bars:
            bar.start_animation()
    
    def stop(self) -> None:
        for bar in self._bars:
            bar.stop_animation()
