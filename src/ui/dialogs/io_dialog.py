"""
io_dialog.py — Universal PLC Monitor
Dialog for adding/editing I/O list entries.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QSpinBox, QComboBox, QCheckBox, QPushButton, 
                             QFormLayout)
from PyQt6.QtCore import Qt


class IODialog(QDialog):
    """Dialog for adding or editing an I/O list entry."""
    
    def __init__(self, parent=None, io_data: dict = None, 
                 register_options: list = None, is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._io_data = io_data or {}
        self._register_options = register_options or []
        
        self.setWindowTitle("Edit I/O Entry" if is_edit else "Add I/O Entry")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setAccessibleName("I/O entry dialog")
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Display name for I/O point")
        form_layout.addRow("Display Name*:", self.name_edit)
        
        self.reg_combo = QComboBox()
        for reg in self._register_options:
            self.reg_combo.addItem(reg["label"], reg["id"])
        form_layout.addRow("Register*:", self.reg_combo)
        
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Group name for grouping")
        form_layout.addRow("Group Name:", self.group_edit)
        
        self.order_spin = QSpinBox()
        self.order_spin.setRange(0, 1000)
        form_layout.addRow("Row Order:", self.order_spin)
        
        self.val_cb = QCheckBox("Show Numeric Value")
        self.val_cb.setChecked(True)
        form_layout.addRow(self.val_cb)
        
        self.on_edit = QLineEdit("ON")
        self.on_edit.setMaxLength(20)
        form_layout.addRow("ON Label:", self.on_edit)
        
        self.off_edit = QLineEdit("OFF")
        self.off_edit.setMaxLength(20)
        form_layout.addRow("OFF Label:", self.off_edit)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_row = QHBoxLayout()
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
        if self._is_edit and self._io_data:
            self.name_edit.setText(self._io_data.get("display_name", ""))
            reg_id = self._io_data.get("register_id")
            idx = self.reg_combo.findData(reg_id)
            if idx >= 0:
                self.reg_combo.setCurrentIndex(idx)
            self.group_edit.setText(self._io_data.get("group_name", ""))
            self.order_spin.setValue(self._io_data.get("row_order", 0))
            self.val_cb.setChecked(bool(self._io_data.get("show_value", True)))
            self.on_edit.setText(self._io_data.get("on_label", "ON"))
            self.off_edit.setText(self._io_data.get("off_label", "OFF"))
    
    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            return
        
        reg_id = self.reg_combo.currentData()
        if reg_id is None:
            return
        
        self._result = {
            "display_name": name,
            "register_id": reg_id,
            "group_name": self.group_edit.text().strip(),
            "row_order": self.order_spin.value(),
            "show_value": self.val_cb.isChecked(),
            "on_label": self.on_edit.text().strip(),
            "off_label": self.off_edit.text().strip(),
        }
        self.accept()
    
    def get_result(self) -> dict:
        return getattr(self, "_result", {})