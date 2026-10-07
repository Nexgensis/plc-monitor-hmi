"""
message_dialog.py — Universal PLC Monitor
Dialog for adding/editing message register mappings.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QSpinBox, QComboBox, QPushButton, QFormLayout)
from PyQt6.QtCore import Qt


class MessageDialog(QDialog):
    """Dialog for adding or editing a message register mapping."""
    
    def __init__(self, parent=None, mapping_data: dict = None, is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._mapping_data = mapping_data or {}
        
        self.setWindowTitle("Edit Message Mapping" if is_edit else "Add Message Mapping")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setAccessibleName("Message mapping dialog")
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.val_spin = QSpinBox()
        self.val_spin.setRange(0, 65535)
        form_layout.addRow("Trigger Value*:", self.val_spin)
        
        self.txt_edit = QLineEdit()
        self.txt_edit.setMaxLength(200)
        self.txt_edit.setPlaceholderText("Message text to display")
        form_layout.addRow("Message Text*:", self.txt_edit)
        
        self.color_combo = QComboBox()
        self.color_combo.addItems(["green", "red", "yellow", "white", "amber"])
        form_layout.addRow("Color:", self.color_combo)
        
        self.sev_combo = QComboBox()
        self.sev_combo.addItems(["INFO", "WARNING", "ERROR", "CRITICAL"])
        form_layout.addRow("Severity:", self.sev_combo)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_row = QHBoxLayout()
        if self._is_edit:
            rem_btn = QPushButton("Remove")
            rem_btn.setObjectName("btn_danger")
            rem_btn.clicked.connect(self._on_remove)
            btn_row.addWidget(rem_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("btn_primary")
        save_btn.clicked.connect(self._on_save)
        save_btn.setDefault(True)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)
    
    def _load_data(self) -> None:
        if self._is_edit and self._mapping_data:
            self.val_spin.setValue(self._mapping_data.get("trigger_value", 0))
            self.txt_edit.setText(self._mapping_data.get("message_text", ""))
            self.color_combo.setCurrentText(self._mapping_data.get("color", "green"))
            self.sev_combo.setCurrentText(self._mapping_data.get("severity", "INFO"))
    
    def _on_save(self) -> None:
        text = self.txt_edit.text().strip()
        if not text:
            self.txt_edit.setFocus()
            return
        
        self._result = {
            "trigger_value": self.val_spin.value(),
            "message_text": text,
            "color": self.color_combo.currentText(),
            "severity": self.sev_combo.currentText(),
        }
        self._removed = False
        self.accept()
    
    def _on_remove(self) -> None:
        from src.ui.dialogs.confirm_dialog import ConfirmDialog
        if ConfirmDialog.ask(self, "Delete Mapping", "Remove this message trigger?"):
            self._result = {}
            self._removed = True
            self.accept()
    
    def get_result(self) -> dict:
        return getattr(self, "_result", {})
    
    def was_removed(self) -> bool:
        return getattr(self, "_removed", False)