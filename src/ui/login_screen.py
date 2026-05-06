"""
ui/login_screen.py
Main entry point for authentication and high-level routing.
Features a dual-panel design: Authentication (left) and Navigation (right).
"""

import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QGridLayout, QMessageBox,
    QSpacerItem, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from database.db_manager import Database
from database.user_repo import UserRepository
from database.model_repo import ModelRepository
from ui.app_state import AppState
from core.constants import APP_NAME, APP_VERSION, ROLE_ADMIN, ROLE_OPERATOR, ROLE_SUPERVISOR


class LoginWindow(QWidget):
    """
    Handles user authentication.
    Reveals navigation options (dashboard, manual test, etc.) only upon successful login.
    """

    def __init__(self, db: Database, app_state: AppState, router=None) -> None:
        super().__init__()
        
        # Inject dependencies or use Singletons
        self._db = db or Database.get_instance()
        self._app_state = app_state or AppState.get_instance()
        self._router = router
        
        self._user_repo = UserRepository(self._db)
        self._model_repo = ModelRepository(self._db)

        self._setup_ui()
        self._apply_layout()
        self._populate_models()
        self._center_window()
        
        self._update_clock()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

    # -----------------------------------------------------------------------
    # UI Setup
    # -----------------------------------------------------------------------

    def _setup_ui(self) -> None:
        # Note: Window titles and maximization are now managed by AppWindow
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Outer alignment container to center the desktop_container vertically
        self.outer_container = QWidget()
        outer_layout = QVBoxLayout(self.outer_container)
        outer_layout.addStretch(1)
        
        # Desktop container (the actual form area)
        self.desktop_container = QWidget()
        self.desktop_layout = QHBoxLayout(self.desktop_container)
        self.desktop_layout.setContentsMargins(40, 20, 40, 20)
        self.desktop_layout.setSpacing(30)
        
        outer_layout.addWidget(self.desktop_container)
        outer_layout.addStretch(1)
        
        self._setup_left_panel()
        self._setup_right_panel()
        self._setup_status_bar()

    def _setup_left_panel(self) -> None:
        self.left_panel = QFrame()
        self.left_panel.setObjectName("card")
        self.left_panel.setFixedWidth(380)
        vbox = QVBoxLayout(self.left_panel)
        vbox.setContentsMargins(30, 40, 30, 40)
        vbox.setSpacing(15)
        
        # Header
        lbl_title = QLabel(APP_NAME)
        lbl_title.setObjectName("label_title")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setWordWrap(True)  # Allow title to wrap if too long
        
        lbl_subtitle = QLabel("Factory Floor Auth")
        lbl_subtitle.setObjectName("label_subtitle")
        lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #d0d8e8;")
        
        # Form
        lbl_role = QLabel("Select Role:")
        self.role_combo = QComboBox()
        self.role_combo.addItems([ROLE_ADMIN, ROLE_OPERATOR, ROLE_SUPERVISOR])
        
        lbl_pass = QLabel("Password:")
        
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.returnPressed.connect(self._on_login_clicked)
        
        self.btn_eye = QPushButton("Show")
        self.btn_eye.setCheckable(True)
        self.btn_eye.setObjectName("btn_secondary")
        self.btn_eye.clicked.connect(self._toggle_password_visibility)
        
        pass_layout = QHBoxLayout()
        pass_layout.addWidget(self.password_field, stretch=1)
        pass_layout.addWidget(self.btn_eye)
        
        self.error_label = QLabel("Invalid credentials. Please try again.")
        self.error_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        self.error_label.hide()
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_login = QPushButton("Login")
        self.btn_login.clicked.connect(self._on_login_clicked)
        self.btn_exit = QPushButton("Exit")
        self.btn_exit.setObjectName("btn_secondary")
        self.btn_exit.clicked.connect(self.close)
        
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_exit)
        
        # Assemble Left Panel
        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_subtitle)
        vbox.addWidget(divider)
        vbox.addWidget(lbl_role)
        vbox.addWidget(self.role_combo)
        vbox.addWidget(lbl_pass)
        vbox.addLayout(pass_layout)
        vbox.addWidget(self.error_label)
        vbox.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        vbox.addLayout(btn_layout)

    def _setup_right_panel(self) -> None:
        self.right_panel = QFrame()
        self.right_panel.setObjectName("card")
        self.right_panel.hide()  # Hidden by default
        vbox = QVBoxLayout(self.right_panel)
        vbox.setContentsMargins(30, 40, 30, 40)
        vbox.setSpacing(20)
        
        self.lbl_logged_in = QLabel("Logged in as: ")
        self.lbl_logged_in.setObjectName("label_title")
        
        # Buttons Grid (2x3)
        grid = QGridLayout()
        grid.setSpacing(15)
        
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setObjectName("btn_secondary")
        self.btn_settings.clicked.connect(self._on_settings_clicked)
        
        self.btn_password = QPushButton("Password Utility")
        self.btn_password.setObjectName("btn_secondary")
        self.btn_password.clicked.connect(self._on_password_utility_clicked)
        
        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setObjectName("btn_danger")
        self.btn_logout.clicked.connect(self._on_logout_clicked)
        
        self.btn_auto_test = QPushButton("Auto Test")
        self.btn_auto_test.setObjectName("btn_success")
        self.btn_auto_test.clicked.connect(self._on_auto_test_clicked)
        
        self.btn_manual_test = QPushButton("Manual Test")
        self.btn_manual_test.setObjectName("btn_secondary")
        self.btn_manual_test.clicked.connect(self._on_manual_test_clicked)
        
        self.btn_comments = QPushButton("Comments")
        self.btn_comments.setObjectName("btn_secondary")
        self.btn_comments.clicked.connect(self._on_comments_clicked)
        
        self.btn_reports = QPushButton("Reports")
        self.btn_reports.setObjectName("btn_secondary")
        self.btn_reports.clicked.connect(self._on_reports_clicked)
        
        grid.addWidget(self.btn_settings, 0, 0)
        grid.addWidget(self.btn_password, 0, 1)
        grid.addWidget(self.btn_logout, 0, 2)
        grid.addWidget(self.btn_auto_test, 1, 0)
        grid.addWidget(self.btn_manual_test, 1, 1)
        grid.addWidget(self.btn_comments, 1, 2)
        grid.addWidget(self.btn_reports, 2, 0)
        
        # Model Selection
        lbl_model = QLabel("Select Model:")
        lbl_model.setObjectName("label_subtitle")
        self.model_combo = QComboBox()
        
        vbox.addWidget(self.lbl_logged_in)
        vbox.addWidget(lbl_model)
        vbox.addWidget(self.model_combo)
        vbox.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        vbox.addLayout(grid)

    def _setup_status_bar(self) -> None:
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setObjectName("status_bar_frame")
        self.status_bar_frame.setFixedHeight(34)
        # Ensure dark background even if QSS fails to apply to children
        self.status_bar_frame.setStyleSheet("background-color: #1e2d4a; border: none;")
        
        hbox = QHBoxLayout(self.status_bar_frame)
        hbox.setContentsMargins(15, 0, 15, 0)
        hbox.setSpacing(10)
        
        self.lbl_clock = QLabel("")
        self.lbl_clock.setStyleSheet("color: white;")
        
        self.lbl_db_status = QLabel("DB: Connected")
        self.lbl_db_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        
        hbox.addWidget(self.lbl_db_status)
        hbox.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        hbox.addWidget(self.lbl_clock)

    def _apply_layout(self) -> None:
        self.desktop_layout.addStretch(1)  # Left stretch
        self.desktop_layout.addWidget(self.left_panel)
        self.desktop_layout.addWidget(self.right_panel)
        self.desktop_layout.addStretch(1)  # Right stretch
        
        self.main_layout.addWidget(self.outer_container, stretch=1)
        self.main_layout.addWidget(self.status_bar_frame)

    def _center_window(self) -> None:
        screen_geo = QApplication.primaryScreen().availableGeometry()
        window_geo = self.frameGeometry()
        center_point = screen_geo.center()
        window_geo.moveCenter(center_point)
        self.move(window_geo.topLeft())

    # -----------------------------------------------------------------------
    # Logic Methods
    # -----------------------------------------------------------------------

    def _populate_models(self) -> None:
        try:
            models = self._model_repo.get_all_models()
            self.model_combo.clear()
            if not models:
                self.model_combo.addItem("No Models Found", None)
            else:
                for m in models:
                    self.model_combo.addItem(m["name"], m["id"])
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Failed to load models: {str(e)}")

    def _on_login_clicked(self) -> None:
        role = self.role_combo.currentText()
        # In this implementation, the backend username corresponds to the abstract role name usually,
        # or we assume username=role.lower() based on prompt spec.
        username = role.lower()
        password = self.password_field.text()
        
        user_dict = self._user_repo.authenticate(username, password)
        if user_dict:
            self._app_state.set_user(user_dict)
            self._show_right_panel()
            self.password_field.clear()
            self.error_label.hide()
        else:
            self.error_label.show()
            self.password_field.clear()
            self.password_field.setFocus()

    def _show_right_panel(self) -> None:
        self.lbl_logged_in.setText(f"Logged in as: {self._app_state.current_user['username']}")
        
        # Enforce role-based access
        is_admin_sup = self._app_state.is_admin() or self._app_state.current_user.get("role") == "SUPERVISOR"
        self.btn_settings.setVisible(self._app_state.is_admin())
        self.btn_reports.setVisible(is_admin_sup)
        
        self.right_panel.show()
        self.model_combo.setFocus()

    def _on_logout_clicked(self) -> None:
        self._app_state.clear_user()
        self.right_panel.hide()
        self.password_field.clear()
        self.role_combo.setCurrentIndex(0)
        self.error_label.hide()

    def _on_auto_test_clicked(self) -> None:
        model_id = self.model_combo.currentData()
        if not model_id:
            QMessageBox.warning(self, "Validation", "Please select a valid model.")
            return
            
        full_config = self._model_repo.get_full_model_config(model_id)
        if not full_config:
            QMessageBox.warning(self, "Error", "Failed to load model config geometry.")
            return
            
        self._app_state.set_model(full_config)
        
        if self._router:
            self._router.show_dashboard()
        else:
            QMessageBox.information(self, "Notice", "Main Dashboard Screen is not yet fully implemented or Router missing.")

    def _on_manual_test_clicked(self) -> None:
        model_id = self.model_combo.currentData()
        if not model_id:
            QMessageBox.warning(self, "Validation", "Please select a valid model.")
            return
            
        # Same sequence as AutoTest logic
        full_config = self._model_repo.get_full_model_config(model_id)
        self._app_state.set_model(full_config)
        
        try:
            from plc.connection_manager import ConnectionManager
            conn_mgr = ConnectionManager(self._app_state.plc_config)
            if self._router:
                self._router.show_manual_test(conn_mgr)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to instantiate mechanical bounds securely:\n{e}")

    def _on_settings_clicked(self) -> None:
        if self._router:
            self._router.show_settings()
        else:
            QMessageBox.information(self, "Notice", "Settings Screen is not yet fully implemented or Router missing.")

    def _on_password_utility_clicked(self) -> None:
        if self._router: self._router.show_password_utility()

    def _on_comments_clicked(self) -> None:
        if self._router: self._router.show_comments()

    def _toggle_password_visibility(self) -> None:
        if self.btn_eye.isChecked():
            self.password_field.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_eye.setText("Hide")
        else:
            self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_eye.setText("Show")

    def _on_reports_clicked(self) -> None:
        if self._router: self._router.show_reports()

    def _update_clock(self) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(f"{APP_NAME} v{APP_VERSION}  |  {now_str}")

    def closeEvent(self, event) -> None:
        QApplication.quit()
