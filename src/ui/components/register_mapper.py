"""
register_mapper.py — Universal PLC Monitor
Grid for mapping test parameters to PLC register addresses.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSpinBox,
    QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ui.app_state import AppState

logger = logging.getLogger(__name__)


class RegisterMapper(QWidget):
    """
    Editable table mapping parameter IDs to PLC register addresses.
    Emits registers_saved(model_id) after a successful save.
    """

    registers_saved = pyqtSignal(int)

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

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Parameter", "Measured Reg (D)", "Result Reg", "Min Reg", "Max Reg", "Role"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(300)
        root.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Mappings")
        self.btn_save.setObjectName("btn_success")
        self.btn_save.setFixedWidth(130)
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

        self.title_lbl.setText(f"Register Mapping — {model.get('name', f'Model #{model_id}')}")
        params = self._app_state.param_repo.get_model_parameters(model_id)

        self.table.setRowCount(0)
        for p in params:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(
                p.get("display_name") or p.get("param_name", "")
            ))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, p.get("id"))

            for col, key in [(1, "measured_register"), (2, "result_register"),
                             (3, "limit_min_register"), (4, "limit_max_register")]:
                spin = QSpinBox()
                spin.setRange(0, 99999)
                spin.setValue(p.get(key, 0))
                self.table.setCellWidget(row, col, spin)

            role_combo = QComboBox()
            role_combo.addItems(["PARAMETER", "COUNTER", "STATUS"])
            role_combo.setCurrentText(p.get("role", "PARAMETER"))
            self.table.setCellWidget(row, 5, role_combo)

    def _on_save(self) -> None:
        if not self._model_id:
            return
        try:
            for row in range(self.table.rowCount()):
                param_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if not param_id:
                    continue
                measured = self.table.cellWidget(row, 1).value()
                result = self.table.cellWidget(row, 2).value()
                min_reg = self.table.cellWidget(row, 3).value()
                max_reg = self.table.cellWidget(row, 4).value()

                self._app_state.param_repo.update_parameter_registers(
                    param_id,
                    measured_register=measured,
                    result_register=result,
                    limit_min_register=min_reg,
                    limit_max_register=max_reg,
                )
            self.status_lbl.setText("Saved ✓")
            self.status_lbl.setProperty("status", "success")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            self.registers_saved.emit(self._model_id)
        except Exception as exc:
            self.status_lbl.setText(f"Error: {exc}")
            self.status_lbl.setProperty("status", "error")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            logger.exception("RegisterMapper save failed")
