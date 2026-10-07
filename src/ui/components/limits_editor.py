"""
limits_editor.py — Universal PLC Monitor
Editor for setting min/max limits for test parameters.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ui.app_state import AppState

logger = logging.getLogger(__name__)


class LimitsEditor(QWidget):
    """
    Editable table for parameter limit values (min/max).
    Emits limits_saved(model_id) after a successful save.
    """

    limits_saved = pyqtSignal(int)

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

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Parameter", "Min Limit", "Max Limit", "Unit"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(300)
        root.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Limits")
        self.btn_save.setObjectName("btn_success")
        self.btn_save.setFixedWidth(120)
        self.btn_save.clicked.connect(self._on_save)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 11px;")

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

        self.title_lbl.setText(f"Limit Values — {model.get('name', f'Model #{model_id}')}")
        params = self._app_state.param_repo.get_model_parameters(model_id)

        self.table.setRowCount(0)
        for p in params:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(
                p.get("display_name") or p.get("param_name", "")
            ))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, p.get("id"))

            min_spin = QDoubleSpinBox()
            min_spin.setRange(-99999, 99999)
            min_spin.setDecimals(2)
            min_spin.setValue(p.get("limit_min_value", 0))
            self.table.setCellWidget(row, 1, min_spin)

            max_spin = QDoubleSpinBox()
            max_spin.setRange(-99999, 99999)
            max_spin.setDecimals(2)
            max_spin.setValue(p.get("limit_max_value", 9999))
            self.table.setCellWidget(row, 2, max_spin)

            self.table.setItem(row, 3, QTableWidgetItem(p.get("unit", "")))

    def _on_save(self) -> None:
        if not self._model_id:
            return
        try:
            for row in range(self.table.rowCount()):
                param_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if not param_id:
                    continue
                min_val = self.table.cellWidget(row, 1).value()
                max_val = self.table.cellWidget(row, 2).value()
                self._app_state.param_repo.update_parameter_limits(param_id, min_val, max_val)

            self.status_lbl.setText("Saved ✓")
            self.status_lbl.setProperty("status", "success")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            self.limits_saved.emit(self._model_id)
        except Exception as exc:
            self.status_lbl.setText(f"Error: {exc}")
            self.status_lbl.setProperty("status", "error")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            logger.exception("LimitsEditor save failed")
