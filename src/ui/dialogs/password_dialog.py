"""
Small dialog for administrative password entry (e.g. operator unlock).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton,
)
from PyQt6.QtCore import Qt


class PasswordDialog(QDialog):
    """
    Modal dialog that prompts for a password.

    Usage::

        dlg = PasswordDialog(parent=self, title="Enter Admin Password")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            password = dlg.password

    Attributes after ``exec()``:
        password (str): The entered password (empty if cancelled).
    """

    def __init__(
        self,
        parent=None,
        title: str = "Enter Password",
        message: str = "This action requires authentication.",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(380, 180)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.password: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #e8f0fa; font-size: 13px;")
        root.addWidget(msg_lbl)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.setFixedHeight(36)
        self.password_input.returnPressed.connect(self._on_accept)
        root.addWidget(self.password_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("btn_primary")
        ok_btn.setFixedHeight(34)
        ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(ok_btn)

        root.addLayout(btn_row)

    def _on_accept(self) -> None:
        self.password = self.password_input.text()
        self.accept()
