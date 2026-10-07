"""
register_dialog.py — Universal PLC Monitor
Dialog for adding/editing register library entries.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
                             QCheckBox, QPushButton, QFormLayout)
from PyQt6.QtCore import Qt

from src.utils.constants import REG_TYPES, DATA_TYPES


class RegisterDialog(QDialog):
    """Dialog for adding or editing a register in the library."""
    
    def __init__(self, parent=None, register_data: dict = None, is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._register_data = register_data or {}
        
        self.setWindowTitle("Edit Register" if is_edit else "Add Register")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setAccessibleName("Register dialog")
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(100)
        self.name_edit.setPlaceholderText("Enter register name")
        form_layout.addRow("Name*:", self.name_edit)
        
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Optional description")
        form_layout.addRow("Description:", self.desc_edit)
        
        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(0, 65535)
        form_layout.addRow("Address*:", self.addr_spin)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(REG_TYPES)
        form_layout.addRow("Type*:", self.type_combo)
        
        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems(DATA_TYPES)
        form_layout.addRow("Data Type*:", self.dtype_combo)
        
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.00001, 100000)
        self.scale_spin.setDecimals(5)
        self.scale_spin.setValue(1.0)
        form_layout.addRow("Scale:", self.scale_spin)
        
        self.decimal_spin = QSpinBox()
        self.decimal_spin.setRange(0, 6)
        self.decimal_spin.setValue(2)
        form_layout.addRow("Decimals:", self.decimal_spin)
        
        self.unit_edit = QLineEdit()
        self.unit_edit.setMaxLength(20)
        self.unit_edit.setPlaceholderText("e.g. bar, °C, V")
        form_layout.addRow("Unit:", self.unit_edit)
        
        self.access_combo = QComboBox()
        self.access_combo.addItems(["READ_ONLY", "READ_WRITE"])
        form_layout.addRow("Access:", self.access_combo)
        
        self.swap_cb = QCheckBox("Word Swap")
        form_layout.addRow(self.swap_cb)
        
        self.access_warn = QLabel("⚠ READ_WRITE registers can be written to PLC")
        self.access_warn.setObjectName("config_warn_lbl")
        self.access_warn.hide()
        form_layout.addRow(self.access_warn)
        self.access_combo.currentTextChanged.connect(
            lambda t: self.access_warn.setVisible(t == "READ_WRITE")
        )
        
        layout.addLayout(form_layout)
        
        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("config_error_lbl")
        self.error_lbl.setWordWrap(True)
        layout.addWidget(self.error_lbl)
        
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
        if self._is_edit and self._register_data:
            self.name_edit.setText(self._register_data.get("name", ""))
            self.desc_edit.setText(self._register_data.get("description", ""))
            self.addr_spin.setValue(self._register_data.get("register_address", 0))
            self.type_combo.setCurrentText(self._register_data.get("register_type", "HOLDING"))
            self.dtype_combo.setCurrentText(self._register_data.get("data_type", "INT16"))
            self.scale_spin.setValue(self._register_data.get("scale_factor", 1.0))
            self.decimal_spin.setValue(self._register_data.get("decimal_places", 2))
            self.unit_edit.setText(self._register_data.get("unit", ""))
            self.access_combo.setCurrentText(self._register_data.get("access", "READ_ONLY"))
            self.swap_cb.setChecked(bool(self._register_data.get("word_swap", False)))
    
    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error_lbl.setText("Name is required")
            self.name_edit.setFocus()
            return
        
        self._result = {
            "name": name,
            "description": self.desc_edit.text().strip(),
            "register_address": self.addr_spin.value(),
            "register_type": self.type_combo.currentText(),
            "data_type": self.dtype_combo.currentText(),
            "scale_factor": self.scale_spin.value(),
            "decimal_places": self.decimal_spin.value(),
            "unit": self.unit_edit.text().strip(),
            "access": self.access_combo.currentText(),
            "word_swap": self.swap_cb.isChecked(),
        }
        self.accept()
    
    def get_result(self) -> dict:
        return getattr(self, "_result", {})


class RegisterDialogResult:
    """Simple result wrapper."""
    def __init__(self, accepted: bool, data: dict = None):
        self.accepted = accepted
        self.data = data or {}