"""
main_window.py — Universal PLC Monitor
Main container for the application UI and connection lifecycle.
"""
from __future__ import annotations

import logging
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState
from src.ui.theme_manager import ThemeManager

# Components
from src.ui.components.sidebar import Sidebar
from src.ui.components.top_bar import TopBar
from src.ui.components.status_bar import StatusBar

# Pages
from src.ui.pages.setup_wizard_page import SetupWizardPage
from src.ui.login_overlay import LoginOverlay
from src.ui.pages.model_page import ModelPage
from src.ui.pages.test_page import TestPage
from src.ui.pages.manual_page import ManualPage
from src.ui.pages.settings_page import SettingsPage
from src.ui.pages.io_list_page import IoListPage
from src.ui.pages.reports_page import ReportsPage
from src.ui.pages.config_page import ConfigPage

# PLC logic
from src.plc.driver_factory import PLCDriverFactory
from src.plc.data_model import PLCDataModel
from src.plc.connection_manager import ConnectionManager
from src.plc.write_manager import PLCWriteManager

from src.utils.constants import (
    PAGE_MODEL, PAGE_TEST, PAGE_MANUAL, PAGE_CONFIG,
    PAGE_IO_LIST, PAGE_REPORTS, PAGE_SETTINGS
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self.setWindowTitle("PLC Monitor")
        self.setMinimumSize(1200, 800)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = Sidebar(self.app_state)
        self.sidebar.setVisible(False)
        root_layout.addWidget(self.sidebar)

        # 2. Main Area (Right)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        root_layout.addWidget(right_container, 1)

        # Top Bar
        self.top_bar = TopBar(self.app_state)
        right_layout.addWidget(self.top_bar)

        # Page Stack
        self.page_stack = QStackedWidget()
        right_layout.addWidget(self.page_stack, 1)

        # Status Bar
        self.status_bar = StatusBar(self.app_state)
        right_layout.addWidget(self.status_bar)

        # Initialize Pages
        self.setup_wizard = SetupWizardPage(self.app_state)
        self.login_overlay = LoginOverlay(self.app_state, self.on_login_success)
        
        self.model_page = ModelPage(self.app_state, lambda: self.navigate_to(PAGE_TEST))
        self.test_page = TestPage(self.app_state)
        self.manual_page = ManualPage(self.app_state)
        self.config_page = ConfigPage(self.app_state, self.on_plc_reconnect) # Admin only
        self.io_page = IoListPage(self.app_state)
        self.reports_page = ReportsPage(self.app_state)
        self.settings_page = SettingsPage(self.app_state, self.on_plc_reconnect)

        # Add to stack in order
        self.page_stack.addWidget(self.setup_wizard) # 0
        self.page_stack.addWidget(self.login_overlay) # 1
        self.page_stack.addWidget(self.model_page)    # 2
        self.page_stack.addWidget(self.test_page)     # 3
        self.page_stack.addWidget(self.manual_page)   # 4
        self.page_stack.addWidget(self.config_page)   # 5
        self.page_stack.addWidget(self.io_page)       # 6
        self.page_stack.addWidget(self.reports_page)  # 7
        self.page_stack.addWidget(self.settings_page) # 8

    def _connect_signals(self) -> None:
        self.sidebar.nav_clicked.connect(self.navigate_to)
        self.sidebar.theme_toggle.connect(self.on_theme_toggle)
        self.sidebar.logout.connect(self.on_logout)
        self.setup_wizard.setup_complete.connect(self.on_setup_complete)

    def on_startup(self) -> None:
        """Determines the first screen based on configuration."""
        if self.app_state.config_repo.is_first_run():
            self.page_stack.setCurrentIndex(0) # Setup Wizard
            self.sidebar.setVisible(False)
        else:
            self.page_stack.setCurrentIndex(1) # Login Overlay
            self.sidebar.setVisible(False)
            if self.app_state.is_plc_configured:
                self._start_plc_connection()

    def on_setup_complete(self) -> None:
        self.app_state.config_repo.mark_setup_complete()
        self.page_stack.setCurrentIndex(1) # Go to login

    def on_login_success(self, user: dict) -> None:
        self.app_state.set_user(user)
        self.sidebar.rebuild_for_role(user["role"])
        self.sidebar.setVisible(True)
        self.top_bar.update_user(user)
        self.navigate_to(PAGE_MODEL)

    def navigate_to(self, page_name: str) -> None:
        page_map = {
            PAGE_MODEL: 2, PAGE_TEST: 3,
            PAGE_MANUAL: 4, PAGE_CONFIG: 5,
            PAGE_IO_LIST: 6, PAGE_REPORTS: 7,
            PAGE_SETTINGS: 8,
        }
        
        if page_name == PAGE_CONFIG:
            if not self.app_state.can_access_config():
                logger.warning("Access denied to CONFIG page for user role")
                return

        idx = page_map.get(page_name, 2)
        self.page_stack.setCurrentIndex(idx)
        self.sidebar.set_active(page_name)
        self.top_bar.update_page_title(page_name)

        # Notify page visibility
        current_page = self.page_stack.widget(idx)
        if hasattr(current_page, "on_page_shown"):
            current_page.on_page_shown()

    def on_theme_toggle(self) -> None:
        new_theme = self.app_state.toggle_theme()
        ThemeManager.apply(new_theme)
        self.app_state.config_repo.set_theme(new_theme)

    def on_logout(self) -> None:
        if self.app_state.connection_manager:
            self.app_state.connection_manager.stop()
        self.app_state.clear_user()
        self.sidebar.setVisible(False)
        self.page_stack.setCurrentIndex(1)
        self.login_overlay.reset()

    def on_plc_reconnect(self) -> None:
        """Restart PLC connection with current profile."""
        if self.app_state.connection_manager:
            self.app_state.connection_manager.stop()
        self._start_plc_connection()

    def _start_plc_connection(self) -> None:
        try:
            profile = self.app_state.profile_repo.get_profile()
            self.app_state.refresh_message_config()
            
            # Create shared driver and model
            driver = PLCDriverFactory.create(profile)
            d_model = PLCDataModel()
            
            conn_mgr = ConnectionManager(
                profile,
                self.app_state.poll_registers,
                self.app_state.message_register,
                self.app_state.message_lookup,
                d_model,
                driver
            )
            write_mgr = PLCWriteManager(driver, self.app_state.db, self.app_state)
            
            self.app_state.connection_manager = conn_mgr
            self.app_state.write_manager = write_mgr
            
            conn_mgr.connection_state_changed.connect(self._on_plc_state_changed)
            conn_mgr.message_changed.connect(self.status_bar.show_message)
            conn_mgr.quality_updated.connect(self.top_bar.update_quality)
            
            conn_mgr.start()
            logger.info("PLC connection background thread started")
        except Exception as e:
            logger.warning(f"PLC connection failed to start: {e}")
            self.top_bar.update_plc_status(False, str(e))

    def _on_plc_state_changed(self, connected: bool) -> None:
        self.app_state.is_plc_connected = connected
        self.top_bar.update_plc_status(connected)
        
        # Notify all pages
        for i in range(2, self.page_stack.count()):
            w = self.page_stack.widget(i)
            if hasattr(w, "on_plc_state_changed"):
                w.on_plc_state_changed(connected)
