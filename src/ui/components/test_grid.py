# src/ui/components/test_grid.py
import logging
from typing import Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt

from src.utils.constants import RESULT_PASS, RESULT_FAIL, RESULT_BYPASS, RESULT_PENDING

logger = logging.getLogger(__name__)

class TestGrid(QWidget):
    """
    Dynamic test grid for a specific test section (e.g. WITHOUT_LOAD).
    Builds column headers dynamically from parameters list.
    """
    def __init__(self,
                 section_title: str,
                 row_labels: List[str],
                 parameters: List[Dict[str, Any]],
                 parent: QWidget | None = None):
        """
        section_title: "Without Load Testing" etc.
        row_labels: list of measurement row names
        parameters: list of param dicts from DB
        """
        super().__init__(parent)
        self._section_title = section_title
        self._row_labels = row_labels
        self._params = parameters
        self._n_cols = len(parameters)

        # Pre-created cell dict (NO FLICKER pattern)
        self._cells: Dict[str, Dict[str, QTableWidgetItem]] = {}
        self._result_cells: Dict[str, QTableWidgetItem] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Section header
        self.section_header = QFrame()
        self.section_header.setStyleSheet("background-color: #1e2d4a; border-radius: 4px;")
        header_layout = QVBoxLayout(self.section_header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        
        self.title_label = QLabel(self._section_title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(self.title_label)
        
        layout.addWidget(self.section_header)

        # Grid
        self.grid = QTableWidget()
        
        # We need N + 2 rows total: 1 custom header row + len(row_labels) + 1 result row
        total_rows = len(self._row_labels) + 2
        self.grid.setRowCount(total_rows)
        self.grid.setColumnCount(self._n_cols + 1)
        self.grid.setAlternatingRowColors(True)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.horizontalHeader().hide()
        
        # Layout columns
        self.grid.setColumnWidth(0, 160)
        
        for i in range(1, self._n_cols + 1):
            self.grid.setColumnWidth(i, 100)
            self.grid.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            
        # Row 0: row labels corner
        corner_item = QTableWidgetItem("")
        self.grid.setItem(0, 0, corner_item)

        # Row 1..N: row labels
        for idx, label in enumerate(self._row_labels):
            item = QTableWidgetItem(label)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setBackground(QColor("#e8ecf2"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.grid.setItem(idx + 1, 0, item)
            
        # Last row: Result label
        result_label_item = QTableWidgetItem("Result")
        result_label_font = result_label_item.font()
        result_label_font.setBold(True)
        result_label_item.setFont(result_label_font)
        result_label_item.setBackground(QColor("#1e2d4a"))
        result_label_item.setForeground(QColor("#ffffff"))
        result_label_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.grid.setItem(total_rows - 1, 0, result_label_item)

        # Columns 1..N: parameter columns
        for col_idx, param in enumerate(self._params):
            grid_col = col_idx + 1
            param_name = param["param_name"]
            display_name = param["display_name"]
            unit = param.get("unit", "")
            
            # Row 0 (header)
            header_item = QTableWidgetItem(display_name)
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            header_item.setBackground(QColor("#1e2d4a"))
            header_item.setForeground(QColor("#ffffff"))
            header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            header_item.setToolTip(f"{param_name} ({unit})")
            self.grid.setItem(0, grid_col, header_item)
            
            self._cells[param_name] = {}
            
            # Rows 1..N (data)
            for row_idx, label in enumerate(self._row_labels):
                grid_row = row_idx + 1
                cell_item = QTableWidgetItem("")
                cell_item.setBackground(QColor("#ffffff"))
                cell_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                font = QFont("Consolas", 10)
                font.setStyleHint(QFont.StyleHint.Monospace)
                cell_item.setFont(font)
                
                self.grid.setItem(grid_row, grid_col, cell_item)
                self._cells[param_name][label] = cell_item
                
            # Last row (result)
            res_item = QTableWidgetItem(RESULT_PENDING)
            res_item.setBackground(QColor("#d0d8e8"))
            res_item.setForeground(QColor("#1a1a2e"))
            res_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            res_item.setFont(res_font)
            res_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.grid.setItem(total_rows - 1, grid_col, res_item)
            self._result_cells[param_name] = res_item
            
        layout.addWidget(self.grid)

    def update_cell(self,
                    param_name: str,
                    row_label: str,
                    value: float,
                    unit: str = "") -> None:
        """Update ONE cell — no table refresh."""
        item = self._cells.get(param_name, {}).get(row_label)
        if not item:
            return
            
        if unit:
            item.setText(f"{value:.2f} {unit}")
        else:
            item.setText(f"{value:.2f}")

    def update_result(self, param_name: str, result: str) -> None:
        """Update result cell color + text."""
        item = self._result_cells.get(param_name)
        if not item:
            return
            
        colors = {
            RESULT_PASS: ("#1a6b3a", "#ffffff"),
            RESULT_FAIL: ("#c0392b", "#ffffff"),
            RESULT_BYPASS: ("#6c757d", "#ffffff"),
            RESULT_PENDING: ("#d0d8e8", "#1a1a2e"),
        }
        
        bg, fg = colors.get(result, ("#d0d8e8", "#1a1a2e"))
        item.setBackground(QColor(bg))
        item.setForeground(QColor(fg))
        item.setText(result)
        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

    def update_from_readings(self,
                             readings: Dict[str, int],
                             evaluator: Any) -> None:
        """
        Called every poll. Updates all cells for this section.
        readings = {param_name: raw_value}
        evaluator used to get scaled value + unit.
        """
        for param in self._params:
            name = param["param_name"]
            raw = readings.get(name, 0)
            scaled = raw * param.get("scale_factor", 1.0)
            unit = param.get("unit", "")
            
            if self._row_labels:
                self.update_cell(name, self._row_labels[0], scaled, unit)

    def update_from_results(self, results: List[Any]) -> None:
        """Update result row from EvaluationResult list."""
        for r in results:
            if r.param_name in self._result_cells:
                self.update_result(r.param_name, r.result)

    def reset_all(self) -> None:
        for param in self._params:
            name = param["param_name"]
            for label in self._row_labels:
                item = self._cells.get(name, {}).get(label)
                if item:
                    item.setText("---")
            self.update_result(name, RESULT_PENDING)

    def highlight_column(self, param_name: str, active: bool) -> None:
        """Bold/highlight column header during test."""
        col = self._get_col_index(param_name)
        if col < 0:
            return
            
        header_item = self.grid.item(0, col)
        if header_item:
            font = header_item.font()
            font.setUnderline(active)
            header_item.setFont(font)

    def _get_col_index(self, param_name: str) -> int:
        for i, p in enumerate(self._params):
            if p["param_name"] == param_name:
                return i + 1  # +1 for label col
        return -1
