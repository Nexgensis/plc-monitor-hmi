"""
param_editor.py — Universal PLC Monitor
Table editor for test parameters of a selected model.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDoubleSpinBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ui.app_state import AppState

logger = logging.getLogger(__name__)


class ParamEditor(QWidget):
    """
    Editable table of model parameters (name, display, module, unit, limits, etc.).
    Emits params_saved(model_id) after a successful save.
    """

    params_saved = pyqtSignal(int)

    def __init__(self, app_state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._model_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.title_lbl = QLabel("No model selected")
        self.title_lbl.setObjectName("editor_title")
        root.addWidget(self.title_lbl)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Display", "Module", "Unit", "Min", "Max", "Enabled"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(300)
        root.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Row")
        self.btn_add.setFixedWidth(90)
        self.btn_add.clicked.connect(self._on_add_row)

        self.btn_del = QPushButton("− Delete Selected")
        self.btn_del.setFixedWidth(120)
        self.btn_del.clicked.connect(self._on_delete_row)

        self.btn_save = QPushButton("Save Parameters")
        self.btn_save.setObjectName("btn_success")
        self.btn_save.setFixedWidth(130)
        self.btn_save.clicked.connect(self._on_save)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 11px;")

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch()
        btn_row.addWidget(self.status_lbl)
        root.addLayout(btn_row)

    def load_model(self, model_id: int) -> None:
        self._model_id = model_id
        model = self._app_state.model_repo.get_model(model_id)
        if not model:
            self.title_lbl.setText("Model not found")
            return

        self.title_lbl.setText(f"Parameters — {model.get('name', f'Model #{model_id}')}")
        params = self._app_state.param_repo.get_model_parameters(model_id)

        self.table.setRowCount(0)
        for p in params:
            self._insert_row(p)

    def _insert_row(self, p: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(p.get("param_name", "")))
        self.table.setItem(row, 1, QTableWidgetItem(p.get("display_name", "")))
        self.table.setItem(row, 2, QTableWidgetItem(p.get("module_name", "")))
        self.table.setItem(row, 3, QTableWidgetItem(p.get("unit", "")))

        min_spin = QDoubleSpinBox()
        min_spin.setRange(-99999, 99999)
        min_spin.setValue(p.get("limit_min_value", 0))
        self.table.setCellWidget(row, 4, min_spin)

        max_spin = QDoubleSpinBox()
        max_spin.setRange(-99999, 99999)
        max_spin.setValue(p.get("limit_max_value", 9999))
        self.table.setCellWidget(row, 5, max_spin)

        enabled_cb = QCheckBox()
        enabled_cb.setChecked(bool(p.get("enabled", 1)))
        self.table.setCellWidget(row, 6, enabled_cb)

        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, p.get("id"))

    def _on_add_row(self) -> None:
        if not self._model_id:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("new_param"))
        self.table.setItem(row, 1, QTableWidgetItem("New Parameter"))
        self.table.setItem(row, 2, QTableWidgetItem("Module A"))
        self.table.setItem(row, 3, QTableWidgetItem("mV"))

        min_spin = QDoubleSpinBox()
        min_spin.setRange(-99999, 99999)
        self.table.setCellWidget(row, 4, min_spin)

        max_spin = QDoubleSpinBox()
        max_spin.setRange(-99999, 99999)
        max_spin.setValue(9999)
        self.table.setCellWidget(row, 5, max_spin)

        enabled_cb = QCheckBox()
        enabled_cb.setChecked(True)
        self.table.setCellWidget(row, 6, enabled_cb)

    def _on_delete_row(self) -> None:
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _on_save(self) -> None:
        if not self._model_id:
            return
        try:
            for row in range(self.table.rowCount()):
                param_id_item = self.table.item(row, 0)
                param_id = param_id_item.data(Qt.ItemDataRole.UserRole) if param_id_item else None
                name = self.table.item(row, 0).text()
                display = self.table.item(row, 1).text()
                module = self.table.item(row, 2).text()
                unit = self.table.item(row, 3).text()
                min_val = self.table.cellWidget(row, 4).value()
                max_val = self.table.cellWidget(row, 5).value()
                enabled = self.table.cellWidget(row, 6).isChecked()

                if param_id:
                    self._app_state.param_repo.update_parameter_info(
                        param_id, param_name=name, display_name=display,
                        module_name=module, unit=unit, enabled=enabled,
                    )
                else:
                    self._app_state.param_repo.add_parameter(
                        self._model_id, name, display, module, row,
                        unit=unit, limit_min_value=min_val, limit_max_value=max_val,
                        enabled=enabled,
                    )
            self.status_lbl.setText("Saved ✓")
            self.status_lbl.setProperty("status", "success")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            self.params_saved.emit(self._model_id)
        except Exception as exc:
            self.status_lbl.setText(f"Error: {exc}")
            self.status_lbl.setProperty("status", "error")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            logger.exception("ParamEditor save failed")
