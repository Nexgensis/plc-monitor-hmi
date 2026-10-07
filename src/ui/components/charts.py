"""
charts.py — Universal PLC Monitor
Simple chart widgets for data visualization using QPainter.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from src.ui.theme_manager import ThemeManager


def _c(token: str) -> QColor:
    """Theme-aware design token as QColor (resolved per paint)."""
    return QColor(ThemeManager.get_color(token))


class PieChart(QWidget):
    """Simple pie chart widget showing pass/fail distribution."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.setMaximumSize(200, 200)
        self._pass_count = 0
        self._fail_count = 0
        self.setAccessibleName("Pass/fail distribution chart")

    def set_data(self, pass_count: int, fail_count: int) -> None:
        self._pass_count = pass_count
        self._fail_count = fail_count
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin = 30
        size = min(w, h) - 2 * margin
        rect = QRect(margin, margin, size, size)

        total = self._pass_count + self._fail_count
        if total == 0:
            painter.setBrush(QBrush(_c("border")))
            painter.drawEllipse(rect)
            painter.setPen(QPen(_c("text_muted")))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        pass_pct = self._pass_count / total
        pass_angle = int(pass_pct * 5760)
        fail_angle = 5760 - pass_angle

        pass_color = _c("pass")
        fail_color = _c("fail")

        painter.setPen(Qt.PenStyle.NoPen)

        if pass_angle > 0:
            painter.setBrush(QBrush(pass_color))
            painter.drawPie(rect, 0, pass_angle)
        if fail_angle > 0:
            painter.setBrush(QBrush(fail_color))
            painter.drawPie(rect, pass_angle, fail_angle)

        inner_rect = QRect(margin + size // 4, margin + size // 4, size // 2, size // 2)
        painter.setBrush(QBrush(_c("bg_secondary")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(inner_rect)

        painter.setPen(QPen(_c("text_primary")))
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(inner_rect, Qt.AlignmentFlag.AlignCenter, f"{pass_pct * 100:.0f}%")

        legend_y = h - 18
        painter.setBrush(QBrush(pass_color))
        painter.drawRect(margin, legend_y, 10, 10)
        painter.setPen(QPen(_c("text_primary")))
        painter.drawText(margin + 14, legend_y + 10, f"Pass ({self._pass_count})")

        fail_x = w // 2
        painter.setBrush(QBrush(fail_color))
        painter.drawRect(fail_x, legend_y, 10, 10)
        painter.setPen(QPen(_c("text_primary")))
        painter.drawText(fail_x + 14, legend_y + 10, f"Fail ({self._fail_count})")


class BarChart(QWidget):
    """Simple horizontal bar chart for parameter failure frequency."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._data: list[tuple[str, int]] = []
        self.setAccessibleName("Parameter failure frequency chart")

    def set_data(self, data: list[tuple[str, int]]) -> None:
        self._data = sorted(data, key=lambda x: x[1], reverse=True)[:5]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        if not self._data:
            painter.setPen(QPen(_c("text_muted")))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No data")
            return

        margin_left = 100
        margin_right = 40
        margin_top = 5
        bar_height = 20
        spacing = 8

        max_val = max(d[1] for d in self._data) if self._data else 1
        chart_w = w - margin_left - margin_right

        for i, (name, count) in enumerate(self._data):
            y = margin_top + i * (bar_height + spacing)
            if y + bar_height > h:
                break

            bar_w = int((count / max_val) * chart_w) if max_val > 0 else 0

            painter.setPen(QPen(_c("text_muted")))
            painter.drawText(QRect(0, y, margin_left - 8, bar_height),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)

            if count > 0:
                color = _c("fail") if i == 0 else _c("warn") if i < 3 else _c("accent")
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(margin_left, y, bar_w, bar_height, 3, 3)

                painter.setPen(QPen(_c("text_primary")))
                painter.drawText(QRect(margin_left + bar_w + 6, y, 30, bar_height),
                               Qt.AlignmentFlag.AlignVCenter, str(count))
