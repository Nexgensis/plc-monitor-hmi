"""
status_bar.py — Universal PLC Monitor
Footer status bar showing PLC messages and database health.
"""
from __future__ import annotations

import logging
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt
from src.utils.constants import DB_PATH

logger = logging.getLogger(__name__)


class StatusBar(QFrame):
    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("status_bar")
        self.setFixedHeight(28)
        self.setStyleSheet("background-color: #070b14; border-top: 1px solid #1e2d4a;")

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)

        # Left: PLC Message
        self.message_lbl = QLabel("[READY]")
        self.message_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #22c55e;")
        layout.addWidget(self.message_lbl)

        layout.addStretch()

        # Right: DB Status + Poll Interval
        poll_ms = 500
        if self.app_state and self.app_state.plc_profile:
            poll_ms = self.app_state.plc_profile.get("poll_interval_ms", 500)

        self.db_lbl = QLabel(f"DB: {DB_PATH} ✓  |  Poll: {poll_ms}ms")
        self.db_lbl.setStyleSheet("font-size: 10px; color: #5a7a9a;")
        layout.addWidget(self.db_lbl)

    def show_message(self, val: int, text: str, color: str) -> None:
        """
        If val==0 or not text: show "[READY]" green.
        Else: "[HH:MM:SS] {text}" in mapped color.
        """
        if val == 0 or not text:
            self.message_lbl.setText("[READY]")
            self.message_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #22c55e;")
            return

        ts = datetime.now().strftime("%H:%M:%S")
        self.message_lbl.setText(f"[{ts}] {text}")

        color_map = {
            "green": "#22c55e",
            "red": "#ef4444",
            "yellow": "#f59e0b",
            "amber": "#f59e0b",
            "white": "#e8f0fa"
        }
        hex_color = color_map.get(color.lower(), "#e8f0fa")
        self.message_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {hex_color};")

    def update_poll_info(self, poll_ms: int) -> None:
        self.db_lbl.setText(f"DB: {DB_PATH} ✓  |  Poll: {poll_ms}ms")
