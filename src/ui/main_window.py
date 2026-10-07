"""
main_window.py — Universal PLC Monitor
Main container for the application UI and connection lifecycle.
"""
from __future__ import annotations

import logging
import time
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut

from src.ui.app_state import AppState
from src.ui.theme_manager import ThemeManager

# Components
from src.ui.components.sidebar import Sidebar
from src.ui.components.top_bar import TopBar
from src.ui.components.breadcrumb import Breadcrumb
from src.ui.components.status_bar import StatusBar
from src.ui.components.toast import ToastManager

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
    PAGE_IO_LIST, PAGE_REPORTS, PAGE_SETTINGS, NAV_ITEMS
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self.setWindowTitle("PLC Monitor")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        self._init_ui()
        self._connect_signals()
        self._init_shortcuts()
        
        # Toast notification manager
        self.toast = ToastManager.instance()

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

        # Breadcrumb
        self.breadcrumb = Breadcrumb()
        self.breadcrumb.crumb_clicked.connect(self.navigate_to)
        right_layout.addWidget(self.breadcrumb)

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

    def on_setup_complete(self) -> None:
        self.app_state.config_repo.mark_setup_complete()
        self.page_stack.setCurrentIndex(1) # Go to login

    def on_login_success(self, user: dict) -> None:
        self.app_state.set_user(user)
        self.sidebar.rebuild_for_role(user["role"])
        self.sidebar.setVisible(True)
        self.top_bar.update_user(user)
        self.navigate_to(PAGE_MODEL)
        self.toast.success(f"Welcome, {user.get('username', 'User')}!")

        # Restart PLC connection after login if configured
        if self.app_state.is_plc_configured:
            self._start_plc_connection()

    def _page_allowed(self, page_name: str) -> bool:
        """Role check derived from NAV_ITEMS (single source of truth)."""
        role = str((self.app_state.current_user or {}).get("role", "")).upper()
        for pid, _icon, _label, roles in NAV_ITEMS:
            if pid == page_name:
                return role in [r.upper() for r in roles]
        return True

    def navigate_to(self, page_name: str) -> None:
        # Build page map dynamically from actual stack widgets
        page_map = {}
        _page_widgets = {
            PAGE_MODEL: self.model_page,
            PAGE_TEST: self.test_page,
            PAGE_MANUAL: self.manual_page,
            PAGE_CONFIG: self.config_page,
            PAGE_IO_LIST: self.io_page,
            PAGE_REPORTS: self.reports_page,
            PAGE_SETTINGS: self.settings_page,
        }
        for name, widget in _page_widgets.items():
            idx = self.page_stack.indexOf(widget)
            if idx >= 0:
                page_map[name] = idx

        # Access gate — must run BEFORE any side effect (on_page_hidden),
        # otherwise a denied navigation silently stops the current page's
        # timers while it stays visible.
        if not self._page_allowed(page_name):
            logger.warning(
                "Access denied to '%s' page for role %s",
                page_name,
                (self.app_state.current_user or {}).get("role", "?"),
            )
            ToastManager.instance().warning("You do not have permission to open that page.")
            return

        # Notify previous page of hidden
        prev_widget = self.page_stack.currentWidget()
        if prev_widget and hasattr(prev_widget, "on_page_hidden"):
            prev_widget.on_page_hidden()

        idx = page_map.get(page_name, self.page_stack.indexOf(self.model_page))
        self.page_stack.setCurrentIndex(idx)
        self.sidebar.set_active(page_name)
        self.top_bar.update_page_title(page_name)
        self.breadcrumb.update_path(page_name)

        # Notify page visibility
        current_page = self.page_stack.widget(idx)
        if hasattr(current_page, "on_page_shown"):
            current_page.on_page_shown()

    def on_theme_toggle(self) -> None:
        new_theme = self.app_state.toggle_theme()
        ThemeManager.apply(new_theme)
        self.app_state.config_repo.set_theme(new_theme)

    def on_logout(self) -> None:
        if self.app_state.write_manager:
            self.app_state.write_manager.stop()
        if self.app_state.connection_manager:
            self.app_state.connection_manager.stop()
        self.app_state.clear_user()
        self.sidebar.setVisible(False)
        self.page_stack.setCurrentIndex(1)
        self.login_overlay.reset()
        self.toast.info("Logged out successfully")

    def on_plc_reconnect(self) -> None:
        """Restart PLC connection with current profile."""
        if self.app_state.connection_manager:
            self.app_state.connection_manager.stop()
        self._start_plc_connection()

    def _start_plc_connection(self) -> None:
        try:
            profile = self.app_state.profile_repo.get_profile()
            self.app_state.refresh_message_config()
            
            # Disconnect old signals if reconnecting
            old_mgr = self.app_state.connection_manager
            if old_mgr:
                try:
                    old_mgr.connection_state_changed.disconnect(self._on_plc_state_changed)
                    old_mgr.message_changed.disconnect(self.status_bar.show_message)
                    old_mgr.quality_updated.disconnect(self.top_bar.update_quality)
                except (TypeError, RuntimeError):
                    pass  # Signal was never connected
                try:
                    old_mgr.comm_error.disconnect(self._on_plc_comm_error)
                except (TypeError, RuntimeError):
                    pass

            # Reuse PLCDataModel across reconnects
            d_model = self.app_state.data_model
            if d_model is None:
                d_model = PLCDataModel()
                self.app_state.data_model = d_model
            
            driver = PLCDriverFactory.create(profile)
            
            conn_mgr = ConnectionManager(
                profile,
                self.app_state.poll_registers,
                self.app_state.message_register,
                self.app_state.message_lookup,
                d_model,
                driver,
                blocks_to_poll=self.app_state.refresh_blocks(),
            )
            write_mgr = PLCWriteManager(driver, self.app_state.db, self.app_state)
            
            self.app_state.connection_manager = conn_mgr
            self.app_state.write_manager = write_mgr
            
            conn_mgr.connection_state_changed.connect(self._on_plc_state_changed)
            conn_mgr.message_changed.connect(self.status_bar.show_message)
            conn_mgr.quality_updated.connect(self.top_bar.update_quality)
            conn_mgr.comm_error.connect(self._on_plc_comm_error)

            # Control-write outcomes (async — result arrives from the write task)
            write_mgr.write_success.connect(self._on_write_success)
            write_mgr.write_failed.connect(self._on_write_failed)
            
            conn_mgr.start()
            logger.info("PLC connection background thread started")
        except Exception as e:
            logger.warning(f"PLC connection failed to start: {e}")
            self.top_bar.update_plc_status(False, str(e))

    def _on_plc_state_changed(self, connected: bool) -> None:
        self.app_state.is_plc_connected = connected
        self.top_bar.update_plc_status(connected)
        self.sidebar.set_connection_status(connected)
        
        if connected:
            self.toast.success("PLC connected successfully")
        else:
            self.toast.warning("PLC disconnected")
        
        # Notify all pages
        for i in range(2, self.page_stack.count()):
            w = self.page_stack.widget(i)
            if hasattr(w, "on_plc_state_changed"):
                w.on_plc_state_changed(connected)

    def _on_plc_comm_error(self, message: str) -> None:
        """
        Handle a PLC communication error. Throttled to one toast per
        5 seconds — the poll loop can emit the same failure every cycle
        and must not flood the UI. Full detail always goes to the log.
        """
        logger.warning("PLC comm error: %s", message)
        now = time.monotonic()
        if now - getattr(self, "_last_comm_error_ts", 0.0) >= 5.0:
            self._last_comm_error_ts = now
            self.toast.error(message)

    def _on_write_success(self, name: str, address: int, value: object) -> None:
        """Async control-write result: success feedback for TEST/MANUAL pages."""
        logger.info("PLC write OK: %s (addr=%s value=%s)", name, address, value)
        self.toast.success(f"Write OK — {name}: {value}")

    def _on_write_failed(self, name: str, address: int, error: str) -> None:
        """Async control-write result: failure feedback for TEST/MANUAL pages."""
        logger.warning("PLC write failed: %s (addr=%s): %s", name, address, error)
        self.toast.error(f"Write failed — {name}: {error}")

    def _init_shortcuts(self) -> None:
        """Initialize keyboard shortcuts for page navigation and test controls."""
        nav_shortcuts = [
            ("Ctrl+1", PAGE_MODEL),
            ("Ctrl+2", PAGE_TEST),
            ("Ctrl+3", PAGE_MANUAL),
            ("Ctrl+4", PAGE_CONFIG),
            ("Ctrl+5", PAGE_IO_LIST),
            ("Ctrl+6", PAGE_REPORTS),
            ("Ctrl+7", PAGE_SETTINGS),
        ]
        for key, page in nav_shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda p=page: self.navigate_to(p))
        
        # Test page shortcuts (L-05)
        start_shortcut = QShortcut(QKeySequence("F5"), self)
        start_shortcut.activated.connect(self._trigger_start_test)
        
        stop_shortcut = QShortcut(QKeySequence("F9"), self)
        stop_shortcut.activated.connect(self._trigger_stop_test)

    def _trigger_start_test(self) -> None:
        """Trigger START TEST if test page is active."""
        if self.page_stack.currentWidget() == self.test_page:
            self.test_page._on_start_clicked()

    def _trigger_stop_test(self) -> None:
        """Trigger STOP if test page is active."""
        if self.page_stack.currentWidget() == self.test_page:
            self.test_page._on_stop_clicked()

    def keyPressEvent(self, event) -> None:
        """Handle additional keyboard shortcuts."""
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        """Auto-collapse sidebar when window is narrow."""
        super().resizeEvent(event)
        width = event.size().width()
        if width < 1100 and self.sidebar._is_expanded:
            self.sidebar._toggle_expand()
        elif width >= 1100 and not self.sidebar._is_expanded and self.sidebar.isVisible():
            pass
