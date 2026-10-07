"""
settings_page.py — Universal PLC Monitor
Application-level settings: user management, themes, and system information.
Does not contain PLC hardware configuration.
"""
from __future__ import annotations

import os
import logging

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTabWidget, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFrame,
                             QGroupBox)
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState
from src.ui.theme_manager import ThemeManager
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.utils.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """
    Administrative interface for application settings and user management.
    """

    def __init__(self, app_state: AppState, on_plc_reconnect: callable) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_plc_reconnect = on_plc_reconnect
        self.setAccessibleName("Settings page")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Header
        title = QLabel("APPLICATION SETTINGS")
        title.setObjectName("settings_page_title")
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
        self.user_table.setAccessibleName("User accounts")
        self.user_table.setToolTip("Manage user accounts and roles")
        user_layout.addWidget(self.user_table)
        
        user_btns = QHBoxLayout()
        btn_add = QPushButton("+ Add User")
        btn_add.setObjectName("btn_success")
        btn_add.clicked.connect(self._on_add_user)
        user_btns.addWidget(btn_add)
        
        btn_del = QPushButton("🗑 Delete User")
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
        dark_card.setObjectName("settings_theme_card")
        dark_card.setProperty("theme", "dark")
        dark_card.setAccessibleName("Dark theme preview")
        dark_v = QVBoxLayout(dark_card)
        dark_v.addWidget(QLabel("DARK THEME"), 0, Qt.AlignmentFlag.AlignCenter)
        btn_dark = QPushButton("Apply Dark")
        btn_dark.setObjectName("btn_primary")
        btn_dark.setAccessibleName("Apply Dark theme")
        btn_dark.setToolTip("Switch the application to dark theme")
        btn_dark.clicked.connect(lambda: self._apply_theme("dark"))
        dark_v.addWidget(btn_dark)
        theme_cards.addWidget(dark_card)
        
        # Light Preview
        light_card = QFrame()
        light_card.setFixedSize(200, 150)
        light_card.setObjectName("settings_theme_card")
        light_card.setProperty("theme", "light")
        light_card.setAccessibleName("Light theme preview")
        light_v = QVBoxLayout(light_card)
        l_lbl = QLabel("LIGHT THEME")
        l_lbl.setObjectName("settings_theme_label")
        light_v.addWidget(l_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        btn_light = QPushButton("Apply Light")
        btn_light.setObjectName("btn_primary")
        btn_light.setAccessibleName("Apply Light theme")
        btn_light.setToolTip("Switch the application to light theme")
        btn_light.clicked.connect(lambda: self._apply_theme("light"))
        light_v.addWidget(btn_light)
        theme_cards.addWidget(light_card)
        
        # Store references for active state
        self._theme_cards = {"dark": dark_card, "light": light_card}
        
        theme_layout.addLayout(theme_cards)
        
        # Font Size Adjustment
        font_group = QGroupBox("Font Size")
        font_group.setAccessibleName("Font size adjustment")
        font_layout = QHBoxLayout(font_group)
        
        font_sizes = [("Small", 11), ("Medium", 13), ("Large", 15)]
        self._font_btns = []
        for label, size in font_sizes:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, s=size: self._apply_font_size(s))
            font_layout.addWidget(btn)
            self._font_btns.append(btn)
        
        theme_layout.addWidget(font_group)
        
        # High Contrast Mode
        contrast_group = QGroupBox("Accessibility")
        contrast_group.setAccessibleName("Accessibility options")
        contrast_layout = QHBoxLayout(contrast_group)
        
        self.high_contrast_btn = QPushButton("High Contrast: OFF")
        self.high_contrast_btn.setFixedHeight(32)
        self.high_contrast_btn.setCheckable(True)
        self.high_contrast_btn.setAccessibleName("Toggle high contrast mode")
        self.high_contrast_btn.setToolTip("Increase contrast for better visibility")
        self.high_contrast_btn.clicked.connect(self._toggle_high_contrast)
        contrast_layout.addWidget(self.high_contrast_btn)
        
        contrast_layout.addStretch()
        theme_layout.addWidget(contrast_group)
        
        theme_layout.addStretch()
        self.tabs.addTab(self.theme_tab, "🎨 Theme")

        # --- TAB: About ---
        self.about_tab = QWidget()
        about_layout = QVBoxLayout(self.about_tab)
        
        info_box = QGroupBox("System Information")
        info_layout = QVBoxLayout(info_box)
        self.info_lbl = QLabel("Loading info...")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setObjectName("settings_about_lbl")
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
        self._refresh_theme_cards()
        self._refresh_font_buttons()
        self._refresh_contrast_button()

    def _refresh_contrast_button(self) -> None:
        """Restore the persisted high-contrast toggle state."""
        is_on = self.app_state.config_repo.get_high_contrast()
        self.high_contrast_btn.setChecked(is_on)
        self.high_contrast_btn.setText(f"High Contrast: {'ON' if is_on else 'OFF'}")

    def _refresh_theme_cards(self) -> None:
        current = self.app_state.current_theme
        for theme, card in self._theme_cards.items():
            card.setProperty("active", theme == current)
            card.style().unpolish(card)
            card.style().polish(card)

    def _refresh_font_buttons(self) -> None:
        current_size = self.app_state.config_repo.get_font_size()
        font_sizes = [("Small", 11), ("Medium", 13), ("Large", 15)]
        for btn, (label, size) in zip(self._font_btns, font_sizes):
            btn.setProperty("active", size == current_size)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

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
            f"<b>Application:</b> {APP_NAME} v{APP_VERSION}<br>"
            f"<b>Build:</b> 2026.05.03 Production<br>"
            f"<b>Database:</b> {db_path} ({db_size:.1f} KB)<br>"
            f"<b>PLC Connection:</b> {'Online' if self.app_state.is_plc_connected else 'Offline'}<br>"
        )
        self.info_lbl.setText(info)
        
        # Load logs (assuming a write_log table exists)
        try:
            logs = self.app_state.db.fetchall(
                """
                SELECT w.timestamp, w.register_name, u.username
                FROM plc_write_log w
                LEFT JOIN users u ON w.operator_id = u.id
                ORDER BY w.id DESC LIMIT 10
                """
            )
            self.log_table.setRowCount(len(logs))
            for i, l in enumerate(logs):
                self.log_table.setItem(i, 0, QTableWidgetItem(l["timestamp"]))
                self.log_table.setItem(i, 1, QTableWidgetItem(l["register_name"]))
                self.log_table.setItem(i, 2, QTableWidgetItem(l["username"] or f"ID:{l.get('operator_id')}"))
        except Exception as e:
            logger.error("Failed to load audit trail: %s", e)

    def _on_add_user(self) -> None:
        # Simplification: in real app this would show an inline form or dialog
        logger.info("Add user clicked")

    def _on_delete_user(self) -> None:
        curr = self.user_table.currentRow()
        if curr < 0: return
        
        uid = int(self.user_table.item(curr, 0).text())
        uname = self.user_table.item(curr, 1).text()
        
        if uid == (self.app_state.current_user or {}).get("id"):
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
        self._refresh_theme_cards()
        logger.info("Theme changed to %s", theme)

    def _apply_font_size(self, size: int) -> None:
        """Apply font size adjustment to the entire application."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            font = app.font()
            font.setPointSize(size)
            app.setFont(font)
            self.app_state.config_repo.set_font_size(size)
            self._refresh_font_buttons()
            logger.info("Font size changed to %d", size)

    def _toggle_high_contrast(self) -> None:
        """Toggle high contrast mode."""
        is_on = self.high_contrast_btn.isChecked()
        self.high_contrast_btn.setText(f"High Contrast: {'ON' if is_on else 'OFF'}")

        # Always re-apply base theme first to avoid accumulation
        ThemeManager.apply(self.app_state.current_theme)
        ThemeManager.apply_high_contrast(is_on)
        self.app_state.config_repo.set_high_contrast(is_on)
        logger.info("High contrast mode: %s", is_on)
