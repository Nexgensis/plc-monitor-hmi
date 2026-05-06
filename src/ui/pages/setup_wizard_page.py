"""
setup_wizard_page.py — Universal PLC Monitor
Initial setup guide for first-time application run.
"""
from __future__ import annotations

import logging
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QComboBox, QLineEdit, QSpinBox, 
                             QStackedWidget, QFrame)
from PyQt6.QtCore import pyqtSignal, Qt
from src.plc.connection_tester import ConnectionTester
from src.utils.constants import PLC_BRANDS, BAUD_RATES, PARITY_OPTIONS

logger = logging.getLogger(__name__)


class SetupWizardPage(QWidget):
    setup_complete = pyqtSignal()

    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("setup_wizard_page")

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stack = QStackedWidget()
        self.stack.setFixedWidth(500)
        
        self._init_step1()
        self._init_step2()
        self._init_step3()

        layout.addWidget(self.stack)

    def _init_step1(self) -> None:
        """STEP 1 — Welcome"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Welcome to PLC Monitor")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #3b82f6;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Let's set up your PLC connection first.")
        subtitle.setStyleSheet("font-size: 18px; color: #e8f0fa;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "This application allows you to monitor and control industrial PLCs "
            "using Modbus TCP or RTU. Before we begin, we need to configure "
            "the hardware interface."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #5a7a9a; line-height: 1.5;")

        start_btn = QPushButton("Get Started →")
        start_btn.setFixedHeight(50)
        start_btn.setFixedWidth(200)
        start_btn.setObjectName("btn_primary")
        start_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(desc)
        layout.addSpacing(20)
        layout.addWidget(start_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.stack.addWidget(page)

    def _init_step2(self) -> None:
        """STEP 2 — PLC Connection"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("Step 1 of 2: PLC Connection")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #5a7a9a;")
        layout.addWidget(header)

        # Brand & Protocol
        row1 = QHBoxLayout()
        self.brand_combo = QComboBox()
        self.brand_combo.addItems([b.capitalize() for b in PLC_BRANDS])
        row1.addWidget(QLabel("PLC BRAND"))
        row1.addWidget(self.brand_combo)

        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["TCP", "RTU"])
        self.proto_combo.currentTextChanged.connect(self._on_proto_changed)
        row1.addWidget(QLabel("PROTOCOL"))
        row1.addWidget(self.proto_combo)
        layout.addLayout(row1)

        # TCP Group
        self.tcp_frame = QFrame()
        tcp_layout = QVBoxLayout(self.tcp_frame)
        self.host_input = QLineEdit("127.0.0.1")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        tcp_layout.addWidget(QLabel("HOST / IP"))
        tcp_layout.addWidget(self.host_input)
        tcp_layout.addWidget(QLabel("PORT"))
        tcp_layout.addWidget(self.port_spin)
        layout.addWidget(self.tcp_frame)

        # RTU Group
        self.rtu_frame = QFrame()
        rtu_layout = QVBoxLayout(self.rtu_frame)
        
        com_row = QHBoxLayout()
        self.com_combo = QComboBox()
        self.com_combo.setEditable(True)
        com_row.addWidget(self.com_combo, 1)
        
        self.refresh_ports_btn = QPushButton("🔄")
        self.refresh_ports_btn.setFixedSize(30, 30)
        self.refresh_ports_btn.clicked.connect(self._refresh_com_ports)
        com_row.addWidget(self.refresh_ports_btn)
        
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText("9600")
        
        self.parity_combo = QComboBox()
        for k, v in PARITY_OPTIONS.items():
            self.parity_combo.addItem(v, k)
        
        rtu_layout.addWidget(QLabel("COM PORT"))
        rtu_layout.addLayout(com_row)
        rtu_layout.addWidget(QLabel("BAUD RATE"))
        rtu_layout.addWidget(self.baud_combo)
        rtu_layout.addWidget(QLabel("PARITY"))
        rtu_layout.addWidget(self.parity_combo)

        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(["7", "8"])
        self.data_bits_combo.setCurrentText("8")
        rtu_layout.addWidget(QLabel("DATA BITS"))
        rtu_layout.addWidget(self.data_bits_combo)

        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(["1", "2"])
        rtu_layout.addWidget(QLabel("STOP BITS"))
        rtu_layout.addWidget(self.stop_bits_combo)

        self.rtu_frame.hide()
        layout.addWidget(self.rtu_frame)

        # Slave ID
        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)
        layout.addWidget(QLabel("SLAVE ID (UNIT ID)"))
        layout.addWidget(self.slave_spin)

        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(500, 30000)
        self.timeout_spin.setSingleStep(500)
        self.timeout_spin.setValue(3000)
        layout.addWidget(QLabel("TIMEOUT (ms)"))
        layout.addWidget(self.timeout_spin)

        # Test Result
        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_result_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.test_result_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        
        self.save_btn = QPushButton("Save & Continue →")
        self.save_btn.setEnabled(False)
        self.save_btn.setObjectName("btn_success")
        self.save_btn.clicked.connect(self._on_save_connection)

        btn_row.addWidget(back_btn)
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self.stack.addWidget(page)

    def _init_step3(self) -> None:
        """STEP 3 — Done"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        success_icon = QLabel("✓")
        success_icon.setStyleSheet("font-size: 64px; color: #22c55e;")
        success_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Connection configured!")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #e8f0fa;")
        
        msg = QLabel(
            "You can now log in and configure register mappings "
            "in the CONFIG screen. Use default admin credentials "
            "to get started."
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #5a7a9a;")

        login_btn = QPushButton("Go to Login →")
        login_btn.setFixedHeight(50)
        login_btn.setFixedWidth(200)
        login_btn.setObjectName("btn_primary")
        login_btn.clicked.connect(self.setup_complete.emit)

        layout.addWidget(success_icon)
        layout.addWidget(title)
        layout.addWidget(msg)
        layout.addSpacing(20)
        layout.addWidget(login_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.stack.addWidget(page)

    def _on_proto_changed(self, proto: str) -> None:
        self.tcp_frame.setVisible(proto == "TCP")
        self.rtu_frame.setVisible(proto == "RTU")
        if proto == "RTU":
            self._refresh_com_ports()

    def _refresh_com_ports(self) -> None:
        if not serial: return
        self.com_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.com_combo.addItem(f"{p.device} — {p.description}", p.device)

    def _on_test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_result_lbl.setText("Testing...")
        self.test_result_lbl.setStyleSheet("color: #3b82f6;")
        
        config = self._get_config_from_ui()
        self.tester = ConnectionTester(config)
        self.tester.test_progress.connect(self.test_result_lbl.setText)
        self.tester.test_passed.connect(self._on_test_passed)
        self.tester.test_failed.connect(self._on_test_failed)
        self.tester.start()

    def _on_test_passed(self, details: dict) -> None:
        self.test_btn.setEnabled(True)
        msg = details.get("message", "✓ Connection Successful!")
        self.test_result_lbl.setText(msg)
        
        if details.get("read_ok"):
            self.test_result_lbl.setStyleSheet("color: #22c55e;")
        else:
            # Connected but address 0 failed (common)
            self.test_result_lbl.setStyleSheet("color: #f59e0b;") # Amber
            
        self.save_btn.setEnabled(True)

    def _on_test_failed(self, error: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_result_lbl.setText(f"✗ Failed: {error}")
        self.test_result_lbl.setStyleSheet("color: #ef4444;")
        self.save_btn.setEnabled(False)

    def _on_save_connection(self) -> None:
        config = self._get_config_from_ui()
        if self.app_state.profile_repo:
            self.app_state.profile_repo.update_profile(**config)
            self.app_state.set_plc_profile(config)
            self.stack.setCurrentIndex(2)

    def _get_config_from_ui(self) -> dict:
        config = {
            "brand": self.brand_combo.currentText().lower(),
            "protocol": self.proto_combo.currentText(),
            "slave_id": self.slave_spin.value(),
            "timeout_ms": self.timeout_spin.value(),
        }
        if config["protocol"] == "TCP":
            config.update({
                "host": self.host_input.text(),
                "port": self.port_spin.value()
            })
        else:
            config.update({
                "com_port": self.com_combo.currentData() or self.com_combo.currentText(),
                "baud_rate": int(self.baud_combo.currentText()),
                "parity": self.parity_combo.currentData(),
                "data_bits": int(self.data_bits_combo.currentText()),
                "stop_bits": int(self.stop_bits_combo.currentText()),
            })
        return config
