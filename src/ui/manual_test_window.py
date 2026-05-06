"""
ui/manual_test_window.py
Main window for manual operation testing, isolating discrete coil triggers.
"""

import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QDoubleSpinBox, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState
from src.ui.components.nav_bar import NavBar
from src.ui.components.manual_grid import ManualGrid
from src.utils.constants import COLOR_NAVY, COLOR_WHITE

log = logging.getLogger(__name__)

class ManualTestWindow(QMainWindow):
    """
    Manual operation window providing granular control over PLC outputs.
    """
    
    def __init__(self, db, app_state: AppState, connection_manager, parent=None):
        super().__init__(parent)
        self._db = db
        self._state = app_state
        self._conn = connection_manager
        self._params = app_state.get_current_parameters()
        
        self._setup_ui()
        self._bind_signals()
        
    def _setup_ui(self) -> None:
        self.resize(1100, 650)
        
        # Center the window
        frame_gm = self.frameGeometry()
        screen = self.screen().availableGeometry().center()
        frame_gm.moveCenter(screen)
        self.move(frame_gm.topLeft())
        
        model_name = self._state.current_model.get("model", {}).get("name", "Unknown") if self._state.current_model else "No Model"
        self.setWindowTitle(f"Manual Operation — {model_name}")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # NavBar
        self.navbar = NavBar(self._state)
        self.navbar.home_requested.connect(self._on_close)
        main_layout.addWidget(self.navbar)
        
        # Content Area
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(16, 16, 16, 16)
        
        card = QFrame()
        card.setObjectName("white_card")
        card.setStyleSheet("QFrame#white_card { background-color: white; border-radius: 8px; border: 1px solid #d0d8e8; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        
        title_lbl = QLabel("Manual Operation")
        title_lbl.setStyleSheet(f"color: {COLOR_NAVY}; font-size: 18px; font-weight: bold;")
        card_layout.addWidget(title_lbl)
        
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background-color: #d0d8e8; max-height: 1px;")
        card_layout.addWidget(divider)
        card_layout.addSpacing(10)
        
        self.manual_grid = ManualGrid(self._params, self._state)
        card_layout.addWidget(self.manual_grid)
        
        content_layout.addWidget(card)
        main_layout.addWidget(content_wrapper, stretch=1)
        
        # Bottom Control Bar
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet(f"background-color: {COLOR_NAVY}; border-top: 1px solid #1a1a2e;")
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(20, 10, 20, 10)
        
        voltage_lbl = QLabel("Input Voltage:")
        voltage_lbl.setStyleSheet(f"color: {COLOR_WHITE}; font-weight: bold;")
        bottom_bar_layout.addWidget(voltage_lbl)
        
        self.input_voltage = QDoubleSpinBox()
        self.input_voltage.setRange(0.0, 30.0)
        self.input_voltage.setSingleStep(0.5)
        self.input_voltage.setSuffix(" V")
        self.input_voltage.setValue(14.0)
        self.input_voltage.setFixedWidth(120)
        self.input_voltage.setStyleSheet("""
            QDoubleSpinBox { 
                padding: 5px; 
                border-radius: 4px; 
                background: white; 
                color: #1e2d4a;
            }
        """)
        bottom_bar_layout.addWidget(self.input_voltage)
        
        self.btn_submit_voltage = QPushButton("Submit Voltage")
        self.btn_submit_voltage.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                font-weight: bold;
                padding: 6px 15px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        self.btn_submit_voltage.clicked.connect(self._on_set_voltage)
        bottom_bar_layout.addWidget(self.btn_submit_voltage)
        
        bottom_bar_layout.addStretch()
        
        self.btn_reset_all = QPushButton("Reset All")
        self.btn_reset_all.setStyleSheet("""
            QPushButton {
                background: #34495e;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #2c3e50; }
        """)
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        bottom_bar_layout.addWidget(self.btn_reset_all)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.btn_close.clicked.connect(self._on_close)
        bottom_bar_layout.addWidget(self.btn_close)
        
        main_layout.addWidget(bottom_bar)
        
        # Message bar for status
        self.message_bar_lbl = QLabel("")
        self.message_bar_lbl.setStyleSheet("color: white; padding: 2px 20px; font-size: 11px;")
        main_layout.addWidget(self.message_bar_lbl)

    def _bind_signals(self) -> None:
        conn = self._state.connection_manager
        if conn:
            conn.readings_updated.connect(self._on_readings)
            conn.connection_state_changed.connect(self._on_connection_changed)
            
            # Initial state
            self._on_connection_changed(self._state.is_plc_connected)

    def _on_readings(self, readings: dict) -> None:
        self.manual_grid.update_readings(readings)

    def _on_connection_changed(self, connected: bool) -> None:
        self.manual_grid.set_buttons_enabled(connected)
        self.navbar.update_plc_status(connected)
        if not connected:
            self.message_bar_lbl.setText("⚠ PLC disconnected — buttons disabled")
            self.message_bar_lbl.setStyleSheet("background: #c0392b; color: white; padding: 2px 20px;")
        else:
            self.message_bar_lbl.setText("✔ PLC connected")
            self.message_bar_lbl.setStyleSheet("background: #27ae60; color: white; padding: 2px 20px;")

    def _on_set_voltage(self) -> None:
        voltage = self.input_voltage.value()
        try:
            driver = self._state.connection_manager.get_driver()
            raw_voltage = int(voltage * 10)  # e.g. 14V → 140
            # D50 is default for voltage setpoint per spec
            driver.write_holding_register(50, raw_voltage)
            log.info(f"Input voltage set to {voltage}V (raw: {raw_voltage})")
        except Exception as e:
            log.error(f"Failed to set input voltage: {e}")

    def _on_reset_all(self) -> None:
        self.manual_grid.reset_all()
        # Write reset coil (safety)
        try:
            driver = self._state.connection_manager.get_driver()
            profile = self._state.plc_profile or {}
            # Safety: start_coil + 2
            reset_coil = profile.get("start_coil", 300) + 2
            driver.write_coil(reset_coil, True)
            log.info(f"Manual test reset — coil M{reset_coil} written")
        except Exception as e:
            log.error(f"Failed to write reset coil: {e}")

    def _on_close(self) -> None:
        # SAFETY: write reset coil before closing
        self._on_reset_all()
        
        # Lazy import to avoid circular dependency
        from src.ui.login_window import LoginWindow
        self._login = LoginWindow(self._state)
        self._login.show()
        self.close()

    def closeEvent(self, event) -> None:
        """Always reset on any close event (e.g. X button)."""
        try:
            driver = self._state.connection_manager.get_driver()
            profile = self._state.plc_profile or {}
            reset_coil = profile.get("start_coil", 300) + 2
            driver.write_coil(reset_coil, True)
        except Exception as e:
            log.error(f"Reset coil failed on closeEvent: {e}")
        event.accept()
