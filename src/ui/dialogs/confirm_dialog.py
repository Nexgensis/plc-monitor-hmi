"""
confirm_dialog.py — Universal PLC Monitor
Small, high-contrast confirmation dialog for destructive actions.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt


class ConfirmDialog(QDialog):
    def __init__(self, parent=None, title="Confirm", message="Are you sure?", danger=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 180)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 14px; color: #e8f0fa;")
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setFixedHeight(40)
        
        self.confirm_btn = QPushButton(title)
        if danger:
            self.confirm_btn.setObjectName("btn_danger")
        else:
            self.confirm_btn.setObjectName("btn_primary")
        self.confirm_btn.clicked.connect(self.accept)
        self.confirm_btn.setFixedHeight(40)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def ask(parent, title="Confirm", message="Are you sure?", danger=False) -> bool:
        """Helper to show dialog and return True if accepted."""
        dlg = ConfirmDialog(parent, title, message, danger)
        return dlg.exec() == QDialog.DialogCode.Accepted
