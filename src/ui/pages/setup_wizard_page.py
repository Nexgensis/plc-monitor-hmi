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
        self.setAccessibleName("Setup wizard")

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
        title.setObjectName("setup_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Let's set up your PLC connection first.")
        subtitle.setObjectName("setup_subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "This application allows you to monitor and control industrial PLCs "
            "using Modbus TCP or RTU. Before we begin, we need to configure "
            "the hardware interface."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setObjectName("setup_desc")

        start_btn = QPushButton("Get Started →")
        start_btn.setFixedHeight(42)
        start_btn.setFixedWidth(200)
        start_btn.setObjectName("btn_primary")
        start_btn.setAccessibleName("Get started")
        start_btn.setToolTip("Begin PLC configuration setup")
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
        layout.setSpacing(10)
        layout.setContentsMargins(0, 4, 0, 0)

        header = QLabel("Step 1 of 3: PLC Connection")
        header.setObjectName("setup_header")
        layout.addWidget(header)

        # Brand & Protocol
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.brand_combo = QComboBox()
        self.brand_combo.addItems([b.capitalize() for b in PLC_BRANDS])
        self.brand_combo.setAccessibleName("PLC brand")
        self.brand_combo.setToolTip("Select your PLC brand")
        brand_lbl = QLabel("PLC BRAND")
        brand_lbl.setObjectName("setup_label")
        row1.addWidget(brand_lbl)
        row1.addWidget(self.brand_combo)

        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["TCP", "RTU"])
        self.proto_combo.currentTextChanged.connect(self._on_proto_changed)
        self.proto_combo.setAccessibleName("Communication protocol")
        self.proto_combo.setToolTip("Select TCP or RTU communication")
        proto_lbl = QLabel("PROTOCOL")
        proto_lbl.setObjectName("setup_label")
        row1.addWidget(proto_lbl)
        row1.addWidget(self.proto_combo)
        layout.addLayout(row1)

        # TCP Group
        self.tcp_frame = QFrame()
        tcp_layout = QVBoxLayout(self.tcp_frame)
        tcp_layout.setSpacing(6)
        tcp_layout.setContentsMargins(0, 0, 0, 0)
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setAccessibleName("PLC host address")
        self.host_input.setToolTip("IP address or hostname of the PLC")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        self.port_spin.setAccessibleName("PLC port number")
        self.port_spin.setToolTip("Modbus TCP port number, default 502")
        host_lbl = QLabel("HOST / IP")
        host_lbl.setObjectName("setup_label")
        tcp_layout.addWidget(host_lbl)
        tcp_layout.addWidget(self.host_input)

        port_lbl = QLabel("PORT")
        port_lbl.setObjectName("setup_label")
        tcp_layout.addWidget(port_lbl)
        tcp_layout.addWidget(self.port_spin)
        layout.addWidget(self.tcp_frame)

        # RTU Group
        self.rtu_frame = QFrame()
        rtu_layout = QVBoxLayout(self.rtu_frame)
        rtu_layout.setSpacing(6)
        rtu_layout.setContentsMargins(0, 0, 0, 0)
        
        com_row = QHBoxLayout()
        self.com_combo = QComboBox()
        self.com_combo.setEditable(True)
        com_row.addWidget(self.com_combo, 1)
        
        self.refresh_ports_btn = QPushButton("🔄")
        self.refresh_ports_btn.setFixedSize(30, 30)
        self.refresh_ports_btn.clicked.connect(self._refresh_com_ports)
        self.refresh_ports_btn.setAccessibleName("Refresh serial ports")
        self.refresh_ports_btn.setToolTip("Refresh available serial ports")
        com_row.addWidget(self.refresh_ports_btn)
        
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText("9600")
        
        self.parity_combo = QComboBox()
        for k, v in PARITY_OPTIONS.items():
            self.parity_combo.addItem(v, k)
        
        com_port_lbl = QLabel("COM PORT")
        com_port_lbl.setObjectName("setup_label")
        rtu_layout.addWidget(com_port_lbl)
        rtu_layout.addLayout(com_row)

        baud_lbl = QLabel("BAUD RATE")
        baud_lbl.setObjectName("setup_label")
        rtu_layout.addWidget(baud_lbl)
        rtu_layout.addWidget(self.baud_combo)

        parity_lbl = QLabel("PARITY")
        parity_lbl.setObjectName("setup_label")
        rtu_layout.addWidget(parity_lbl)
        rtu_layout.addWidget(self.parity_combo)

        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(["7", "8"])
        self.data_bits_combo.setCurrentText("8")
        data_bits_lbl = QLabel("DATA BITS")
        data_bits_lbl.setObjectName("setup_label")
        rtu_layout.addWidget(data_bits_lbl)
        rtu_layout.addWidget(self.data_bits_combo)

        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(["1", "2"])
        stop_bits_lbl = QLabel("STOP BITS")
        stop_bits_lbl.setObjectName("setup_label")
        rtu_layout.addWidget(stop_bits_lbl)
        rtu_layout.addWidget(self.stop_bits_combo)

        self.rtu_frame.hide()
        layout.addWidget(self.rtu_frame)

        # Slave ID
        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)
        self.slave_spin.setAccessibleName("Slave ID")
        self.slave_spin.setToolTip("Modbus slave device ID")
        slave_lbl = QLabel("SLAVE ID (UNIT ID)")
        slave_lbl.setObjectName("setup_label")
        layout.addWidget(slave_lbl)
        layout.addWidget(self.slave_spin)

        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(500, 30000)
        self.timeout_spin.setSingleStep(500)
        self.timeout_spin.setValue(3000)
        self.timeout_spin.setAccessibleName("Timeout in milliseconds")
        self.timeout_spin.setToolTip("Connection timeout in milliseconds")
        timeout_lbl = QLabel("TIMEOUT (ms)")
        timeout_lbl.setObjectName("setup_label")
        layout.addWidget(timeout_lbl)
        layout.addWidget(self.timeout_spin)

        # Test Result
        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_result_lbl.setObjectName("setup_test_result")
        layout.addWidget(self.test_result_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        self.test_btn.setAccessibleName("Test PLC connection")
        self.test_btn.setToolTip("Test the PLC connection with current settings")
        
        self.save_btn = QPushButton("Save & Continue →")
        self.save_btn.setEnabled(False)
        self.save_btn.setObjectName("btn_success")
        self.save_btn.clicked.connect(self._on_save_connection)
        self.save_btn.setAccessibleName("Save and continue")
        self.save_btn.setToolTip("Save configuration and proceed")

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

        header = QLabel("Step 3 of 3: Complete")
        header.setObjectName("setup_header")
        layout.addWidget(header)

        success_icon = QLabel("✓")
        success_icon.setObjectName("setup_success_icon")
        success_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Connection configured!")
        title.setObjectName("setup_done_title")
        
        msg = QLabel(
            "You can now log in and configure register mappings "
            "in the CONFIG screen. Use default admin credentials "
            "to get started."
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setObjectName("setup_done_msg")

        login_btn = QPushButton("Go to Login →")
        login_btn.setFixedHeight(42)
        login_btn.setFixedWidth(200)
        login_btn.setObjectName("btn_primary")
        login_btn.setAccessibleName("Go to login")
        login_btn.setToolTip("Proceed to the login screen")
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
        self._set_test_result("info")
        
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
            self._set_test_result("pass")
        else:
            self._set_test_result("warn")
            
        self.save_btn.setEnabled(True)

    def _on_test_failed(self, error: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_result_lbl.setText(f"✗ Failed: {error}")
        self._set_test_result("fail")
        self.save_btn.setEnabled(False)

    def _set_test_result(self, result: str) -> None:
        self.test_result_lbl.setProperty("result", result)
        self.test_result_lbl.style().unpolish(self.test_result_lbl)
        self.test_result_lbl.style().polish(self.test_result_lbl)

    def _on_save_connection(self) -> None:
        config = self._get_config_from_ui()
        
        # Validate required fields
        errors = []
        if config["protocol"] == "TCP":
            host = config.get("host", "").strip()
            if not host:
                errors.append("Host/IP address is required for TCP connections.")
            port = config.get("port", 0)
            if not (1 <= port <= 65535):
                errors.append(f"Port must be between 1 and 65535 (got {port}).")
        else:
            com_port = config.get("com_port", "")
            if not com_port:
                errors.append("COM port is required for serial connections.")
        
        slave_id = config.get("slave_id", 0)
        if not (1 <= slave_id <= 247):
            errors.append(f"Slave ID must be between 1 and 247 (got {slave_id}).")
        
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return
        
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
