"""
settings_page.py — Universal PLC Monitor
Application-level settings: user management, themes, and system information.
Does not contain PLC hardware configuration.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTabWidget, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFrame,
                             QLineEdit, QComboBox, QProgressBar, QGroupBox)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor

from src.ui.app_state import AppState
from src.ui.theme_manager import ThemeManager
from src.ui.dialogs.confirm_dialog import ConfirmDialog

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """
    Administrative interface for application settings and user management.
    """

    def __init__(self, app_state: AppState, on_plc_reconnect: callable) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_plc_reconnect = on_plc_reconnect
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Header
        title = QLabel("APPLICATION SETTINGS")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e8f0fa;")
        layout.addWidget(title)

        # 2. Main Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- TAB: Users ---
        self.user_tab = QWidget()
        user_layout = QVBoxLayout(self.user_tab)
        
        self.user_table = QTableWidget(0, 5)
        self.user_table.setHorizontalHeaderLabels(["#", "Username", "Role", "Created", "Last Login"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        user_layout.addWidget(self.user_table)
        
        user_btns = QHBoxLayout()
        btn_add = QPushButton("+ Add User")
        btn_add.setObjectName("btn_success")
        btn_add.clicked.connect(self._on_add_user)
        user_btns.addWidget(btn_add)
        
        btn_del = QPushButton("Delete User")
        btn_del.setObjectName("btn_danger")
        btn_del.clicked.connect(self._on_delete_user)
        user_btns.addWidget(btn_del)
        
        user_btns.addStretch()
        user_layout.addLayout(user_btns)
        
        self.tabs.addTab(self.user_tab, "👤 Users & Roles")

        # --- TAB: Theme ---
        self.theme_tab = QWidget()
        theme_layout = QVBoxLayout(self.theme_tab)
        theme_layout.setSpacing(30)
        theme_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        theme_cards = QHBoxLayout()
        
        # Dark Preview
        dark_card = QFrame()
        dark_card.setFixedSize(200, 150)
        dark_card.setStyleSheet("background: #0f172a; border: 2px solid #3b82f6; border-radius: 8px;")
        dark_v = QVBoxLayout(dark_card)
        dark_v.addWidget(QLabel("DARK THEME"), 0, Qt.AlignmentFlag.AlignCenter)
        btn_dark = QPushButton("Apply Dark")
        btn_dark.setObjectName("btn_primary")
        btn_dark.clicked.connect(lambda: self._apply_theme("dark"))
        dark_v.addWidget(btn_dark)
        theme_cards.addWidget(dark_card)
        
        # Light Preview
        light_card = QFrame()
        light_card.setFixedSize(200, 150)
        light_card.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;")
        light_v = QVBoxLayout(light_card)
        l_lbl = QLabel("LIGHT THEME")
        l_lbl.setStyleSheet("color: #1e293b;")
        light_v.addWidget(l_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        btn_light = QPushButton("Apply Light")
        btn_light.setObjectName("btn_primary")
        btn_light.clicked.connect(lambda: self._apply_theme("light"))
        light_v.addWidget(btn_light)
        theme_cards.addWidget(light_card)
        
        theme_layout.addLayout(theme_cards)
        self.tabs.addTab(self.theme_tab, "🎨 Theme")

        # --- TAB: About ---
        self.about_tab = QWidget()
        about_layout = QVBoxLayout(self.about_tab)
        
        info_box = QGroupBox("System Information")
        info_layout = QVBoxLayout(info_box)
        self.info_lbl = QLabel("Loading info...")
        self.info_lbl.setWordWrap(True)
        info_layout.addWidget(self.info_lbl)
        about_layout.addWidget(info_box)
        
        log_box = QGroupBox("Audit Trail: PLC Write Log (Last 10)")
        log_layout = QVBoxLayout(log_box)
        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["Time", "Command", "User"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        log_layout.addWidget(self.log_table)
        about_layout.addWidget(log_box)
        
        about_layout.addStretch()
        self.tabs.addTab(self.about_tab, "ℹ About")

    def on_page_shown(self) -> None:
        self._refresh_users()
        self._refresh_about()

    def _refresh_users(self) -> None:
        users = self.app_state.user_repo.get_all_users()
        self.user_table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.user_table.setItem(i, 0, QTableWidgetItem(str(u["id"])))
            self.user_table.setItem(i, 1, QTableWidgetItem(u["username"]))
            self.user_table.setItem(i, 2, QTableWidgetItem(u["role"]))
            self.user_table.setItem(i, 3, QTableWidgetItem(str(u["created_at"])))
            self.user_table.setItem(i, 4, QTableWidgetItem(str(u["last_login"] or "Never")))

    def _refresh_about(self) -> None:
        # Build info string
        db_path = self.app_state.db.db_path if self.app_state.db else "N/A"
        db_size = os.path.getsize(db_path) / 1024 if os.path.exists(db_path) else 0
        
        info = (
            f"<b>Application:</b> PLC Monitor v4.0.0<br>"
            f"<b>Build:</b> 2026.05.03 Production<br>"
            f"<b>Database:</b> {db_path} ({db_size:.1f} KB)<br>"
            f"<b>PLC Connection:</b> {'Online' if self.app_state.is_plc_connected else 'Offline'}<br>"
        )
        self.info_lbl.setText(info)
        
        # Load logs (assuming a write_log table exists)
        try:
            logs = self.app_state.db.fetchall(
                "SELECT timestamp, register_name, operator_id FROM plc_write_log ORDER BY id DESC LIMIT 10"
            )
            self.log_table.setRowCount(len(logs))
            for i, l in enumerate(logs):
                self.log_table.setItem(i, 0, QTableWidgetItem(l["timestamp"]))
                self.log_table.setItem(i, 1, QTableWidgetItem(l["register_name"]))
                self.log_table.setItem(i, 2, QTableWidgetItem(str(l["operator_id"])))
        except:
            pass

    def _on_add_user(self) -> None:
        # Simplification: in real app this would show an inline form or dialog
        logger.info("Add user clicked")

    def _on_delete_user(self) -> None:
        curr = self.user_table.currentRow()
        if curr < 0: return
        
        uid = int(self.user_table.item(curr, 0).text())
        uname = self.user_table.item(curr, 1).text()
        
        if uid == self.app_state.current_user["id"]:
            ConfirmDialog.show_error(self, "Access Denied", "You cannot delete your own account.")
            return
            
        if ConfirmDialog.ask(self, "Delete User", f"Are you sure you want to delete user '{uname}'?"):
            try:
                self.app_state.user_repo.delete_user(uid)
                self._refresh_users()
            except Exception as e:
                ConfirmDialog.show_error(self, "Delete Failed", str(e))

    def _apply_theme(self, theme: str) -> None:
        ThemeManager.apply(theme)
        self.app_state.config_repo.set_theme(theme)
        self.app_state.current_theme = theme
        logger.info("Theme changed to %s", theme)
