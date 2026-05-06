"""
login_overlay.py — Universal PLC Monitor
Full-screen overlay for user authentication.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Dict, Any
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QFrame)
from PyQt6.QtCore import pyqtSignal, QPropertyAnimation, QPoint, Qt, QSequentialAnimationGroup
from src.utils.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class LoginOverlay(QWidget):
    def __init__(self, app_state: any, on_success: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_success_callback = on_success
        self.setObjectName("login_overlay")

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centered Card
        self.card = QFrame()
        self.card.setObjectName("login_card")
        self.card.setFixedWidth(420)
        self.card.setStyleSheet("""
            #login_card {
                background-color: #111827;
                border: 1px solid #1e2d4a;
                border-radius: 12px;
            }
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        # Branding
        title_lbl = QLabel(APP_NAME)
        title_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #e8f0fa;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        version_lbl = QLabel(f"Version {APP_VERSION}")
        version_lbl.setStyleSheet("font-size: 12px; color: #5a7a9a;")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(version_lbl)

        # PLC Status Banner
        self.plc_notice = QLabel("⚠ PLC NOT CONFIGURED")
        self.plc_notice.setStyleSheet("background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; "
                                      "padding: 8px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        self.plc_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plc_notice.setVisible(not self.app_state.is_plc_configured)
        card_layout.addWidget(self.plc_notice)

        # Form
        self.role_combo = QComboBox()
        self.role_combo.addItems(["OPERATOR", "SUPERVISOR", "ADMIN"])
        self.role_combo.setFixedHeight(40)
        card_layout.addWidget(QLabel("SELECT ROLE"))
        card_layout.addWidget(self.role_combo)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter Password")
        self.password_input.setFixedHeight(40)
        self.password_input.returnPressed.connect(self._on_login)

        pw_layout = QHBoxLayout()
        pw_layout.addWidget(self.password_input)

        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFixedSize(40, 40)
        self.eye_btn.setCheckable(True)
        self.eye_btn.clicked.connect(self._toggle_password)
        pw_layout.addWidget(self.eye_btn)

        card_layout.addWidget(QLabel("PASSWORD"))
        card_layout.addLayout(pw_layout)

        # Error Label
        self.error_lbl = QLabel("Invalid password. Please try again.")
        self.error_lbl.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.hide()
        card_layout.addWidget(self.error_lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("LOGIN")
        self.login_btn.setFixedHeight(44)
        self.login_btn.setObjectName("btn_primary")
        self.login_btn.clicked.connect(self._on_login)

        self.exit_btn = QPushButton("EXIT")
        self.exit_btn.setFixedHeight(44)
        self.exit_btn.setObjectName("btn_danger")
        from PyQt6.QtWidgets import QApplication
        self.exit_btn.clicked.connect(QApplication.quit)

        btn_layout.addWidget(self.login_btn, 2)
        btn_layout.addWidget(self.exit_btn, 1)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(self.card)

    def _toggle_password(self, checked: bool) -> None:
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_login(self) -> None:
        role = self.role_combo.currentText().upper()
        password = self.password_input.text()

        # Check against DB via app_state.user_repo
        if self.app_state.user_repo:
            user = self.app_state.user_repo.authenticate(role, password)
            if user:
                logger.info("Authentication successful for role: %s", role)
                if self.on_success_callback:
                    self.on_success_callback(user)
                return

        logger.warning("Authentication failed for role: %s", role)
        self.error_lbl.show()
        self._shake_card()
        self.password_input.clear()

    def _shake_card(self) -> None:
        """QPropertyAnimation for wrong password shake effect."""
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
        """Clear form on logout."""
        self.password_input.clear()
        self.error_lbl.hide()
        self.plc_notice.setVisible(not self.app_state.is_plc_configured)
        self.password_input.setFocus()
