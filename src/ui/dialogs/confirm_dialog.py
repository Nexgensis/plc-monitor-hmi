"""
confirm_dialog.py — Universal PLC Monitor
Small, high-contrast confirmation dialog for destructive actions.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt


class ConfirmDialog(QDialog):
    def __init__(self, parent=None, title="Confirm", message="Are you sure?",
                 danger=False, confirm_text=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 180)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAccessibleName(title)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setObjectName("confirm_dialog_message")
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setAccessibleName("Cancel action")
        self.cancel_btn.setToolTip("Cancel and close this dialog")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setFixedHeight(34)
        
        self.confirm_btn = QPushButton(confirm_text or title)
        self.confirm_btn.setAccessibleName(confirm_text or title)
        if danger:
            self.confirm_btn.setObjectName("btn_danger")
            self.confirm_btn.setToolTip("Confirm destructive action")
        else:
            self.confirm_btn.setObjectName("btn_primary")
            self.confirm_btn.setToolTip("Confirm this action")
        self.confirm_btn.clicked.connect(self.accept)
        self.confirm_btn.setFixedHeight(34)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)
        
        self.setTabOrder(self.cancel_btn, self.confirm_btn)

    @staticmethod
    def ask(parent, title="Confirm", message="Are you sure?", danger=False,
            confirm_text=None) -> bool:
        """Helper to show dialog and return True if accepted."""
        dlg = ConfirmDialog(parent, title, message, danger, confirm_text)
        return dlg.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def show_error(parent, title="Error", message="An error occurred.") -> None:
        """Show a non-interactive error message dialog."""
        dlg = ConfirmDialog(parent, title, message, danger=True)
        dlg.confirm_btn.setText("OK")
        dlg.cancel_btn.hide()
        dlg.exec()
