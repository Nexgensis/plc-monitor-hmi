"""
sidebar.py — Universal PLC Monitor
Navigation sidebar with role-based access control.
"""
from __future__ import annotations

import logging
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QPushButton, QLabel, 
                             QSpacerItem, QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt
from src.utils.constants import NAV_ITEMS, THEME_DARK

logger = logging.getLogger(__name__)


class Sidebar(QFrame):
    nav_clicked = pyqtSignal(str)
    theme_toggle = pyqtSignal()
    logout = pyqtSignal()

    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("sidebar")
        self.setFixedWidth(68)

        self._buttons: dict[str, QPushButton] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Main Nav Items
        for page_id, icon, label, roles in NAV_ITEMS:
            btn = self._create_nav_button(page_id, icon, label)
            self._buttons[page_id] = btn
            layout.addWidget(btn)

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Bottom items
        self.theme_btn = self._create_nav_button("theme", "🌓", "THEME")
        self.theme_btn.clicked.disconnect()
        self.theme_btn.clicked.connect(self.theme_toggle.emit)
        layout.addWidget(self.theme_btn)

        self.logout_btn = self._create_nav_button("logout", "🚪", "LOGOUT")
        self.logout_btn.clicked.disconnect()
        self.logout_btn.clicked.connect(self.logout.emit)
        layout.addWidget(self.logout_btn)

    def _create_nav_button(self, page_id: str, icon: str, label: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("nav_btn")
        btn.setFixedSize(52, 52)
        btn.setProperty("active", False)

        btn_layout = QVBoxLayout(btn)
        btn_layout.setContentsMargins(0, 4, 0, 4)
        btn_layout.setSpacing(2)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent; border: none;")

        label_lbl = QLabel(label)
        label_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_lbl.setStyleSheet("font-size: 8px; font-weight: bold; background: transparent; border: none;")

        btn_layout.addWidget(icon_lbl)
        btn_layout.addWidget(label_lbl)

        btn.clicked.connect(lambda: self.nav_clicked.emit(page_id))
        return btn

    def rebuild_for_role(self, role: str) -> None:
        """Show/hide items based on role access list in NAV_ITEMS."""
        for page_id, icon, label, roles in NAV_ITEMS:
            if page_id in self._buttons:
                self._buttons[page_id].setVisible(role in roles)

    def set_active(self, page_name: str) -> None:
        """Highlight the active navigation item."""
        for name, btn in self._buttons.items():
            is_active = (name == page_name)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
