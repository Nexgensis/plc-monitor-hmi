"""
ui/app_window.py
Main Shell Window managing the navigation stack for a seamless Single Window Application (SWA).
"""

import logging
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from database.db_manager import Database
from ui.app_state import AppState

logger = logging.getLogger(__name__)

class AppWindow(QMainWindow):
    """
    The primary shell of the application. 
    It hosts a QStackedWidget and coordinates transitions between Login, Dashboard, and Settings.
    """
    def __init__(self, db: Database, app_state: AppState) -> None:
        super().__init__()
        self._db = db
        self._app_state = app_state
        
        self.setWindowTitle("PLC Monitor — Switch Test Station")
        # Always fill the screen; works on any resolution
        self.setMinimumSize(1024, 600)   # safety lower bound
        self.showMaximized()
        
        # Central widget and stack logic
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        self._init_screens()
        
    def _init_screens(self) -> None:
        """Initialize and register all primary screens in the stack."""
        from ui.login_screen import LoginWindow
        # We pass self as a router reference to allow screens to trigger navigations
        self.login_screen = LoginWindow(self._db, self._app_state, self)
        self.stack.addWidget(self.login_screen)
        
        # Dashboard and Settings will be initialized on demand or when needed
        # to ensure they have the latest AppState (like selected model)
        self.main_dashboard = None
        self.settings_screen = None
        
        # Start at login
        self.stack.setCurrentWidget(self.login_screen)

    def show_login(self) -> None:
        self.stack.setCurrentWidget(self.login_screen)
        
    def show_dashboard(self) -> None:
        """Transitions to the main functional dashboard."""
        from ui.main_window import MainWindow
        
        # Re-initialize dashboard if it doesn't exist or if state changed significantly
        if self.main_dashboard:
            self.stack.removeWidget(self.main_dashboard)
            self.main_dashboard.deleteLater()
            
        self.main_dashboard = MainWindow(self._db, self._app_state, self)
        self.stack.addWidget(self.main_dashboard)
        self.stack.setCurrentWidget(self.main_dashboard)

    def show_settings(self) -> None:
        """Transitions to the administrative settings hub."""
        from ui.settings_window import SettingsWindow
        
        if self.settings_screen:
            self.stack.removeWidget(self.settings_screen)
            self.settings_screen.deleteLater()
            
        self.settings_screen = SettingsWindow(self._db, self._app_state, self)
        # Assuming SettingsWindow is now a QWidget with a 'back' functional trigger
        self.stack.addWidget(self.settings_screen)
        self.stack.setCurrentWidget(self.settings_screen)
        
    def show_manual_test(self, conn_mgr) -> None:
        from ui.manual_test_window import ManualTestWindow
        if hasattr(self, 'manual_screen') and self.manual_screen:
            self.stack.removeWidget(self.manual_screen)
            self.manual_screen.deleteLater()
        self.manual_screen = ManualTestWindow(self._db, self._app_state, conn_mgr, self)
        self.stack.addWidget(self.manual_screen)
        self.stack.setCurrentWidget(self.manual_screen)

    def show_reports(self) -> None:
        from ui.dialogs.reports_dialog import ReportsDialog
        if hasattr(self, 'reports_screen') and self.reports_screen:
            self.stack.removeWidget(self.reports_screen)
            self.reports_screen.deleteLater()
        self.reports_screen = ReportsDialog(self._db, self._app_state, self)
        self.stack.addWidget(self.reports_screen)
        self.stack.setCurrentWidget(self.reports_screen)

    def show_comments(self) -> None:
        from ui.dialogs.comments_dialog import CommentsDialog
        if hasattr(self, 'comments_screen') and self.comments_screen:
            self.stack.removeWidget(self.comments_screen)
            self.comments_screen.deleteLater()
        self.comments_screen = CommentsDialog(self._db, self._app_state, self)
        self.stack.addWidget(self.comments_screen)
        self.stack.setCurrentWidget(self.comments_screen)

    def show_password_utility(self) -> None:
        from ui.dialogs.password_utility import PasswordUtilityDialog
        if hasattr(self, 'pwd_screen') and self.pwd_screen:
            self.stack.removeWidget(self.pwd_screen)
            self.pwd_screen.deleteLater()
        self.pwd_screen = PasswordUtilityDialog(self._db, self._app_state, self)
        self.stack.addWidget(self.pwd_screen)
        self.stack.setCurrentWidget(self.pwd_screen)

    def go_back(self) -> None:
        """Universal back navigation logic."""
        if self.stack.currentWidget() == getattr(self, 'main_dashboard', None):
            self.show_login()
        elif self.stack.currentWidget() == getattr(self, 'settings_screen', None):
            if self._app_state.current_model: self.show_dashboard()
            else: self.show_login()
        else:
            self.show_login()
