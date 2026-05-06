# src/ui/components/plc_block_editor.py
"""
PLCBlockEditor — Tab 4 of the Settings screen.

Lets Admin users configure and write the raw model-identification
block registers (e.g. D3000…D3005) that the PLC reads when a model
is selected on the login screen.
"""

import csv
import json
import logging
import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem,
    QGroupBox, QAbstractItemView, QHeaderView,
    QFrame, QFileDialog, QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from src.ui.app_state import AppState

logger = logging.getLogger(__name__)


class PLCBlockEditor(QWidget):
    """
    Tab 4 widget — raw D3000 model block register values.

    Allows editing, importing/exporting, writing and reading back
    the model identification block in the PLC.
    """

    def __init__(self, app_state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._model_id: Optional[int] = None

        self._setup_ui()

    # ==================================================================
    # UI Construction
    # ==================================================================

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self._build_warning_banner())
        root.addWidget(self._build_config_group())
        root.addWidget(self._build_values_group())
        root.addWidget(self._build_write_group())
        root.addLayout(self._build_save_bar())

    # ── Warning banner ─────────────────────────────────────────────────

    def _build_warning_banner(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #fff3cd; border: 1px solid #ffc107;"
            " border-radius: 4px; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)

        icon = QLabel("⚠")
        icon.setStyleSheet("font-size: 20px; color: #856404; background: transparent; border: none;")
        icon.setFixedWidth(28)

        text = QLabel(
            "The model block is written <b>atomically</b> to the PLC when a model "
            "is selected on the login screen.  "
            "Values are raw 16-bit integers (0–65535).  "
            "Read your PLC program to find the correct values.  "
            "Example: H25=37, H26=38, H24=36."
        )
        text.setWordWrap(True)
        text.setStyleSheet(
            "color: #856404; font-size: 12px; background: transparent; border: none;"
        )

        layout.addWidget(icon)
        layout.addWidget(text, stretch=1)
        return frame

    # ── Block configuration group ──────────────────────────────────────

    def _build_config_group(self) -> QGroupBox:
        grp = QGroupBox("Block Configuration")
        form = QFormLayout(grp)
        form.setSpacing(8)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 65535)
        self.start_spin.setValue(0)
        self.start_spin.setToolTip(
            "First D-register of the model block\n"
            "e.g. enter 3000 for D3000"
        )
        self.start_spin.setFixedWidth(160)

        self.block_size_lbl = QLabel("0 registers")
        self.block_size_lbl.setStyleSheet("color: #5a6a8a;")

        form.addRow(QLabel("Start Register (D):"), self.start_spin)
        form.addRow(QLabel("Block Size:"), self.block_size_lbl)
        return grp

    # ── Register values group ──────────────────────────────────────────

    def _build_values_group(self) -> QGroupBox:
        grp = QGroupBox("Register Values")
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_add_val = QPushButton("+ Add Value")
        self.btn_add_val.setObjectName("btn_success")
        self.btn_add_val.setFixedWidth(100)
        self.btn_add_val.clicked.connect(self._on_add_value)

        self.btn_remove_val = QPushButton("− Remove Last")
        self.btn_remove_val.setObjectName("btn_secondary")
        self.btn_remove_val.setFixedWidth(110)
        self.btn_remove_val.clicked.connect(self._on_remove_last)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setObjectName("btn_danger")
        self.btn_clear_all.setFixedWidth(80)
        self.btn_clear_all.clicked.connect(self._on_clear_all)

        toolbar.addWidget(self.btn_add_val)
        toolbar.addWidget(self.btn_remove_val)
        toolbar.addWidget(self.btn_clear_all)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Values table
        self.values_table = QTableWidget()
        self.values_table.setColumnCount(2)
        self.values_table.setHorizontalHeaderLabels(["Index", "Value (0–65535)"])
        hdr = self.values_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.values_table.setColumnWidth(0, 60)
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.values_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.values_table.setAlternatingRowColors(True)
        self.values_table.setFixedHeight(160)
        layout.addWidget(self.values_table)

        # Import / Export row
        io_row = QHBoxLayout()
        self.btn_import = QPushButton("Import from CSV")
        self.btn_import.setObjectName("btn_secondary")
        self.btn_import.clicked.connect(self._on_import_csv)

        self.btn_export = QPushButton("Export to CSV")
        self.btn_export.setObjectName("btn_secondary")
        self.btn_export.clicked.connect(self._on_export_csv)

        io_row.addWidget(self.btn_import)
        io_row.addWidget(self.btn_export)
        io_row.addStretch()
        layout.addLayout(io_row)
        return grp

    # ── Write to PLC group ─────────────────────────────────────────────

    def _build_write_group(self) -> QGroupBox:
        grp = QGroupBox("Write to PLC")
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        # Last pushed values display
        self.current_block_lbl = QLabel("Last pushed: (none)")
        self.current_block_lbl.setStyleSheet(
            "color: #5a6a8a; font-size: 12px; font-style: italic;"
        )
        self.current_block_lbl.setWordWrap(True)
        layout.addWidget(self.current_block_lbl)

        btn_row = QHBoxLayout()
        self.btn_write_now = QPushButton("Write Block Now")
        self.btn_write_now.setObjectName("btn_success")
        self.btn_write_now.clicked.connect(self._on_write_block_now)

        self.btn_read_back = QPushButton("Read Block from PLC")
        self.btn_read_back.setObjectName("btn_secondary")
        self.btn_read_back.clicked.connect(self._on_read_block)

        btn_row.addWidget(self.btn_write_now)
        btn_row.addWidget(self.btn_read_back)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return grp

    # ── Bottom save bar ────────────────────────────────────────────────

    def _build_save_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        self.btn_save_db = QPushButton("Save to DB")
        self.btn_save_db.setStyleSheet(
            "background: #1e2d4a; color: white; min-width: 110px;"
        )
        self.btn_save_db.clicked.connect(self._on_save_to_db)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")

        bar.addWidget(self.btn_save_db)
        bar.addStretch()
        bar.addWidget(self.status_lbl)
        return bar

    # ==================================================================
    # Public API
    # ==================================================================

    def load_model(self, model_id: int) -> None:
        """Load block configuration from *model_id* into the editor."""
        self._model_id = model_id
        model = self._app_state.model_repo.get_model(model_id)
        if not model:
            return

        start = model.get("plc_block_start_register", 0)
        self.start_spin.blockSignals(True)
        self.start_spin.setValue(start)
        self.start_spin.blockSignals(False)

        values = model.get("plc_block_values", [])
        # plc_block_values is already decoded by model_repo (JSON → list)
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except Exception:
                values = []

        self._populate_values_table(values)
        self.status_lbl.setText("")
        logger.debug(
            "PLCBlockEditor: loaded model_id=%d, start=D%d, values=%s",
            model_id, start, values,
        )

    # ==================================================================
    # Values table helpers
    # ==================================================================

    def _populate_values_table(self, values: list) -> None:
        self.values_table.setRowCount(0)
        for i, v in enumerate(values):
            self._insert_value_row(i, int(v))
        self._update_block_size()

    def _insert_value_row(self, index: int, value: int = 0) -> None:
        row = self.values_table.rowCount()
        self.values_table.insertRow(row)

        idx_item = QTableWidgetItem(str(index))
        idx_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        idx_item.setForeground(QColor("#6c757d"))
        self.values_table.setItem(row, 0, idx_item)

        spin = QSpinBox()
        spin.setRange(0, 65535)
        spin.setValue(value)
        spin.valueChanged.connect(self._update_block_size)   # keeps size updated
        self.values_table.setCellWidget(row, 1, spin)

    def _get_values_from_table(self) -> list[int]:
        values: list[int] = []
        for row in range(self.values_table.rowCount()):
            spin: QSpinBox = self.values_table.cellWidget(row, 1)
            if spin:
                values.append(spin.value())
        return values

    def _update_block_size(self) -> None:
        n = self.values_table.rowCount()
        self.block_size_lbl.setText(f"{n} register{'s' if n != 1 else ''}")

    # ==================================================================
    # Toolbar slots
    # ==================================================================

    def _on_add_value(self) -> None:
        idx = self.values_table.rowCount()
        self._insert_value_row(idx, 0)
        self._update_block_size()

    def _on_remove_last(self) -> None:
        n = self.values_table.rowCount()
        if n > 0:
            self.values_table.removeRow(n - 1)
            self._update_block_size()

    def _on_clear_all(self) -> None:
        from src.ui.dialogs.confirm_dialog import ConfirmDialog
        if ConfirmDialog.ask(
            self, "Clear All",
            "Remove all register values from the list?",
            confirm_text="Clear",
            danger=True,
        ):
            self.values_table.setRowCount(0)
            self._update_block_size()

    # ==================================================================
    # CSV import / export
    # ==================================================================

    def _on_import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Block Values", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            values: list[int] = []
            with open(path, newline="") as fh:
                reader = csv.reader(fh)
                for row in reader:
                    for cell in row:
                        cell = cell.strip()
                        if cell.isdigit() or (
                            cell.startswith("-") and cell[1:].isdigit()
                        ):
                            values.append(int(cell))
            self._populate_values_table(values)
            self._show_status(f"Imported {len(values)} values from CSV.", success=True)
            logger.info("PLCBlockEditor: imported %d values from %s", len(values), path)
        except Exception as exc:
            self._show_status(f"Import failed: {exc}", success=False)
            logger.exception("PLCBlockEditor: CSV import error")

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Block Values", "block_values.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        values = self._get_values_from_table()
        try:
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(values)
            self._show_status(
                f"Exported {len(values)} values to {os.path.basename(path)}.",
                success=True,
            )
            logger.info("PLCBlockEditor: exported to %s", path)
        except Exception as exc:
            self._show_status(f"Export failed: {exc}", success=False)
            logger.exception("PLCBlockEditor: CSV export error")

    # ==================================================================
    # Write to PLC
    # ==================================================================

    def _on_write_block_now(self) -> None:
        """Write the current block values directly to the PLC via WriteManager."""
        start = self.start_spin.value()
        values = self._get_values_from_table()

        if start == 0:
            QMessageBox.warning(
                self,
                "Start Register Not Set",
                "Set the start D-register before writing.",
            )
            return
        if not values:
            QMessageBox.warning(
                self,
                "No Values",
                "Add at least one register value before writing.",
            )
            return
        if not self._app_state.is_plc_connected:
            QMessageBox.warning(
                self,
                "PLC Not Connected",
                "Cannot write — PLC is not connected.",
            )
            return

        model = {
            "id": self._model_id,
            "name": "",
            "plc_block_start_register": start,
            "plc_block_values": json.dumps(values),
        }
        operator_id = (
            self._app_state.current_user.get("id", 0)
            if self._app_state.current_user else 0
        )

        try:
            result = self._app_state.write_manager.write_model_block(
                model, operator_id
            )
        except Exception as exc:
            self._show_status(f"Write error: {exc}", success=False)
            logger.exception("PLCBlockEditor: write_model_block error")
            return

        if result.success and result.verified:
            self._show_status("Block written and verified ✓", success=True)
            self.current_block_lbl.setText(f"Last pushed: {values}")
            logger.info(
                "PLCBlockEditor: block written D%d, values=%s", start, values
            )
        else:
            err = getattr(result, "error", "Unknown error")
            self._show_status(f"Write failed: {err}", success=False)
            logger.error("PLCBlockEditor: write_model_block failed — %s", err)

    # ==================================================================
    # Read back from PLC
    # ==================================================================

    def _on_read_block(self) -> None:
        """Read back current block registers from the PLC and compare."""
        start = self.start_spin.value()
        n     = self.values_table.rowCount()

        if start == 0 or n == 0:
            QMessageBox.information(
                self,
                "Nothing to Read",
                "Set the start register and add values first.",
            )
            return
        if not self._app_state.is_plc_connected:
            QMessageBox.warning(
                self, "PLC Not Connected", "Cannot read — PLC is not connected."
            )
            return

        cm = self._app_state.connection_manager
        driver = cm.get_driver() if (cm and hasattr(cm, "get_driver")) else None
        if not driver:
            return

        result = driver.read_holding_registers(start, n)
        if not result.success:
            self._show_status(
                f"Read failed: {getattr(result, 'error', '?')}", success=False
            )
            return

        plc_vals  = result.values or []
        db_vals   = self._get_values_from_table()
        match     = (plc_vals == db_vals)

        self.current_block_lbl.setText(
            f"PLC readback: {plc_vals}  "
            f"{'✓ Matches DB' if match else '✗ Differs from DB'}"
        )
        colour = "#1a6b3a" if match else "#c0392b"
        self.current_block_lbl.setStyleSheet(
            f"color: {colour}; font-size: 12px;"
        )
        logger.info(
            "PLCBlockEditor: readback D%d…D%d = %s, match=%s",
            start, start + n - 1, plc_vals, match,
        )

    # ==================================================================
    # Save to DB
    # ==================================================================

    def _on_save_to_db(self) -> None:
        if not self._model_id:
            return
        start  = self.start_spin.value()
        values = self._get_values_from_table()
        try:
            self._app_state.model_repo.update_model(
                self._model_id,
                plc_block_start_register=start,
                plc_block_values=values,
            )
            self._show_status("Saved to database ✓", success=True)
            logger.info(
                "PLCBlockEditor: saved model_id=%d block start=D%d values=%s",
                self._model_id, start, values,
            )
        except Exception as exc:
            self._show_status(f"Save error: {exc}", success=False)
            logger.exception("PLCBlockEditor: save to DB failed")

    # ==================================================================
    # Status helper
    # ==================================================================

    def _show_status(self, msg: str, success: bool) -> None:
        colour = "#1a6b3a" if success else "#c0392b"
        self.status_lbl.setText(msg)
        self.status_lbl.setStyleSheet(
            f"color: {colour}; font-size: 12px; font-weight: 600;"
        )
        def _clear():
            try:
                if self.status_lbl:
                    self.status_lbl.setText("")
            except RuntimeError:
                pass
        QTimer.singleShot(4000, _clear)
