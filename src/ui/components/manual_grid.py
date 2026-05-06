"""
ui/components/manual_grid.py
Manual test grid component for individual PLC coil control and live monitoring.
"""

import logging
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from src.ui.app_state import AppState
from src.utils.constants import (
    WRITE_MANUAL, COLOR_NAVY, COLOR_WHITE, COLOR_AMBER
)

log = logging.getLogger(__name__)

ACTION_ROWS = 7  # 0: Header, 1-3: Buttons, 4-6: Values

class ManualGrid(QWidget):
    """
    Grid component allowing manual triggering of PLC coils per parameter.
    """
    
    def __init__(self, 
                 parameters: List[Dict[str, Any]], 
                 app_state: AppState, 
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._params = parameters
        self._state = app_state
        self._n_params = len(parameters)
        
        # Pre-created value cells: {param_name: {row_idx: QTableWidgetItem}}
        self._value_cells: Dict[str, Dict[int, QTableWidgetItem]] = {}
        
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.grid = QTableWidget()
        self.grid.setRowCount(ACTION_ROWS)
        self.grid.setColumnCount(1 + self._n_params)
        
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setVisible(False)
        self.grid.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Style headers
        header_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        mono_font = QFont("Consolas", 10)
        
        # Col 0 Labels
        row_labels = [
            "Action",
            "Supply ON — OK Polarity",
            "Supply ON — Rev. Polarity",
            "Load ON (2A)"
        ]
        
        # Units from first parameter if available
        unit = self._params[0].get("unit", "A") if self._params else "A"
        row_labels.extend([
            f"Output Current ({unit})",
            "Output Voltage (V)",
            "Input Current (A)"
        ])
        
        for row_idx, label in enumerate(row_labels):
            if row_idx == 0:
                item = QTableWidgetItem(label)
                item.setFont(header_font)
                item.setBackground(QColor(COLOR_NAVY))
                item.setForeground(QColor(COLOR_WHITE))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid.setItem(0, 0, item)
            elif 1 <= row_idx <= 3:
                btn = QPushButton(label)
                btn.setStyleSheet(f"background:{COLOR_NAVY}; color:{COLOR_WHITE}; font-weight:bold; border:none; padding:5px;")
                # Label buttons in col 0 are typically read-only / non-functional markers
                btn.setEnabled(False) 
                self.grid.setCellWidget(row_idx, 0, btn)
            else:
                item = QTableWidgetItem(label)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setFont(header_font)
                self.grid.setItem(row_idx, 0, item)
                
        # Data Columns
        for col_idx, param in enumerate(self._params, start=1):
            name = param["param_name"]
            self._value_cells[name] = {}
            
            # Row 0: Parameter Header
            header_item = QTableWidgetItem(param.get("display_name", name))
            header_item.setFont(header_font)
            header_item.setBackground(QColor(COLOR_NAVY))
            header_item.setForeground(QColor(COLOR_WHITE))
            header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Tooltip: full name + register info
            reg_info = f"D{param.get('register', '??')}"
            header_item.setToolTip(f"{name}\nRegister: {reg_info}")
            self.grid.setItem(0, col_idx, header_item)
            
            # Rows 1-3: Buttons
            actions = ["supply_ok", "supply_rev", "load_on"]
            labels = ["OK", "REV", "LOAD"]
            for i, action in enumerate(actions, start=1):
                btn = QPushButton(labels[i-1])
                btn.setStyleSheet(f"background:{COLOR_NAVY}; color:{COLOR_WHITE}; border-radius:2px;")
                # Use default param binding
                btn.clicked.connect(lambda checked, a=action, p=param: self._trigger_action(a, p))
                self.grid.setCellWidget(i, col_idx, btn)
                
            # Rows 4-6: Values
            for row_idx in [4, 5, 6]:
                val_item = QTableWidgetItem("0.000")
                val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                val_item.setFont(mono_font)
                self.grid.setItem(row_idx, col_idx, val_item)
                self._value_cells[name][row_idx] = val_item
                
        # Column resizing
        header = self.grid.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for i in range(1, 1 + self._n_params):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            
        layout.addWidget(self.grid)

    def _trigger_action(self, action: str, param: Dict[str, Any]) -> None:
        """
        Write coil to PLC via WriteManager.
        coil_addr = 400 + (param_order * 3) + action_offset
        """
        profile = self._state.plc_profile or {}
        # brand = profile.get("brand", "mitsubishi")
        param_order = param.get("param_order", 0)
        action_offsets = {
            "supply_ok":  0,
            "supply_rev": 1,
            "load_on":    2,
        }
        
        base_coil = 400 # Default for manual mode M coils
        # In practice, this might be brand dependent, but following spec formula
        coil_num = base_coil + (param_order * 3) + action_offsets.get(action, 0)
        
        # Flash button amber during write
        btn = self._get_action_button(param["param_name"], action)
        if btn:
            btn.setStyleSheet(f"background:{COLOR_AMBER}; color:{COLOR_WHITE};")
            QTimer.singleShot(400, lambda: btn.setStyleSheet(
                f"background:{COLOR_NAVY}; color:{COLOR_WHITE};"
            ))
            
        # Write via WriteManager (logged + verified)
        # Note: write_and_verify is usually for D registers. 
        # The spec says d_register=0 as a proxy for coil logging.
        if self._state.write_manager:
            self._state.write_manager.write_and_verify(
                d_register=0,
                value=1,
                reason=WRITE_MANUAL,
                operator_id=self._state.current_user["id"] if self._state.current_user else 0
            )
            
        # Actually write coil
        try:
            driver = self._state.connection_manager.get_driver()
            result = driver.write_coil(coil_num, True)
            if not result.success:
                log.warning(f"Manual coil write failed: M{coil_num}")
            else:
                log.info(f"Manual: {action} → {param['param_name']} coil M{coil_num}")
        except Exception as e:
            log.error(f"Failed to write manual coil M{coil_num}: {e}")

    def update_readings(self, readings: Dict[str, Any]) -> None:
        """
        readings = {param_name: ParameterReading}
        Updates value cells ONLY.
        """
        for param in self._params:
            name = param["param_name"]
            if name not in readings:
                continue
            
            r = readings[name]
            # Row 4: output current (scaled value)
            item4 = self._value_cells.get(name, {}).get(4)
            if item4:
                # Assuming r has scaled_value property
                val = getattr(r, "scaled_value", 0.0)
                item4.setText(f"{val:.3f}")
                
            # Row 5: output voltage (use scaled as proxy per spec)
            item5 = self._value_cells.get(name, {}).get(5)
            if item5:
                val = getattr(r, "scaled_value", 0.0)
                item5.setText(f"{val:.2f}")
                
            # Row 6: input current (raw / 10 as proxy per spec)
            item6 = self._value_cells.get(name, {}).get(6)
            if item6:
                raw = getattr(r, "raw_value", 0.0)
                item6.setText(f"{raw / 10:.3f}")

    def reset_all(self) -> None:
        """Resets all reading cells to 0.000."""
        for name in [p["param_name"] for p in self._params]:
            for row_idx in [4, 5, 6]:
                item = self._value_cells.get(name, {}).get(row_idx)
                if item:
                    item.setText("0.000")

    def set_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable all action buttons."""
        for col in range(1, self._n_params + 1):
            for row in range(1, 4):
                btn = self.grid.cellWidget(row, col)
                if isinstance(btn, QPushButton):
                    btn.setEnabled(enabled)

    def _get_action_button(self, param_name: str, action: str) -> Optional[QPushButton]:
        """Helper to find button widget for specific param/action."""
        action_row = {
            "supply_ok": 1,
            "supply_rev": 2,
            "load_on": 3,
        }.get(action)
        
        if action_row is None:
            return None
            
        for i, p in enumerate(self._params):
            if p["param_name"] == param_name:
                return self.grid.cellWidget(action_row, i + 1)
        return None
