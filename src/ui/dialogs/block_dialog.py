"""
block_dialog.py — Universal PLC Monitor
Dialog for adding/editing Register Block definitions (contiguous address
ranges polled in batch and written in bulk via FC16/FC0F).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
                             QCheckBox, QPushButton, QFormLayout, QMessageBox)
from PyQt6.QtCore import Qt

from src.utils.constants import (
    REG_TYPES,
    REG_TYPE_LABELS,
    REG_TYPE_HOLDING,
    REG_TYPE_COIL,
    REG_TYPE_DISCRETE,
    REG_TYPE_INPUT,
    DATA_TYPES,
    DATA_TYPE_BOOL,
    DATA_TYPE_LABELS,
    DATA_TYPE_REGISTER_COUNT,
    ACCESS_READ_ONLY,
    ACCESS_READ_WRITE,
    MAX_BLOCK_COUNT_REGS,
    MAX_BLOCK_COUNT_BITS,
)

# Word types whose decoding uses two registers (word swap applies).
_32BIT_TYPES = ("INT32", "UINT32", "FLOAT32", "BCD32")
_READ_ONLY_TABLES = (REG_TYPE_DISCRETE, REG_TYPE_INPUT)
_BIT_TABLES = (REG_TYPE_COIL, REG_TYPE_DISCRETE)

_ACCESS_CHOICES = (
    (ACCESS_READ_WRITE, "Read / Write"),
    (ACCESS_READ_ONLY, "Read Only"),
)


class BlockDialog(QDialog):
    """Dialog for adding or editing a register block definition."""

    def __init__(self, parent=None, block_data: dict = None,
                 is_edit: bool = False) -> None:
        super().__init__(parent)
        self._is_edit = is_edit
        self._block_data = block_data or {}

        self.setWindowTitle("Edit Register Block" if is_edit else "Add Register Block")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setAccessibleName("Register block dialog")

        self._init_ui()
        self._load_data()
        self._apply_type_rules()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Tank Sensors 100-199")
        form.addRow("Name*:", self.name_edit)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self.desc_edit)

        self.type_combo = QComboBox()
        for rt in REG_TYPES:
            self.type_combo.addItem(REG_TYPE_LABELS[rt], rt)
        self.type_combo.currentIndexChanged.connect(self._apply_type_rules)
        form.addRow("Register Type*:", self.type_combo)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 65535)
        self.start_spin.setToolTip("First PLC-native address of the range (0-65535)")
        form.addRow("Start Address*:", self.start_spin)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, MAX_BLOCK_COUNT_BITS)
        self.count_spin.setToolTip(
            "Range size: words for HOLDING/INPUT, bits for COIL/DISCRETE"
        )
        form.addRow("Count*:", self.count_spin)

        self.dtype_combo = QComboBox()
        for dt in DATA_TYPES:
            self.dtype_combo.addItem(DATA_TYPE_LABELS[dt], dt)
        self.dtype_combo.currentIndexChanged.connect(self._apply_type_rules)
        form.addRow("Data Type*:", self.dtype_combo)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.scale_spin.setDecimals(6)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setToolTip("Engineering-unit multiplier (cannot be 0)")
        form.addRow("Scale Factor:", self.scale_spin)

        self.dp_spin = QSpinBox()
        self.dp_spin.setRange(0, 6)
        self.dp_spin.setValue(2)
        form.addRow("Decimal Places:", self.dp_spin)

        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText("e.g. bar, °C, %")
        self.unit_edit.setMaxLength(16)
        form.addRow("Unit:", self.unit_edit)

        self.swap_cb = QCheckBox("Swap word order (low-word first)")
        form.addRow("", self.swap_cb)

        self.access_combo = QComboBox()
        for value, label in _ACCESS_CHOICES:
            self.access_combo.addItem(label, value)
        self.access_combo.setToolTip(
            "DISCRETE / INPUT blocks are protocol read-only"
        )
        form.addRow("Access*:", self.access_combo)

        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Tab grouping on the I/O page")
        form.addRow("Group Name:", self.group_edit)

        self.order_spin = QSpinBox()
        self.order_spin.setRange(0, 1000)
        form.addRow("Row Order:", self.order_spin)

        # Bit-block display options (COIL/DISCRETE only)
        self.val_cb = QCheckBox("Show Numeric Value")
        self.val_cb.setChecked(True)
        form.addRow("", self.val_cb)

        self.on_edit = QLineEdit("ON")
        self.on_edit.setMaxLength(20)
        form.addRow("ON Label:", self.on_edit)

        self.off_edit = QLineEdit("OFF")
        self.off_edit.setMaxLength(20)
        form.addRow("OFF Label:", self.off_edit)

        self.active_cb = QCheckBox("Active (included in polling)")
        self.active_cb.setChecked(True)
        form.addRow("", self.active_cb)

        layout.addLayout(form)

        hint = QLabel(
            "Range reads are batched automatically "
            "(≤125 words / ≤2000 bits per Modbus request)."
        )
        hint.setObjectName("config_info_lbl")
        hint.setWordWrap(True)
        layout.addWidget(hint)

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

    # ------------------------------------------------------------------
    # Dynamic rules
    # ------------------------------------------------------------------
    def _current_type(self) -> str:
        return self.type_combo.currentData() or REG_TYPE_HOLDING

    def _current_dtype(self) -> str:
        return self.dtype_combo.currentData() or DATA_TYPE_BOOL

    def _apply_type_rules(self) -> None:
        """Enforce table-specific limits as the operator makes selections."""
        reg_type = self._current_type()

        # Bit tables: data type is always BOOL, count counts bits
        if reg_type in _BIT_TABLES:
            self.dtype_combo.setEnabled(False)
            self.count_spin.setMaximum(MAX_BLOCK_COUNT_BITS)
        else:
            self.dtype_combo.setEnabled(True)
            self.count_spin.setMaximum(MAX_BLOCK_COUNT_REGS)

        # Read-only protocol tables: access forced to READ_ONLY
        if reg_type in _READ_ONLY_TABLES:
            self.access_combo.setEnabled(False)
            idx = self.access_combo.findData(ACCESS_READ_ONLY)
            if idx >= 0:
                self.access_combo.setCurrentIndex(idx)
        else:
            self.access_combo.setEnabled(True)

        # Word swap only makes sense for two-register types
        self.swap_cb.setEnabled(self._current_dtype() in _32BIT_TYPES)
        if not self.swap_cb.isEnabled():
            self.swap_cb.setChecked(False)

        # Numeric-value flag / labels only apply to bit blocks
        bit_view = reg_type in _BIT_TABLES
        self.val_cb.setVisible(bit_view)
        self.on_edit.setVisible(bit_view)
        self.off_edit.setVisible(bit_view)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        if not self._is_edit or not self._block_data:
            return
        d = self._block_data
        self.name_edit.setText(d.get("name", ""))
        self.desc_edit.setText(d.get("description", ""))
        idx = self.type_combo.findData(d.get("register_type"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.start_spin.setValue(int(d.get("start_address", 0)))
        self.count_spin.setValue(int(d.get("count", 1)))
        idx = self.dtype_combo.findData(d.get("data_type"))
        if idx >= 0:
            self.dtype_combo.setCurrentIndex(idx)
        self.scale_spin.setValue(float(d.get("scale_factor", 1.0) or 1.0))
        self.dp_spin.setValue(int(d.get("decimal_places", 2)))
        self.unit_edit.setText(d.get("unit", ""))
        self.swap_cb.setChecked(bool(d.get("word_swap", 0)))
        idx = self.access_combo.findData(d.get("access"))
        if idx >= 0:
            self.access_combo.setCurrentIndex(idx)
        self.group_edit.setText(d.get("group_name", "") or "")
        self.order_spin.setValue(int(d.get("row_order", 0) or 0))
        self.val_cb.setChecked(bool(d.get("show_value", 1)))
        self.on_edit.setText(d.get("on_label", "ON") or "ON")
        self.off_edit.setText(d.get("off_label", "OFF") or "OFF")
        self.active_cb.setChecked(bool(d.get("is_active", 1)))

    def _on_save(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        if self.scale_spin.value() == 0:
            QMessageBox.warning(self, "Invalid Scale",
                                "Scale factor cannot be zero.")
            self.scale_spin.setFocus()
            return

        reg_type = self._current_type()
        data_type = DATA_TYPE_BOOL if reg_type in _BIT_TABLES else self._current_dtype()

        # Early hint for the whole-element rule (repo validates as well)
        stride = DATA_TYPE_REGISTER_COUNT.get(data_type, 1)
        if reg_type not in _BIT_TABLES and self.count_spin.value() % stride != 0:
            QMessageBox.warning(
                self, "Invalid Count",
                f"Count must be a multiple of {stride} for {data_type} "
                f"(whole elements only)."
            )
            self.count_spin.setFocus()
            return

        access = self.access_combo.currentData()
        if reg_type in _READ_ONLY_TABLES:
            access = ACCESS_READ_ONLY

        self._result = {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "register_type": reg_type,
            "start_address": self.start_spin.value(),
            "count": self.count_spin.value(),
            "data_type": data_type,
            "scale_factor": self.scale_spin.value(),
            "decimal_places": self.dp_spin.value(),
            "unit": self.unit_edit.text().strip(),
            "word_swap": self.swap_cb.isChecked(),
            "access": access,
            "group_name": self.group_edit.text().strip(),
            "row_order": self.order_spin.value(),
            "show_value": self.val_cb.isChecked(),
            "on_label": self.on_edit.text().strip() or "ON",
            "off_label": self.off_edit.text().strip() or "OFF",
            "is_active": self.active_cb.isChecked(),
        }
        self.accept()

    def get_result(self) -> dict:
        return getattr(self, "_result", {})
