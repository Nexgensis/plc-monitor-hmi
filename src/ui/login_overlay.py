"""
login_overlay.py — Universal PLC Monitor
Full-screen overlay for user authentication.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Dict, Any
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QComboBox, QFrame,
                             QApplication, QMessageBox)
from PyQt6.QtCore import QPropertyAnimation, QPoint, Qt
from src.ui.components.spinner import Spinner
from src.utils.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class LoginOverlay(QWidget):
    def __init__(self, app_state: any, on_success: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_success_callback = on_success
        self.setObjectName("login_overlay")
        self.setAccessibleName("Login screen")

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centered Card
        self.card = QFrame()
        self.card.setObjectName("login_card")
        self.card.setAccessibleName("Login form")
        self.card.setFixedWidth(420)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        # Branding
        title_lbl = QLabel(APP_NAME)
        title_lbl.setObjectName("login_title")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        version_lbl = QLabel(f"Version {APP_VERSION}")
        version_lbl.setObjectName("login_version")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(version_lbl)

        # PLC Status Banner
        self.plc_notice = QLabel("PLC NOT CONFIGURED")
        self.plc_notice.setObjectName("login_plc_notice")
        self.plc_notice.setAccessibleName("PLC configuration notice")
        self.plc_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plc_notice.setVisible(not self.app_state.is_plc_configured)
        card_layout.addWidget(self.plc_notice)

        # Form
        role_label = QLabel("SELECT ROLE")
        role_label.setObjectName("login_form_label")
        card_layout.addWidget(role_label)

        self.role_combo = QComboBox()
        self.role_combo.setAccessibleName("Select user role")
        self.role_combo.setToolTip("Choose your role: OPERATOR, SUPERVISOR, or ADMIN")
        self.role_combo.addItems(["OPERATOR", "SUPERVISOR", "ADMIN"])
        self.role_combo.setFixedHeight(40)
        card_layout.addWidget(self.role_combo)

        pw_label = QLabel("PASSWORD")
        pw_label.setObjectName("login_form_label")
        card_layout.addWidget(pw_label)

        self.password_input = QLineEdit()
        self.password_input.setAccessibleName("Password")
        self.password_input.setToolTip("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter Password")
        self.password_input.setFixedHeight(40)
        self.password_input.returnPressed.connect(self._on_login)

        pw_layout = QHBoxLayout()
        pw_layout.addWidget(self.password_input)

        self.eye_btn = QPushButton()
        self.eye_btn.setObjectName("login_eye_btn")
        self.eye_btn.setAccessibleName("Toggle password visibility")
        self.eye_btn.setFixedSize(40, 40)
        self.eye_btn.setCheckable(True)
        self.eye_btn.setToolTip("Toggle password visibility")
        self.eye_btn.clicked.connect(self._toggle_password)
        pw_layout.addWidget(self.eye_btn)

        card_layout.addLayout(pw_layout)

        # Error Label
        self.error_lbl = QLabel("Invalid password. Please try again.")
        self.error_lbl.setObjectName("login_error")
        self.error_lbl.setAccessibleName("Login error message")
        self.error_lbl.setAccessibleDescription("Shown when login fails")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.hide()
        card_layout.addWidget(self.error_lbl)

        # Loading Spinner
        self.loading_widget = QWidget()
        loading_layout = QHBoxLayout(self.loading_widget)
        loading_layout.setContentsMargins(0, 10, 0, 10)
        loading_layout.setSpacing(8)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._spinner = Spinner(size=20, speed=80, parent=self.loading_widget)
        self._spinner.setFixedSize(20, 20)
        loading_layout.addWidget(self._spinner)
        
        self.loading_lbl = QLabel("Authenticating...")
        self.loading_lbl.setObjectName("login_loading")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self.loading_lbl)
        
        self.loading_widget.hide()
        card_layout.addWidget(self.loading_widget)

        # Buttons
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("LOGIN")
        self.login_btn.setAccessibleName("Login")
        self.login_btn.setToolTip("Log in with selected role and password")
        self.login_btn.setFixedHeight(42)
        self.login_btn.setObjectName("btn_primary")
        self.login_btn.clicked.connect(self._on_login)

        self.exit_btn = QPushButton("EXIT")
        self.exit_btn.setAccessibleName("Exit application")
        self.exit_btn.setToolTip("Close the application")
        self.exit_btn.setFixedHeight(42)
        self.exit_btn.setObjectName("btn_danger")
        self.exit_btn.clicked.connect(self._on_exit_clicked)

        btn_layout.addWidget(self.login_btn, 2)
        btn_layout.addWidget(self.exit_btn, 1)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(self.card)

        self.setTabOrder(self.role_combo, self.password_input)
        self.setTabOrder(self.password_input, self.eye_btn)
        self.setTabOrder(self.eye_btn, self.login_btn)
        self.setTabOrder(self.login_btn, self.exit_btn)

    def _toggle_password(self, checked: bool) -> None:
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_exit_clicked(self) -> None:
        reply = QMessageBox.question(
            self, "Exit Application",
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.quit()

    def _on_login(self) -> None:
        role = self.role_combo.currentText().upper()
        password = self.password_input.text()

        if not password:
            self.error_lbl.setText("Please enter your password.")
            self.error_lbl.show()
            self._shake_card()
            self.password_input.setFocus()
            return

        self.login_btn.setEnabled(False)
        self.exit_btn.setEnabled(False)
        self.loading_widget.show()
        self._spinner.start()
        self.error_lbl.hide()
        QApplication.processEvents()

        if self.app_state.user_repo:
            user = self.app_state.user_repo.authenticate(role, password)
            if user:
                logger.info("Authentication successful for role: %s", role)
                self._spinner.stop()
                self.loading_widget.hide()
                self.login_btn.setEnabled(True)
                self.exit_btn.setEnabled(True)
                if self.on_success_callback:
                    self.on_success_callback(user)
                return

        self._spinner.stop()
        self.loading_widget.hide()
        self.login_btn.setEnabled(True)
        self.exit_btn.setEnabled(True)
        logger.warning("Authentication failed for role: %s", role)
        self.error_lbl.setText("Invalid password. Please try again.")
        self.error_lbl.show()
        self._shake_card()
        self.password_input.clear()

    def _shake_card(self) -> None:
        orig_pos = self.card.pos()
        self.animation = QPropertyAnimation(self.card, b"pos")
        self.animation.setDuration(400)
        self.animation.setStartValue(orig_pos)
        self.animation.setKeyValueAt(0.1, orig_pos + QPoint(-10, 0))
        self.animation.setKeyValueAt(0.3, orig_pos + QPoint(10, 0))
        self.animation.setKeyValueAt(0.5, orig_pos + QPoint(-10, 0))
        self.animation.setKeyValueAt(0.7, orig_pos + QPoint(10, 0))
        self.animation.setEndValue(orig_pos)
        self.animation.start()

    def reset(self) -> None:
        self.password_input.clear()
        self.error_lbl.hide()
        self._spinner.stop()
        self.loading_widget.hide()
        self.login_btn.setEnabled(True)
        self.exit_btn.setEnabled(True)
        self.plc_notice.setVisible(not self.app_state.is_plc_configured)
        self.password_input.setFocus()
