"""
control_dialog.py — Universal PLC Monitor
Dialog for adding/editing control register buttons.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QSpinBox, QComboBox, QCheckBox, QPushButton, 
                             QFormLayout)
from PyQt6.QtCore import Qt

from src.utils.constants import CTRL_TYPES


class ControlDialog(QDialog):
    """Dialog for adding or editing a control register button."""
    
    def __init__(self, parent=None, control_data: dict = None, 
                 register_options: list = None, is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._control_data = control_data or {}
        self._register_options = register_options or []
        
        self.setWindowTitle("Edit Control Button" if is_edit else "Add Control Button")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setAccessibleName("Control button dialog")
        
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
        self.name_edit.setPlaceholderText("Button name (e.g. Start Test)")
        form_layout.addRow("Button Name*:", self.name_edit)
        
        self.reg_combo = QComboBox()
        for reg in self._register_options:
            self.reg_combo.addItem(reg["label"], reg["id"])
        form_layout.addRow("Register*:", self.reg_combo)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(CTRL_TYPES)
        form_layout.addRow("Control Type*:", self.type_combo)
        
        self.val_spin = QSpinBox()
        self.val_spin.setRange(0, 65535)
        self.val_spin.setValue(1)
        form_layout.addRow("Write Value:", self.val_spin)
        
        self.pulse_spin = QSpinBox()
        self.pulse_spin.setRange(0, 10000)
        self.pulse_spin.setSuffix(" ms")
        self.pulse_spin.setValue(0)
        form_layout.addRow("Pulse Reset:", self.pulse_spin)
        
        self.conf_cb = QCheckBox("Require Confirmation Dialog")
        form_layout.addRow(self.conf_cb)
        
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
        if self._is_edit and self._control_data:
            self.name_edit.setText(self._control_data.get("name", ""))
            reg_id = self._control_data.get("register_id")
            idx = self.reg_combo.findData(reg_id)
            if idx >= 0:
                self.reg_combo.setCurrentIndex(idx)
            self.type_combo.setCurrentText(self._control_data.get("control_type", "CUSTOM"))
            self.val_spin.setValue(self._control_data.get("write_value", 1))
            self.pulse_spin.setValue(self._control_data.get("reset_after_ms", 0))
            self.conf_cb.setChecked(bool(self._control_data.get("confirm_required", False)))
    
    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            return
        
        reg_id = self.reg_combo.currentData()
        if reg_id is None:
            return
        
        self._result = {
            "name": name,
            "register_id": reg_id,
            "control_type": self.type_combo.currentText(),
            "write_value": self.val_spin.value(),
            "reset_after_ms": self.pulse_spin.value(),
            "confirm_required": self.conf_cb.isChecked(),
        }
        self.accept()
    
    def get_result(self) -> dict:
        return getattr(self, "_result", {})