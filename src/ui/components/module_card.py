"""
ModuleCard component.
Displays all signals and real-time status for a single hardware module.
"""
import logging
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt
from src.utils.constants import (
    RESULT_PASS, RESULT_FAIL, RESULT_PENDING, RESULT_BYPASS,
    DARK_PASS, DARK_FAIL, DARK_TEXT_PRIMARY,
    LIGHT_PASS, LIGHT_FAIL, LIGHT_TEXT_PRIMARY
)
from src.plc.data_model import ParameterReading

logger = logging.getLogger(__name__)

class ModuleCard(QFrame):
    def __init__(self, module_name: str, parameters: list[dict], app_state=None):
        super().__init__()
        self.setObjectName("module_card")
        self._module_name = module_name
        self._params = parameters
        self._app_state = app_state
        self._value_labels: dict[str, QLabel] = {}
        self._mvd_labels: dict[str, QLabel] = {}
        self.result_lbl: QLabel = None
        
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)
        
        # MODULE HEADER
        header_layout = QHBoxLayout()
        
        icons = {
            "DIPPER": "⬛",
            "BLINKER": "🔶",
            "HORN": "📯",
            "WIPER": "🌀"
        }
        icon_str = icons.get(self._module_name.upper(), "⚙️")
        
        icon_lbl = QLabel(icon_str)
        name_lbl = QLabel(self._module_name.upper())
        name_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #888888; border: none; background: transparent;")
        
        self.result_lbl = QLabel("● PENDING")
        self.result_lbl.setObjectName("result_pending")
        self.result_lbl.setStyleSheet("font-size: 11px; font-weight: bold; border: none; background: transparent;")
        
        header_layout.addWidget(icon_lbl)
        header_layout.addWidget(name_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.result_lbl)
        
        main_layout.addLayout(header_layout)
        
        # SIGNAL GRID
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(6)
        
        cols = 2 if len(self._params) > 1 else 1
        
        for i, param in enumerate(self._params):
            name = param["param_name"]
            disp_name = param.get("display_name", name)
            unit = param.get("unit", "")
            
            sig_frame = QFrame()
            sig_frame.setObjectName("card")
            sig_frame.setStyleSheet("background-color: rgba(128,128,128,0.1); border-radius: 4px;")
            sig_layout = QVBoxLayout(sig_frame)
            sig_layout.setContentsMargins(6, 6, 6, 6)
            sig_layout.setSpacing(2)
            
            name_lbl = QLabel(disp_name.upper())
            name_lbl.setStyleSheet("font-size: 8px; color: #888888; border: none; background: transparent;")
            
            val_layout = QHBoxLayout()
            val_layout.setContentsMargins(0, 0, 0, 0)
            
            val_lbl = QLabel("0.000")
            val_lbl.setStyleSheet("font-size: 14px; font-weight: bold; font-family: monospace; border: none; background: transparent;")
            
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet("font-size: 9px; color: #888888; border: none; background: transparent;")
            
            val_layout.addWidget(val_lbl)
            val_layout.addWidget(unit_lbl)
            val_layout.addStretch()
            
            mvd_lbl = QLabel("0.000 mV")
            mvd_lbl.setStyleSheet("font-size: 11px; font-family: monospace; color: #3b82f6; border: none; background: transparent;")
            
            sig_layout.addWidget(name_lbl)
            sig_layout.addLayout(val_layout)
            sig_layout.addWidget(mvd_lbl)
            
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(sig_frame, row, col)
            
            self._value_labels[name] = val_lbl
            self._mvd_labels[name] = mvd_lbl
            
        main_layout.addLayout(self.grid_layout)

    def update_reading(self, param_name: str, reading: ParameterReading) -> None:
        lbl = self._value_labels.get(param_name)
        if not lbl:
            return
            
        lbl.setText(f"{reading.scaled_value:.3f}")
        
        mvd_lbl = self._mvd_labels.get(param_name)
        if mvd_lbl:
            mvd_lbl.setText(f"{reading.raw_value} raw") # Placeholder for raw/mvd logic
            
        theme = self._app_state.current_theme if self._app_state else "dark"
        
        if reading.result == RESULT_PASS:
            color = DARK_PASS if theme == "dark" else LIGHT_PASS
        elif reading.result == RESULT_FAIL:
            color = DARK_FAIL if theme == "dark" else LIGHT_FAIL
        else:
            color = DARK_TEXT_PRIMARY if theme == "dark" else LIGHT_TEXT_PRIMARY
            
        lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; font-family: monospace; color: {color}; border: none; background: transparent;")

    def update_module_result(self, result: str) -> None:
        icons = {
            RESULT_PASS:    "● PASS",
            RESULT_FAIL:    "● FAIL",
            RESULT_PENDING: "● PENDING",
            RESULT_BYPASS:  "● BYPASS",
        }
        self.result_lbl.setText(icons.get(result, "● PENDING"))
        
        obj_names = {
            RESULT_PASS:    "result_pass",
            RESULT_FAIL:    "result_fail",
            RESULT_PENDING: "result_pending",
        }
        self.result_lbl.setObjectName(obj_names.get(result, "result_pending"))
        self._restyle(self.result_lbl)
        
        prop = "pass" if result == RESULT_PASS else "fail" if result == RESULT_FAIL else ""
        self.setProperty("result", prop)
        self._restyle(self)

    def reset(self) -> None:
        for lbl in self._value_labels.values():
            lbl.setText("0.000")
            lbl.setStyleSheet("font-size: 14px; font-weight: bold; font-family: monospace; border: none; background: transparent;")
        for lbl in self._mvd_labels.values():
            lbl.setText("0 raw")
        self.update_module_result(RESULT_PENDING)

    def _restyle(self, w) -> None:
        w.style().unpolish(w)
        w.style().polish(w)
