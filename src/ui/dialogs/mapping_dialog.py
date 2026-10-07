"""
mapping_dialog.py — Universal PLC Monitor
Dialog for adding/editing model register mappings.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, 
                             QPushButton, QFormLayout)
from PyQt6.QtCore import Qt

from src.utils.constants import ROLES


class MappingDialog(QDialog):
    """Dialog for adding or editing a model register mapping."""
    
    def __init__(self, parent=None, mapping_data: dict = None, 
                 library_name: str = "", is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._mapping_data = mapping_data or {}
        self._library_name = library_name
        
        self.setWindowTitle("Edit Mapping" if is_edit else "Add Register Mapping")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setAccessibleName("Mapping dialog")
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Library name display
        lib_row = QHBoxLayout()
        lib_row.addWidget(QLabel("Register:"))
        self.lib_name_lbl = QLabel(self._library_name)
        self.lib_name_lbl.setObjectName("editor_title")
        lib_row.addWidget(self.lib_name_lbl, 1)
        layout.addLayout(lib_row)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.form_layout = form_layout
        
        self.disp_name_edit = QLineEdit()
        self.disp_name_edit.setPlaceholderText("Display name for dashboard")
        form_layout.addRow("Display Name*:", self.disp_name_edit)
        
        self.role_combo = QComboBox()
        self.role_combo.addItems(ROLES)
        self.role_combo.currentTextChanged.connect(self._on_role_changed)
        form_layout.addRow("Role*:", self.role_combo)
        
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("e.g. ELECTRICAL, MECHANICAL")
        form_layout.addRow("Group Name:", self.group_edit)
        
        self.enabled_cb = QCheckBox("Enabled")
        self.enabled_cb.setChecked(True)
        form_layout.addRow(self.enabled_cb)
        
        self.bypass_cb = QCheckBox("Bypass in Pass/Fail")
        form_layout.addRow(self.bypass_cb)
        
        self.db_cb = QCheckBox("Show in Dashboard")
        self.db_cb.setChecked(True)
        form_layout.addRow(self.db_cb)
        
        self.pos_spin = QSpinBox()
        self.pos_spin.setRange(0, 29)
        form_layout.addRow("Position:", self.pos_spin)
        
        # Pass/Fail values (only for RESULT role)
        self.pass_spin = QSpinBox()
        self.pass_spin.setRange(0, 65535)
        form_layout.addRow("Pass Value:", self.pass_spin)
        
        self.fail_spin = QSpinBox()
        self.fail_spin.setRange(0, 65535)
        form_layout.addRow("Fail Value:", self.fail_spin)

        # Min/Max spec limits (shown for MEASURED/STATUS/COUNTER/etc.)
        self.limit_min_spin = QDoubleSpinBox()
        self.limit_min_spin.setRange(-999999999.0, 999999999.0)
        self.limit_min_spin.setDecimals(4)
        form_layout.addRow("Min Limit:", self.limit_min_spin)

        self.limit_max_spin = QDoubleSpinBox()
        self.limit_max_spin.setRange(-999999999.0, 999999999.0)
        self.limit_max_spin.setDecimals(4)
        form_layout.addRow("Max Limit:", self.limit_max_spin)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("btn_primary")
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setDefault(True)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)
    
    def _load_data(self) -> None:
        if self._is_edit and self._mapping_data:
            self.disp_name_edit.setText(self._mapping_data.get("display_name", ""))
            self.role_combo.setCurrentText(self._mapping_data.get("role", "MEASURED"))
            self.group_edit.setText(self._mapping_data.get("group_name", ""))
            self.enabled_cb.setChecked(bool(self._mapping_data.get("enabled", True)))
            self.bypass_cb.setChecked(bool(self._mapping_data.get("bypass", False)))
            self.db_cb.setChecked(bool(self._mapping_data.get("show_in_dashboard", True)))
            self.pos_spin.setValue(self._mapping_data.get("card_position", 0))
            self.pass_spin.setValue(self._mapping_data.get("pass_value", 1))
            self.fail_spin.setValue(self._mapping_data.get("fail_value", 2))
            self.limit_min_spin.setValue(float(self._mapping_data.get("limit_min", 0.0)))
            self.limit_max_spin.setValue(float(self._mapping_data.get("limit_max", 0.0)))
        self._on_role_changed(self.role_combo.currentText())
    
    def _on_role_changed(self, role: str) -> None:
        is_result = (role == "RESULT")
        self.pass_spin.setVisible(is_result)
        self.fail_spin.setVisible(is_result)
        # Hide min/max limits for RESULT role (they use pass/fail raw values)
        show_limits = not is_result
        self.limit_min_spin.setVisible(show_limits)
        self.limit_max_spin.setVisible(show_limits)
        # Toggle the associated row labels too
        for widget, visible in (
            (self.limit_min_spin, show_limits),
            (self.limit_max_spin, show_limits),
            (self.pass_spin, is_result),
            (self.fail_spin, is_result),
        ):
            self._set_row_visible(widget, visible)

    def _set_row_visible(self, field_widget, visible: bool) -> None:
        """Show/hide both the label and field of a QFormLayout row."""
        label_widget = self.form_layout.labelForField(field_widget)
        if label_widget:
            label_widget.setVisible(visible)
    
    def _on_apply(self) -> None:
        disp_name = self.disp_name_edit.text().strip()
        if not disp_name:
            # Could show error, but for now just use library name
            disp_name = self._library_name
        
        self._result = {
            "display_name": disp_name,
            "role": self.role_combo.currentText(),
            "group_name": self.group_edit.text().strip(),
            "enabled": self.enabled_cb.isChecked(),
            "bypass": self.bypass_cb.isChecked(),
            "show_in_dashboard": self.db_cb.isChecked(),
            "card_position": self.pos_spin.value(),
            "pass_value": self.pass_spin.value(),
            "fail_value": self.fail_spin.value(),
            "limit_min": self.limit_min_spin.value(),
            "limit_max": self.limit_max_spin.value(),
        }
        self.accept()
    
    def get_result(self) -> dict:
        return getattr(self, "_result", {})