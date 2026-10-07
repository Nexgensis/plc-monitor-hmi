import logging
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal

from src.ui.app_state import AppState

logger = logging.getLogger(__name__)

class ConfirmDialog(QMessageBox):
    """Utility class to ask confirmation directly without full MessageBox setup."""
    @staticmethod
    def ask(parent, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            parent,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes

class NavBar(QFrame):
    """
    NavBar reused on MainWindow and ManualTestWindow.
    """
    home_requested = pyqtSignal()

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        self.setFixedHeight(44)
        self.setObjectName("nav_bar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)

        # LEFT
        self.app_name_lbl = QLabel("PLC Monitor")
        self.app_name_lbl.setObjectName("nav_bar_title")
        layout.addWidget(self.app_name_lbl)

        # CENTER
        layout.addStretch()
        self.model_name_lbl = QLabel("")
        self.model_name_lbl.setObjectName("nav_bar_model")
        self.model_name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.model_name_lbl)
        layout.addStretch()

        # RIGHT
        self.plc_status_lbl = QLabel("● PLC: Disconnected")
        self.plc_status_lbl.setObjectName("nav_bar_plc_status")
        layout.addWidget(self.plc_status_lbl)

        layout.addSpacing(15)

        user = self.app_state.current_user
        username = user.get("username", "Unknown") if user else "Unknown"
        role = user.get("role", "Unknown") if user else "Unknown"
        
        self.user_lbl = QLabel(f"👤 {username} ({role})")
        self.user_lbl.setObjectName("nav_bar_user")
        layout.addWidget(self.user_lbl)

        layout.addSpacing(15)

        self.home_btn = QPushButton("⌂ Home")
        self.home_btn.setFlat(True)
        self.home_btn.setObjectName("nav_bar_home_btn")
        self.home_btn.clicked.connect(self._on_home_clicked)
        layout.addWidget(self.home_btn)

        # Initial updates
        self.update_plc_status(self.app_state.is_plc_connected)
        if self.app_state.current_model:
            model_name = self.app_state.current_model.get("name", "")
            self.update_model_name(model_name)

    def update_plc_status(self, connected: bool) -> None:
        if connected:
            self.plc_status_lbl.setText("● PLC: Connected")
            self.plc_status_lbl.setProperty("connected", True)
        else:
            self.plc_status_lbl.setText("● PLC: Disconnected")
            self.plc_status_lbl.setProperty("connected", False)
        self.plc_status_lbl.style().unpolish(self.plc_status_lbl)
        self.plc_status_lbl.style().polish(self.plc_status_lbl)

    def update_model_name(self, name: str) -> None:
        self.model_name_lbl.setText(name)

    def _on_home_clicked(self) -> None:
        reply = ConfirmDialog.ask(
            self,
            "Return to Login",
            "Return to login screen?\nThe current test session will be paused."
        )
        if reply:
            self.home_requested.emit()
