"""
top_bar.py — Universal PLC Monitor
Top bar showing application status, PLC connectivity, and active user.
"""
from __future__ import annotations

import logging
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PyQt6.QtCore import QTimer
from src.utils.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class TopBar(QFrame):
    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("top_bar")
        self.setAccessibleName("Application top bar")
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
        self.app_name_lbl.setObjectName("app_name_lbl")
        self.app_name_lbl.setAccessibleName("Application name")
        layout.addWidget(self.app_name_lbl)

        # Center: Page Title
        self.title_lbl = QLabel("HOME")
        self.title_lbl.setObjectName("top_bar_title")
        self.title_lbl.setAccessibleName("Current page title")
        layout.addWidget(self.title_lbl)

        layout.addStretch()

        # PLC Status Pill
        self.plc_pill = QFrame()
        self.plc_pill.setObjectName("plc_status_pill")
        pill_lay = QHBoxLayout(self.plc_pill)
        pill_lay.setContentsMargins(10, 3, 10, 3)
        pill_lay.setSpacing(6)

        self.plc_status_dot = QLabel("●")
        self.plc_status_dot.setObjectName("plc_status_dot")
        self.plc_status_dot.setAccessibleName("PLC connection indicator")
        pill_lay.addWidget(self.plc_status_dot)

        self.plc_status_lbl = QLabel("Not Configured")
        self.plc_status_lbl.setObjectName("plc_status_lbl")
        self.plc_status_lbl.setAccessibleName("PLC connection status")
        self.plc_status_lbl.setToolTip("Shows current PLC connection state")
        pill_lay.addWidget(self.plc_status_lbl)
        self.plc_pill.setMaximumWidth(220)
        layout.addWidget(self.plc_pill)

        # Quality Indicator
        self.quality_dot = QLabel("●")
        self.quality_dot.setObjectName("quality_dot")
        self.quality_dot.setAccessibleName("PLC connection quality indicator")
        self.quality_dot.setFixedWidth(14)
        layout.addWidget(self.quality_dot)

        self.quality_lbl = QLabel("--ms")
        self.quality_lbl.setObjectName("quality_lbl")
        self.quality_lbl.setAccessibleName("PLC response time")
        self.quality_lbl.setToolTip("Average PLC communication response time in milliseconds")
        layout.addWidget(self.quality_lbl)

        # Cycle Time - only visible on test page (M-01)
        self.cycle_lbl = QLabel("Cycle: --s")
        self.cycle_lbl.setObjectName("cycle_lbl")
        self.cycle_lbl.setAccessibleName("Cycle time")
        self.cycle_lbl.setToolTip("Current test cycle duration")
        self.cycle_lbl.setVisible(False)
        layout.addWidget(self.cycle_lbl)

        # User Avatar
        self.user_avatar = QLabel("G")
        self.user_avatar.setObjectName("user_avatar")
        self.user_avatar.setFixedSize(28, 28)
        self.user_avatar.setAccessibleName("User avatar")
        self.user_avatar.setToolTip("User initials")
        layout.addWidget(self.user_avatar)

        # User
        self.user_lbl = QLabel("Guest")
        self.user_lbl.setObjectName("user_lbl")
        self.user_lbl.setAccessibleName("Logged in user")
        self.user_lbl.setToolTip("Current user and role")
        layout.addWidget(self.user_lbl)

        # Clock
        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setObjectName("clock_lbl")
        self.clock_lbl.setAccessibleName("Current time")
        layout.addWidget(self.clock_lbl)

    def update_page_title(self, title: str) -> None:
        self.title_lbl.setText(title.replace("_", " ").upper())
        # Show cycle label only on test page
        is_test = title.lower() == "test"
        self.cycle_lbl.setVisible(is_test)

    def update_plc_status(self, connected: bool, msg: str = "") -> None:
        online = bool(connected)
        self.plc_pill.setProperty("online", online)
        if not self.app_state.is_plc_configured:
            self.plc_status_lbl.setText("Not Configured")
            self.plc_status_lbl.setToolTip("No PLC connection configured")
            self.plc_status_lbl.setProperty("connected", None)
        elif connected:
            profile = self.app_state.plc_profile or {}
            host = profile.get("host", "0.0.0.0")
            port = profile.get("port", 502)
            status_text = f"● ONLINE  {host}:{port}"
            self.plc_status_lbl.setText(status_text)
            self.plc_status_lbl.setToolTip(f"Connected to PLC at {host}:{port}")
            self.plc_status_lbl.setProperty("connected", True)
        else:
            txt = f"● OFFLINE  {msg}".strip()
            self.plc_status_lbl.setText(txt)
            self.plc_status_lbl.setToolTip(txt)
            self.plc_status_lbl.setProperty("connected", False)

        self.plc_pill.style().unpolish(self.plc_pill)
        self.plc_pill.style().polish(self.plc_pill)
        self.plc_status_lbl.style().unpolish(self.plc_status_lbl)
        self.plc_status_lbl.style().polish(self.plc_status_lbl)

    def update_quality(self, quality: dict) -> None:
        avg_ms = quality.get("avg_response_ms") or 0
        self.quality_lbl.setText(f"{int(avg_ms)}ms")

        if avg_ms < 100:
            level = "good"
        elif avg_ms < 500:
            level = "medium"
        else:
            level = "poor"
        self.quality_dot.setProperty("quality", level)
        self.quality_dot.style().unpolish(self.quality_dot)
        self.quality_dot.style().polish(self.quality_dot)

    def update_user(self, user: dict) -> None:
        username = user.get('username', 'User')
        role = user.get('role', 'OPERATOR')
        self.user_lbl.setText(f"{username} ({role})")

        initials = username[:2].upper()
        self.user_avatar.setText(initials)

    def _update_clock(self) -> None:
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))
