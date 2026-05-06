"""
top_bar.py — Universal PLC Monitor
Top bar showing application status, PLC connectivity, and active user.
"""
from __future__ import annotations

import logging
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import QTimer, Qt
from src.utils.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class TopBar(QFrame):
    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("top_bar")
        self.setFixedHeight(44)

        self._init_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_clock)
        self._timer.start(1000)
        self._update_clock()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(15)

        # Left: App Name
        self.app_name_lbl = QLabel(f"{APP_NAME} v{APP_VERSION}")
        self.app_name_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #3b82f6;")
        layout.addWidget(self.app_name_lbl)

        # Center: Page Title
        self.title_lbl = QLabel("HOME")
        self.title_lbl.setStyleSheet("font-weight: 600; font-size: 14px; text-transform: uppercase;")
        layout.addWidget(self.title_lbl)

        layout.addStretch()

        # PLC Status
        self.plc_status_lbl = QLabel("● Not Configured")
        self.plc_status_lbl.setStyleSheet("font-weight: 600; color: #f59e0b;") # Amber default
        layout.addWidget(self.plc_status_lbl)

        # Quality Indicator
        self.quality_lbl = QLabel("⏱ --ms")
        self.quality_lbl.setStyleSheet("font-family: monospace; color: #5a7a9a;")
        layout.addWidget(self.quality_lbl)

        # Cycle Time (Placeholder if needed)
        self.cycle_lbl = QLabel("Cycle: --s")
        self.cycle_lbl.setStyleSheet("font-family: monospace; color: #5a7a9a;")
        layout.addWidget(self.cycle_lbl)

        # User
        self.user_lbl = QLabel("👤 Guest")
        self.user_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.user_lbl)

        # Clock
        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self.clock_lbl)

    def update_page_title(self, title: str) -> None:
        self.title_lbl.setText(title.replace("_", " ").upper())

    def update_plc_status(self, connected: bool, msg: str = "") -> None:
        """
        Updates the PLC status label with color coding.
        """
        if not self.app_state.is_plc_configured:
            self.plc_status_lbl.setText("● Not Configured")
            self.plc_status_lbl.setStyleSheet("font-weight: 600; color: #f59e0b;")
        elif connected:
            profile = self.app_state.plc_profile or {}
            host = profile.get("host", "0.0.0.0")
            port = profile.get("port", 502)
            self.plc_status_lbl.setText(f"● {host}:{port}")
            self.plc_status_lbl.setStyleSheet("font-weight: 600; color: #22c55e;")
        else:
            txt = f"● Disconnected {msg}".strip()
            self.plc_status_lbl.setText(txt)
            self.plc_status_lbl.setStyleSheet("font-weight: 600; color: #ef4444;")

    def update_quality(self, quality: dict) -> None:
        """
        Shows response time: "⏱ {avg_ms}ms"
        Changes color: <100ms green, <500ms amber, >500ms red
        """
        avg_ms = quality.get("avg_response_ms", 0)
        self.quality_lbl.setText(f"⏱ {int(avg_ms)}ms")

        if avg_ms < 100:
            color = "#22c55e" # green
        elif avg_ms < 500:
            color = "#f59e0b" # amber
        else:
            color = "#ef4444" # red
        
        self.quality_lbl.setStyleSheet(f"font-family: monospace; color: {color};")

    def update_user(self, user: dict) -> None:
        self.user_lbl.setText(f"👤 {user.get('username', 'User')} ({user.get('role', 'OPERATOR')})")

    def _update_clock(self) -> None:
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))
