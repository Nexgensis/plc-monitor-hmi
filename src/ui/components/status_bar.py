"""
status_bar.py — Universal PLC Monitor
Footer status bar showing PLC messages and database health.
"""
from __future__ import annotations

import logging
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel
from src.utils.constants import DB_PATH

logger = logging.getLogger(__name__)


class StatusBar(QFrame):
    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("status_bar")
        self.setAccessibleName("Status bar")
        self.setFixedHeight(28)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)

        # Left: PLC Message
        self.message_lbl = QLabel("[READY]")
        self.message_lbl.setObjectName("status_message_lbl")
        self.message_lbl.setAccessibleName("PLC status message")
        self.message_lbl.setToolTip("Shows the latest PLC status message")
        layout.addWidget(self.message_lbl)

        layout.addStretch()

        # Right: DB Status + Poll Interval
        poll_ms = 500
        if self.app_state and self.app_state.plc_profile:
            poll_ms = self.app_state.plc_profile.get("poll_interval_ms", 500)

        self.db_lbl = QLabel(f"DB: {DB_PATH} | Poll: {poll_ms}ms")
        self.db_lbl.setObjectName("status_db_lbl")
        self.db_lbl.setAccessibleName("Database and poll status")
        self.db_lbl.setToolTip("Database file path and current polling interval")
        layout.addWidget(self.db_lbl)

    def show_message(self, val: int, text: str, color: str) -> None:
        if val == 0 or not text:
            self.message_lbl.setText("[READY]")
            return

        ts = datetime.now().strftime("%H:%M:%S")
        self.message_lbl.setText(f"[{ts}] {text}")

    def update_poll_info(self, poll_ms: int) -> None:
        self.db_lbl.setText(f"DB: {DB_PATH} | Poll: {poll_ms}ms")
