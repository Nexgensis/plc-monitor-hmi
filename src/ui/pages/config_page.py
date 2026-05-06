"""
config_page.py — Universal PLC Monitor
Admin-only configuration hub for system settings, register library, and model mapping.
"""
from __future__ import annotations

import logging
import json
import time
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTabWidget, QGroupBox, QComboBox, QLineEdit, 
                             QSpinBox, QDoubleSpinBox, QPushButton, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFrame, QGridLayout, 
                             QProgressBar, QScrollArea, QSplitter, QCheckBox, 
                             QFormLayout, QMessageBox, QFileDialog, QTextEdit, 
                             QListWidget)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

try:
    import serial.tools.list_ports
except ImportError:
    serial = None

from src.ui.app_state import AppState
from src.plc.connection_tester import ConnectionTester
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.ui.dialogs.register_picker import RegisterPicker
from src.utils.constants import (BAUD_RATES, PARITY_OPTIONS, REG_TYPES, 
                                 DATA_TYPES, ROLES, CTRL_TYPES, 
                                 PAGE_CONFIG)

logger = logging.getLogger(__name__)


class ConfigPage(QWidget):
    def __init__(self, app_state: AppState, on_plc_reconnect: callable) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_plc_reconnect = on_plc_reconnect
        self.setObjectName("config_page")

        self._init_ui()
        self._init_quality_timer()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header Bar
        header = QHBoxLayout()
        title = QLabel("CONFIGURATION")
        title.setObjectName("page_title_main")
        header.addWidget(title)
        header.addStretch()
        muted_lbl = QLabel("Admin access only")
        muted_lbl.setObjectName("admin_only_label")
        header.addWidget(muted_lbl)
        layout.addLayout(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.currentChanged.connect(self._refresh_tab_data)
        
        self._init_tab_connection()   # Tab 0
        self._init_tab_library()      # Tab 1
        self._init_tab_mapping()      # Tab 2
        self._init_tab_io_list()      # Tab 3
        self._init_tab_control()      # Tab 4
        self._init_tab_message()      # Tab 5
        self._init_tab_export()       # Tab 6

        layout.addWidget(self.tabs)

    def on_page_shown(self) -> None:
        """Called by MainWindow when this page becomes active."""
        idx = self.tabs.currentIndex()
        self._refresh_tab_data(idx)

    def _refresh_tab_data(self, index: int) -> None:
        if index == 0: self._refresh_connection_status()
        elif index == 1: self._refresh_library_table()
        elif index == 2: self._refresh_mapping_tab()
        elif index == 3: self._refresh_io_table()
        elif index == 4: self._refresh_control_table()
        elif index == 5: self._refresh_message_tab()

    # =========================================================================
    # TAB 0: PLC CONNECTION
    # =========================================================================
    def _init_tab_connection(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(30)

        # LEFT COLUMN
        left_col = QScrollArea()
        left_col.setWidgetResizable(True)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)

        # 1. Connection Type
        type_grp = QGroupBox("Connection Type")
        type_form = QFormLayout(type_grp)
        type_form.setSpacing(12)
        type_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.brand_combo = QComboBox()
        self.brand_combo.addItems(["Mitsubishi FX/iQ-F Series", "Delta DVP/AS Series", "Generic Modbus TCP/RTU"])
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["TCP", "RTU"])
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_toggle)
        type_form.addRow("Brand:", self.brand_combo)
        type_form.addRow("Protocol:", self.protocol_combo)
        left_layout.addWidget(type_grp)

        # 2. TCP Settings
        self.tcp_grp = QGroupBox("TCP/IP Settings")
        tcp_form = QFormLayout(self.tcp_grp)
        tcp_form.setSpacing(12)
        
        self.host_field = QLineEdit()
        self.host_field.setPlaceholderText("e.g. 192.168.1.30")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)
        tcp_form.addRow("Host / IP:", self.host_field)
        tcp_form.addRow("Port:", self.port_spin)
        tcp_form.addRow("Slave ID:", self.slave_spin)
        left_layout.addWidget(self.tcp_grp)

        # 3. RTU Settings
        self.rtu_grp = QGroupBox("RTU / Serial Settings")
        self.rtu_grp.hide()
        rtu_form = QFormLayout(self.rtu_grp)
        rtu_form.setSpacing(12)
        
        com_row = QHBoxLayout()
        com_row.setSpacing(5)
        self.com_combo = QComboBox()
        self.com_refresh_btn = QPushButton("🔄")
        self.com_refresh_btn.setFixedSize(30, 30)
        self.com_refresh_btn.clicked.connect(self._refresh_com_ports)
        com_row.addWidget(self.com_combo, 1)
        com_row.addWidget(self.com_refresh_btn)
        
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText("9600")
        
        self.parity_combo = QComboBox()
        for k, v in PARITY_OPTIONS.items():
            self.parity_combo.addItem(v, k)
        
        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(["7", "8"])
        self.data_bits_combo.setCurrentText("8")
        
        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(["1", "2"])
        
        self.slave_spin_rtu = QSpinBox()
        self.slave_spin_rtu.setRange(1, 247)
        
        rtu_form.addRow("COM Port:", com_row)
        rtu_form.addRow("Baud Rate:", self.baud_combo)
        rtu_form.addRow("Parity:", self.parity_combo)
        rtu_form.addRow("Data Bits:", self.data_bits_combo)
        rtu_form.addRow("Stop Bits:", self.stop_bits_combo)
        rtu_form.addRow("Slave ID:", self.slave_spin_rtu)
        left_layout.addWidget(self.rtu_grp)

        # 4. Polling Settings
        poll_grp = QGroupBox("Polling Settings")
        poll_form = QFormLayout(poll_grp)
        poll_form.setSpacing(12)
        
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(100, 5000)
        self.poll_spin.setSingleStep(100)
        self.poll_spin.setValue(500)
        self.poll_spin.setToolTip("How often to read PLC registers")
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(500, 30000)
        self.timeout_spin.setSingleStep(500)
        self.timeout_spin.setValue(3000)
        
        self.reconnect_spin = QSpinBox()
        self.reconnect_spin.setRange(1000, 30000)
        self.reconnect_spin.setValue(5000)
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(1, 10)
        self.retry_spin.setValue(3)
        
        poll_form.addRow("Poll Interval (ms):", self.poll_spin)
        poll_form.addRow("Timeout (ms):", self.timeout_spin)
        poll_form.addRow("Reconnect Delay (ms):", self.reconnect_spin)
        poll_form.addRow("Max Retries:", self.retry_spin)
        left_layout.addWidget(poll_grp)

        # Save Button
        self.save_conn_btn = QPushButton("💾 Save Settings")
        self.save_conn_btn.setObjectName("btn_primary")
        self.save_conn_btn.setFixedHeight(45)
        self.save_conn_btn.clicked.connect(self._on_save_connection)
        left_layout.addWidget(self.save_conn_btn)
        
        self.conn_success_lbl = QLabel("")
        self.conn_success_lbl.setObjectName("success_message")
        self.conn_success_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.conn_success_lbl)

        left_layout.addStretch()
        left_col.setWidget(left_widget)
        layout.addWidget(left_col, 1)

        # RIGHT COLUMN
        right_col = QVBoxLayout()
        right_col.setSpacing(20)

        # 1. Connection Test
        test_grp = QGroupBox("Connection Test")
        test_layout = QVBoxLayout(test_grp)
        self.test_btn = QPushButton("🔌 Test Connection")
        self.test_btn.setObjectName("btn_success")
        self.test_btn.setFixedHeight(50)
        self.test_btn.clicked.connect(self._on_test_connection)
        test_layout.addWidget(self.test_btn)

        self.test_progress = QProgressBar()
        self.test_progress.hide()
        test_layout.addWidget(self.test_progress)

        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setWordWrap(True)
        test_layout.addWidget(self.test_result_lbl)

        # Quality Frame
        self.quality_frame = QFrame()
        self.quality_frame.setObjectName("card")
        self.quality_frame.hide()
        q_layout = QVBoxLayout(self.quality_frame)
        q_title = QLabel("✓ Connected")
        q_title.setObjectName("connection_test_title")
        q_layout.addWidget(q_title)
        
        self.q_grid = QGridLayout()
        q_layout.addLayout(self.q_grid)
        test_layout.addWidget(self.quality_frame)
        right_col.addWidget(test_grp)

        # 2. Current Status
        status_grp = QGroupBox("Current Connection Status")
        status_layout = QVBoxLayout(status_grp)
        self.status_lbl = QLabel("Disconnected")
        self.status_lbl.setObjectName("connection_status_label")
        status_layout.addWidget(self.status_lbl)
        
        self.status_grid_layout = QGridLayout()
        status_layout.addLayout(self.status_grid_layout)
        
        self.reconnect_btn = QPushButton("🔄 Reconnect Now")
        self.reconnect_btn.setObjectName("btn_secondary")
        self.reconnect_btn.clicked.connect(self.on_plc_reconnect)
        status_layout.addWidget(self.reconnect_btn)
        right_col.addWidget(status_grp)

        # 3. Quality Metrics
        quality_grp = QGroupBox("Connection Quality (Live)")
        quality_layout = QVBoxLayout(quality_grp)
        self.quality_stats_lbl = QLabel("Total Requests: 0\nAvg Response: 0 ms")
        quality_layout.addWidget(self.quality_stats_lbl)
        
        self.success_rate_bar = QProgressBar()
        self.success_rate_bar.setRange(0, 100)
        self.success_rate_bar.setValue(0)
        self.success_rate_bar.setFormat("Success Rate: %v%")
        quality_layout.addWidget(self.success_rate_bar)
        right_col.addWidget(quality_grp)

        right_col.addStretch()
        layout.addLayout(right_col, 1)

        self.tabs.addTab(page, "🔌 PLC Connection")
        
        # Load initial values
        self._load_connection_settings()
        self._refresh_com_ports()

    def _on_protocol_toggle(self, proto: str) -> None:
        self.tcp_grp.setVisible(proto == "TCP")
        self.rtu_grp.setVisible(proto == "RTU")

    def _refresh_com_ports(self) -> None:
        if not serial: return
        self.com_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.com_combo.addItem(f"{p.device} — {p.description}", p.device)

    def _load_connection_settings(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        brand_map = {
            "mitsubishi": 0,
            "delta": 1,
            "generic": 2
        }
        self.brand_combo.setCurrentIndex(brand_map.get(profile.get("brand", "mitsubishi"), 0))
        self.protocol_combo.setCurrentText(profile.get("protocol", "TCP"))
        
        self.host_field.setText(profile.get("host", ""))
        self.port_spin.setValue(profile.get("port", 502))
        self.slave_spin.setValue(profile.get("slave_id", 1))
        
        self.com_combo.setCurrentText(profile.get("com_port", ""))
        self.baud_combo.setCurrentText(str(profile.get("baud_rate", 9600)))
        self.parity_combo.setCurrentIndex(self.parity_combo.findData(profile.get("parity", "E")))
        self.data_bits_combo.setCurrentText(str(profile.get("data_bits", 8)))
        self.stop_bits_combo.setCurrentText(str(profile.get("stop_bits", 1)))
        self.slave_spin_rtu.setValue(profile.get("slave_id", 1))
        
        self.poll_spin.setValue(profile.get("poll_interval_ms", 500))
        self.timeout_spin.setValue(profile.get("timeout_ms", 3000))
        self.reconnect_spin.setValue(profile.get("reconnect_delay_ms", 5000))
        self.retry_spin.setValue(profile.get("max_retries", 3))

    def _on_save_connection(self) -> None:
        brand_text = self.brand_combo.currentText()
        brand = "mitsubishi"
        if "Delta" in brand_text: brand = "delta"
        elif "Generic" in brand_text: brand = "generic"
        
        protocol = self.protocol_combo.currentText()
        
        data = {
            "brand": brand,
            "protocol": protocol,
            "poll_interval_ms": self.poll_spin.value(),
            "timeout_ms": self.timeout_spin.value(),
            "reconnect_delay_ms": self.reconnect_spin.value(),
            "max_retries": self.retry_spin.value(),
        }
        
        if protocol == "TCP":
            data.update({
                "host": self.host_field.text().strip(),
                "port": self.port_spin.value(),
                "slave_id": self.slave_spin.value(),
            })
        else:
            data.update({
                "com_port": self.com_combo.currentData(),
                "baud_rate": int(self.baud_combo.currentText()),
                "parity": self.parity_combo.currentData(),
                "data_bits": int(self.data_bits_combo.currentText()),
                "stop_bits": int(self.stop_bits_combo.currentText()),
                "slave_id": self.slave_spin_rtu.value(),
            })
            
        if self.app_state.profile_repo.update_profile(**data):
            self.conn_success_lbl.setText("✓ Settings saved and applied")
            QTimer.singleShot(3000, lambda: self.conn_success_lbl.setText(""))
            self.on_plc_reconnect()
            self._refresh_connection_status()

    def _on_test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_progress.show()
        self.test_progress.setRange(0, 0) # Marquee
        self.test_result_lbl.setText("Initializing test...")
        self.quality_frame.hide()

        # Build profile for test
        protocol = self.protocol_combo.currentText()
        test_profile = {
            "protocol": protocol,
            "timeout_ms": self.timeout_spin.value(),
        }
        if protocol == "TCP":
            test_profile.update({
                "host": self.host_field.text().strip(),
                "port": self.port_spin.value(),
                "slave_id": self.slave_spin.value(),
            })
        else:
            test_profile.update({
                "com_port": self.com_combo.currentData(),
                "baud_rate": int(self.baud_combo.currentText()),
                "parity": self.parity_combo.currentData(),
                "data_bits": int(self.data_bits_combo.currentText()),
                "stop_bits": int(self.stop_bits_combo.currentText()),
                "slave_id": self.slave_spin_rtu.value(),
            })

        self.tester = ConnectionTester(test_profile)
        self.tester.test_progress.connect(self.test_result_lbl.setText)
        self.tester.test_passed.connect(self._on_test_passed)
        self.tester.test_failed.connect(self._on_test_failed)
        self.tester.start()

    def _on_test_passed(self, details: dict) -> None:
        self.test_btn.setEnabled(True)
        self.test_progress.hide()
        msg = details.get("message", "Test completed successfully.")
        self.test_result_lbl.setText(msg)
        self.test_result_lbl.setStyleSheet("color: #22c55e;" if details.get("read_ok") else "color: #f59e0b;")
        
        self.quality_frame.show()
        # Clear grid
        for i in reversed(range(self.q_grid.count())): 
            self.q_grid.itemAt(i).widget().deleteLater()
            
        rows = [
            ("Response Time:", f"{details['response_ms']} ms"),
            ("Protocol:", details["protocol"]),
            ("Endpoint:", details["host"] or details["com_port"]),
            ("Read Test:", "✓" if details["read_ok"] else "✗"),
            ("Write Test:", "✓" if details["write_ok"] else "✗"),
        ]
        for i, (k, v) in enumerate(rows):
            self.q_grid.addWidget(QLabel(k), i, 0)
            val_lbl = QLabel(v)
            val_lbl.setStyleSheet("font-weight: bold;")
            self.q_grid.addWidget(val_lbl, i, 1)

    def _on_test_failed(self, error: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_progress.hide()
        self.test_result_lbl.setText(f"✗ Test Failed:\n{error}")
        self.test_result_lbl.setStyleSheet("color: #ef4444;")

    def _refresh_connection_status(self) -> None:
        connected = self.app_state.is_plc_connected
        if connected:
            self.status_lbl.setText("Connected")
            self.status_lbl.setStyleSheet("font-weight: bold; color: #22c55e;")
        else:
            self.status_lbl.setText("Disconnected")
            self.status_lbl.setStyleSheet("font-weight: bold; color: #ef4444;")
            
        profile = self.app_state.profile_repo.get_profile()
        # Clear and rebuild status grid
        for i in reversed(range(self.status_grid_layout.count())): 
            self.status_grid_layout.itemAt(i).widget().deleteLater()
            
        rows = [
            ("Brand", profile.get("brand", "mitsubishi")),
            ("Protocol", profile.get("protocol", "TCP")),
            ("Slave ID", str(profile.get("slave_id", 1))),
            ("Interval", f"{profile.get('poll_interval_ms')} ms"),
        ]
        if profile.get("protocol") == "TCP":
            rows.insert(2, ("Host", profile.get("host", "")))
            rows.insert(3, ("Port", str(profile.get("port", 502))))
        else:
            rows.insert(2, ("Port", profile.get("com_port", "")))
            rows.insert(3, ("Baud", str(profile.get("baud_rate", 9600))))
            
        for i, (k, v) in enumerate(rows):
            self.status_grid_layout.addWidget(QLabel(f"{k}:"), i, 0)
            self.status_grid_layout.addWidget(QLabel(str(v)), i, 1)

    def _init_quality_timer(self) -> None:
        self.quality_timer = QTimer(self)
        self.quality_timer.timeout.connect(self._update_live_quality)
        self.quality_timer.start(5000)

    def _update_live_quality(self) -> None:
        if not self.app_state.connection_manager: return
        stats = self.app_state.connection_manager.get_quality_stats()
        
        self.quality_stats_lbl.setText(
            f"Total Requests: {stats['total_requests']}\n"
            f"Avg Response: {stats['avg_response_ms']:.1f} ms"
        )
        rate = stats['success_rate_pct']
        self.success_rate_bar.setValue(int(rate))
        
        # Color bar
        if rate > 95: color = "#22c55e"
        elif rate > 80: color = "#eab308"
        else: color = "#ef4444"
        self.success_rate_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

    # =========================================================================
    # TAB 1: REGISTER LIBRARY
    # =========================================================================
    def _init_tab_library(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.lib_add_btn = QPushButton("+ Add Register")
        self.lib_add_btn.setObjectName("btn_success")
        self.lib_add_btn.clicked.connect(self._on_lib_add)
        
        self.lib_edit_btn = QPushButton("✎ Edit")
        self.lib_edit_btn.setObjectName("btn_primary")
        self.lib_edit_btn.setEnabled(False)
        self.lib_edit_btn.clicked.connect(self._on_lib_edit)
        
        self.lib_del_btn = QPushButton("✕ Delete")
        self.lib_del_btn.setObjectName("btn_danger")
        self.lib_del_btn.setEnabled(False)
        self.lib_del_btn.clicked.connect(self._on_lib_delete)
        
        toolbar.addWidget(self.lib_add_btn)
        toolbar.addWidget(self.lib_edit_btn)
        toolbar.addWidget(self.lib_del_btn)
        toolbar.addStretch()
        
        self.lib_search = QLineEdit()
        self.lib_search.setPlaceholderText("Search name or address...")
        self.lib_search.setFixedWidth(200)
        self.lib_search.textChanged.connect(self._refresh_library_table)
        toolbar.addWidget(self.lib_search)
        
        self.lib_count_lbl = QLabel("0 registers")
        toolbar.addWidget(self.lib_count_lbl)
        layout.addLayout(toolbar)

        # Table
        self.lib_table = QTableWidget(0, 9)
        self.lib_table.setHorizontalHeaderLabels([
            "#", "Name", "Address", "Type", "Data Type", 
            "Scale", "Unit", "Access", "Description"
        ])
        self.lib_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.lib_table.setColumnWidth(1, 200)
        self.lib_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lib_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.lib_table.itemSelectionChanged.connect(self._on_lib_selection_changed)
        self.lib_table.itemDoubleClicked.connect(self._on_lib_edit)
        layout.addWidget(self.lib_table)

        # Inline Edit Form
        self.lib_form_grp = QGroupBox("Register Details")
        self.lib_form_grp.hide()
        form_layout = QVBoxLayout(self.lib_form_grp)
        
        f_row1 = QHBoxLayout()
        self.lib_name_edit = QLineEdit(); self.lib_name_edit.setMaxLength(100)
        self.lib_desc_edit = QLineEdit()
        f_row1.addWidget(QLabel("Name*:")); f_row1.addWidget(self.lib_name_edit, 2)
        f_row1.addWidget(QLabel("Description:")); f_row1.addWidget(self.lib_desc_edit, 3)
        form_layout.addLayout(f_row1)

        f_row2 = QHBoxLayout()
        self.lib_addr_spin = QSpinBox(); self.lib_addr_spin.setRange(0, 65535)
        self.lib_type_combo = QComboBox(); self.lib_type_combo.addItems(REG_TYPES)
        self.lib_dtype_combo = QComboBox(); self.lib_dtype_combo.addItems(DATA_TYPES)
        
        f_row2.addWidget(QLabel("Address*:")); f_row2.addWidget(self.lib_addr_spin)
        f_row2.addWidget(QLabel("Type*:")); f_row2.addWidget(self.lib_type_combo)
        f_row2.addWidget(QLabel("Data Type*:")); f_row2.addWidget(self.lib_dtype_combo)
        form_layout.addLayout(f_row2)

        f_row3 = QHBoxLayout()
        self.lib_scale_spin = QDoubleSpinBox(); self.lib_scale_spin.setRange(0.00001, 100000); self.lib_scale_spin.setDecimals(5); self.lib_scale_spin.setValue(1.0)
        self.lib_decimal_spin = QSpinBox(); self.lib_decimal_spin.setRange(0, 6); self.lib_decimal_spin.setValue(2)
        self.lib_unit_edit = QLineEdit(); self.lib_unit_edit.setMaxLength(20)
        
        f_row3.addWidget(QLabel("Scale:")); f_row3.addWidget(self.lib_scale_spin)
        f_row3.addWidget(QLabel("Decimals:")); f_row3.addWidget(self.lib_decimal_spin)
        f_row3.addWidget(QLabel("Unit:")); f_row3.addWidget(self.lib_unit_edit)
        form_layout.addLayout(f_row3)

        f_row4 = QHBoxLayout()
        self.lib_access_combo = QComboBox(); self.lib_access_combo.addItems(["READ_ONLY", "READ_WRITE"])
        self.lib_swap_cb = QCheckBox("Word Swap")
        self.lib_access_warn = QLabel("⚠ READ_WRITE registers can be written to PLC")
        self.lib_access_warn.setStyleSheet("color: #eab308;")
        self.lib_access_warn.hide()
        self.lib_access_combo.currentTextChanged.connect(lambda t: self.lib_access_warn.setVisible(t == "READ_WRITE"))
        
        f_row4.addWidget(QLabel("Access:")); f_row4.addWidget(self.lib_access_combo)
        f_row4.addWidget(self.lib_swap_cb)
        f_row4.addWidget(self.lib_access_warn)
        f_row4.addStretch()
        form_layout.addLayout(f_row4)

        btn_row = QHBoxLayout()
        self.lib_save_btn = QPushButton("Save")
        self.lib_save_btn.setObjectName("btn_primary")
        self.lib_save_btn.clicked.connect(self._on_lib_save)
        self.lib_cancel_btn = QPushButton("Cancel")
        self.lib_cancel_btn.clicked.connect(self.lib_form_grp.hide)
        btn_row.addStretch()
        btn_row.addWidget(self.lib_cancel_btn)
        btn_row.addWidget(self.lib_save_btn)
        form_layout.addLayout(btn_row)

        self.lib_error_lbl = QLabel("")
        self.lib_error_lbl.setStyleSheet("color: #ef4444;")
        form_layout.addWidget(self.lib_error_lbl)

        layout.addWidget(self.lib_form_grp)
        self.tabs.addTab(page, "📚 Register Library")

    def _refresh_library_table(self) -> None:
        query = self.lib_search.text().strip()
        regs = self.app_state.library_repo.search_registers(query)
        self.lib_table.setRowCount(len(regs))
        self.lib_count_lbl.setText(f"{len(regs)} registers")
        
        for i, r in enumerate(regs):
            self.lib_table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self.lib_table.setItem(i, 1, QTableWidgetItem(r["name"]))
            self.lib_table.setItem(i, 2, QTableWidgetItem(str(r["register_address"])))
            self.lib_table.setItem(i, 3, QTableWidgetItem(r["register_type"]))
            self.lib_table.setItem(i, 4, QTableWidgetItem(r["data_type"]))
            self.lib_table.setItem(i, 5, QTableWidgetItem(str(r["scale_factor"])))
            self.lib_table.setItem(i, 6, QTableWidgetItem(r["unit"]))
            
            # Access Badge
            acc = r["access"]
            item = QTableWidgetItem(acc)
            if acc == "READ_WRITE": item.setForeground(QColor("#22c55e"))
            else: item.setForeground(QColor("#3b82f6"))
            self.lib_table.setItem(i, 7, item)
            
            self.lib_table.setItem(i, 8, QTableWidgetItem(r["description"]))
            self.lib_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

    def _on_lib_selection_changed(self) -> None:
        has_sel = len(self.lib_table.selectedItems()) > 0
        self.lib_edit_btn.setEnabled(has_sel)
        self.lib_del_btn.setEnabled(has_sel)

    def _on_lib_add(self) -> None:
        self._current_lib_id = None
        self.lib_name_edit.clear()
        self.lib_desc_edit.clear()
        self.lib_addr_spin.setValue(0)
        self.lib_scale_spin.setValue(1.0)
        self.lib_decimal_spin.setValue(2)
        self.lib_unit_edit.clear()
        self.lib_swap_cb.setChecked(False)
        self.lib_error_lbl.setText("")
        self.lib_form_grp.setTitle("Add Register")
        self.lib_form_grp.show()
        self.lib_name_edit.setFocus()

    def _on_lib_edit(self) -> None:
        rows = self.lib_table.selectedItems()
        if not rows: return
        reg_id = rows[0].data(Qt.ItemDataRole.UserRole)
        reg = self.app_state.library_repo.get_register(reg_id)
        if not reg: return

        self._current_lib_id = reg_id
        self.lib_name_edit.setText(reg["name"])
        self.lib_desc_edit.setText(reg["description"])
        self.lib_addr_spin.setValue(reg["register_address"])
        self.lib_type_combo.setCurrentText(reg["register_type"])
        self.lib_dtype_combo.setCurrentText(reg["data_type"])
        self.lib_scale_spin.setValue(reg["scale_factor"])
        self.lib_decimal_spin.setValue(reg["decimal_places"])
        self.lib_unit_edit.setText(reg["unit"])
        self.lib_access_combo.setCurrentText(reg["access"])
        self.lib_swap_cb.setChecked(bool(reg["word_swap"]))
        
        self.lib_error_lbl.setText("")
        self.lib_form_grp.setTitle(f"Edit Register: {reg['name']}")
        self.lib_form_grp.show()

    def _on_lib_save(self) -> None:
        data = {
            "name": self.lib_name_edit.text().strip(),
            "description": self.lib_desc_edit.text().strip(),
            "register_address": self.lib_addr_spin.value(),
            "register_type": self.lib_type_combo.currentText(),
            "data_type": self.lib_dtype_combo.currentText(),
            "scale_factor": self.lib_scale_spin.value(),
            "decimal_places": self.lib_decimal_spin.value(),
            "unit": self.lib_unit_edit.text().strip(),
            "access": self.lib_access_combo.currentText(),
            "word_swap": self.lib_swap_cb.isChecked(),
        }

        try:
            if self._current_lib_id:
                self.app_state.library_repo.update_register(self._current_lib_id, **data)
            else:
                self.app_state.library_repo.create_register(**data)
            
            self.lib_form_grp.hide()
            self._refresh_library_table()
        except Exception as e:
            self.lib_error_lbl.setText(str(e))

    def _on_lib_delete(self) -> None:
        rows = self.lib_table.selectedItems()
        if not rows: return
        reg_id = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.lib_table.item(self.lib_table.currentRow(), 1).text()

        try:
            usage = self.app_state.library_repo.check_register_in_use(reg_id)
            if usage["total"] > 0:
                QMessageBox.warning(self, "Cannot Delete", f"Register '{name}' is in use by {usage['total']} items.")
                return

            if ConfirmDialog.ask(self, "Delete Register", f"Permanently delete '{name}'?", danger=True):
                self.app_state.library_repo.delete_register(reg_id)
                self._refresh_library_table()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # =========================================================================
    # TAB 2: MODEL MAPPING
    # =========================================================================
    def _init_tab_mapping(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        # Top Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Model:"))
        self.map_model_combo = QComboBox()
        self.map_model_combo.setFixedWidth(200)
        self.map_model_combo.currentIndexChanged.connect(self._refresh_mapping_tab)
        top_bar.addWidget(self.map_model_combo)

        self.model_add_btn = QPushButton("+ Add Model")
        self.model_add_btn.setObjectName("btn_success")
        self.model_add_btn.clicked.connect(self._on_model_add)
        top_bar.addWidget(self.model_add_btn)

        self.model_rename_btn = QPushButton("✎ Rename")
        self.model_rename_btn.clicked.connect(self._on_model_rename)
        top_bar.addWidget(self.model_rename_btn)

        self.model_del_btn = QPushButton("✕ Delete Model")
        self.model_del_btn.setObjectName("btn_danger")
        self.model_del_btn.clicked.connect(self._on_model_delete)
        top_bar.addWidget(self.model_del_btn)

        self.model_copy_btn = QPushButton("⎘ Copy From...")
        self.model_copy_btn.clicked.connect(self._on_model_copy)
        top_bar.addWidget(self.model_copy_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Panel (Table)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        btn_row = QHBoxLayout()
        self.map_add_reg_btn = QPushButton("＋ Add Register")
        self.map_add_reg_btn.setObjectName("btn_success")
        self.map_add_reg_btn.clicked.connect(self._on_map_add_register)
        
        self.map_up_btn = QPushButton("↑ Up")
        self.map_down_btn = QPushButton("↓ Down")
        self.map_rem_btn = QPushButton("✕ Remove")
        self.map_rem_btn.setObjectName("btn_danger")
        self.map_rem_btn.clicked.connect(self._on_map_remove)
        
        btn_row.addWidget(self.map_add_reg_btn)
        btn_row.addWidget(self.map_up_btn)
        btn_row.addWidget(self.map_down_btn)
        btn_row.addWidget(self.map_rem_btn)
        btn_row.addStretch()
        self.map_db_count_lbl = QLabel("Dashboard: 0/12")
        btn_row.addWidget(self.map_db_count_lbl)
        left_layout.addLayout(btn_row)

        self.map_table = QTableWidget(0, 10)
        self.map_table.setHorizontalHeaderLabels([
            "☐", "Display Name", "Register", "Address", "Type", 
            "Role", "Group", "Dashboard", "Position", "Bypass"
        ])
        self.map_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.map_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.map_table.itemSelectionChanged.connect(self._on_map_selection_changed)
        left_layout.addWidget(self.map_table)
        splitter.addWidget(left_panel)

        # Right Panel (Edit Form)
        self.map_form_grp = QGroupBox("Mapping Details")
        self.map_form_grp.setFixedWidth(300)
        form_layout = QFormLayout(self.map_form_grp)
        
        self.map_lib_name_lbl = QLabel("-")
        self.map_disp_name_edit = QLineEdit()
        self.map_role_combo = QComboBox(); self.map_role_combo.addItems(ROLES)
        self.map_group_edit = QLineEdit()
        self.map_enabled_cb = QCheckBox("Enabled")
        self.map_bypass_cb = QCheckBox("Bypass in Pass/Fail")
        self.map_db_cb = QCheckBox("Show in Dashboard")
        self.map_pos_spin = QSpinBox(); self.map_pos_spin.setRange(0, 11)
        self.map_pass_spin = QSpinBox(); self.map_pass_spin.setRange(0, 65535)
        self.map_fail_spin = QSpinBox(); self.map_fail_spin.setRange(0, 65535)
        
        self.map_role_combo.currentTextChanged.connect(self._on_map_role_changed)
        
        form_layout.addRow("Register:", self.map_lib_name_lbl)
        form_layout.addRow("Display Name:", self.map_disp_name_edit)
        form_layout.addRow("Role:", self.map_role_combo)
        form_layout.addRow("Group Name:", self.map_group_edit)
        form_layout.addRow(self.map_enabled_cb)
        form_layout.addRow(self.map_bypass_cb)
        form_layout.addRow(self.map_db_cb)
        form_layout.addRow("Position:", self.map_pos_spin)
        self.map_pass_row = form_layout.addRow("Pass Value:", self.map_pass_spin)
        self.map_fail_row = form_layout.addRow("Fail Value:", self.map_fail_spin)
        
        self.map_apply_btn = QPushButton("Apply")
        self.map_apply_btn.setObjectName("btn_primary")
        self.map_apply_btn.clicked.connect(self._on_map_apply)
        form_layout.addRow(self.map_apply_btn)
        
        splitter.addWidget(self.map_form_grp)
        layout.addWidget(splitter)

        # Validation Bar
        self.map_warn_lbl = QLabel("✓ Configuration valid")
        self.map_warn_lbl.setStyleSheet("color: #22c55e; padding: 5px; background: rgba(34, 197, 94, 0.1);")
        layout.addWidget(self.map_warn_lbl)

        self.tabs.addTab(page, "🗂 Model Mapping")

    def _refresh_mapping_tab(self) -> None:
        # 1. Update Model Combo
        models = self.app_state.model_repo.get_all_models()
        self.map_model_combo.blockSignals(True)
        curr_id = self.map_model_combo.currentData()
        self.map_model_combo.clear()
        for m in models:
            self.map_model_combo.addItem(m["name"], m["id"])
        
        if curr_id:
            idx = self.map_model_combo.findData(curr_id)
            if idx >= 0: self.map_model_combo.setCurrentIndex(idx)
        self.map_model_combo.blockSignals(False)

        # 2. Update Table
        model_id = self.map_model_combo.currentData()
        if not model_id: return
        
        mappings = self.app_state.map_repo.get_model_mappings(model_id)
        self.map_table.setRowCount(len(mappings))
        db_count = 0
        
        for i, m in enumerate(mappings):
            self.map_table.setItem(i, 0, QTableWidgetItem("☑" if m["enabled"] else "☐"))
            self.map_table.setItem(i, 1, QTableWidgetItem(m["display_name"]))
            self.map_table.setItem(i, 2, QTableWidgetItem(m["library_name"]))
            self.map_table.setItem(i, 3, QTableWidgetItem(str(m["register_address"])))
            self.map_table.setItem(i, 4, QTableWidgetItem(m["register_type"]))
            self.map_table.setItem(i, 5, QTableWidgetItem(m["role"]))
            self.map_table.setItem(i, 6, QTableWidgetItem(m["group_name"] or ""))
            self.map_table.setItem(i, 7, QTableWidgetItem("Yes" if m["show_in_dashboard"] else "No"))
            self.map_table.setItem(i, 8, QTableWidgetItem(str(m["card_position"])))
            self.map_table.setItem(i, 9, QTableWidgetItem("Yes" if m["bypass"] else "No"))
            
            self.map_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, m["id"])
            if m["show_in_dashboard"] and m["enabled"]: db_count += 1

        self.map_db_count_lbl.setText(f"Dashboard: {db_count}/12")
        
        # 3. Validate
        warnings = self.app_state.map_repo.validate_model_mappings(model_id)
        if warnings:
            self.map_warn_lbl.setText("⚠ " + "; ".join(warnings))
            self.map_warn_lbl.setStyleSheet("color: #eab308; padding: 5px; background: rgba(234, 179, 8, 0.1);")
        else:
            self.map_warn_lbl.setText("✓ Configuration valid")
            self.map_warn_lbl.setStyleSheet("color: #22c55e; padding: 5px; background: rgba(34, 197, 94, 0.1);")

    def _on_map_selection_changed(self) -> None:
        rows = self.map_table.selectedItems()
        if not rows:
            self.map_form_grp.setEnabled(False)
            return
        
        self.map_form_grp.setEnabled(True)
        mapping_id = rows[0].data(Qt.ItemDataRole.UserRole)
        # Find mapping in current list
        model_id = self.map_model_combo.currentData()
        mappings = self.app_state.map_repo.get_model_mappings(model_id)
        mapping = next((m for m in mappings if m["id"] == mapping_id), None)
        if not mapping: return
        
        self._current_map_id = mapping_id
        self.map_lib_name_lbl.setText(mapping["library_name"])
        self.map_disp_name_edit.setText(mapping["display_name"])
        self.map_role_combo.setCurrentText(mapping["role"])
        self.map_group_edit.setText(mapping["group_name"] or "")
        self.map_enabled_cb.setChecked(bool(mapping["enabled"]))
        self.map_bypass_cb.setChecked(bool(mapping["bypass"]))
        self.map_db_cb.setChecked(bool(mapping["show_in_dashboard"]))
        self.map_pos_spin.setValue(mapping["card_position"])
        self.map_pass_spin.setValue(mapping["pass_value"])
        self.map_fail_spin.setValue(mapping["fail_value"])

    def _on_map_role_changed(self, role: str) -> None:
        is_result = (role == "RESULT")
        self.map_pass_spin.setVisible(is_result)
        self.map_fail_spin.setVisible(is_result)

    def _on_map_apply(self) -> None:
        if not hasattr(self, "_current_map_id"): return
        data = {
            "display_name": self.map_disp_name_edit.text().strip(),
            "role": self.map_role_combo.currentText(),
            "group_name": self.map_group_edit.text().strip(),
            "enabled": self.map_enabled_cb.isChecked(),
            "bypass": self.map_bypass_cb.isChecked(),
            "show_in_dashboard": self.map_db_cb.isChecked(),
            "card_position": self.map_pos_spin.value(),
            "pass_value": self.map_pass_spin.value(),
            "fail_value": self.map_fail_spin.value(),
        }
        self.app_state.map_repo.update_mapping(self._current_map_id, **data)
        self._refresh_mapping_tab()

    def _on_map_add_register(self) -> None:
        model_id = self.map_model_combo.currentData()
        if not model_id: return
        
        all_regs = self.app_state.library_repo.get_all_registers()
        curr_mappings = self.app_state.map_repo.get_model_mappings(model_id)
        mapped_ids = {m["register_id"] for m in curr_mappings}
        
        reg = RegisterPicker.pick(self, all_regs, mapped_ids)
        if reg:
            self.app_state.map_repo.add_mapping(model_id, reg["id"])
            self._refresh_mapping_tab()

    def _on_map_remove(self) -> None:
        rows = self.map_table.selectedItems()
        if not rows: return
        mapping_id = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.map_table.item(self.map_table.currentRow(), 1).text()
        
        if ConfirmDialog.ask(self, "Remove Mapping", f"Remove '{name}' from this model?"):
            self.app_state.map_repo.remove_mapping(mapping_id)
            self._refresh_mapping_tab()

    def _on_model_add(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Model", "New Model Name:")
        if ok and name.strip():
            try:
                self.app_state.model_repo.create_model(name.strip())
                self._refresh_mapping_tab()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_model_rename(self) -> None:
        model_id = self.map_model_combo.currentData()
        if not model_id: return
        old_name = self.map_model_combo.currentText()
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Rename Model", "New Name:", text=old_name)
        if ok and new_name.strip() and new_name != old_name:
            self.app_state.model_repo.update_model(model_id, name=new_name.strip())
            self._refresh_mapping_tab()

    def _on_model_delete(self) -> None:
        model_id = self.map_model_combo.currentData()
        if not model_id: return
        name = self.map_model_combo.currentText()
        if ConfirmDialog.ask(self, "Delete Model", f"Permanently delete model '{name}' and all its mappings?", danger=True):
            self.app_state.model_repo.delete_model(model_id)
            self._refresh_mapping_tab()

    def _on_model_copy(self) -> None:
        target_id = self.map_model_combo.currentData()
        if not target_id: return
        
        models = self.app_state.model_repo.get_all_models()
        from PyQt6.QtWidgets import QInputDialog
        names = [m["name"] for m in models if m["id"] != target_id]
        if not names: return
        
        src_name, ok = QInputDialog.getItem(self, "Copy Mappings", "Source Model:", names, 0, False)
        if ok:
            src_id = next(m["id"] for m in models if m["name"] == src_name)
            count = self.app_state.map_repo.copy_mappings(src_id, target_id)
            QMessageBox.information(self, "Copy Complete", f"Copied {count} register mappings.")
            self._refresh_mapping_tab()

    # =========================================================================
    # TAB 3: I/O LIST CONFIG
    # =========================================================================
    def _init_tab_io_list(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        toolbar = QHBoxLayout()
        self.io_add_btn = QPushButton("+ Add Entry")
        self.io_add_btn.setObjectName("btn_success")
        self.io_add_btn.clicked.connect(self._on_io_add)
        
        self.io_edit_btn = QPushButton("✎ Edit")
        self.io_edit_btn.setEnabled(False)
        self.io_edit_btn.clicked.connect(self._on_io_edit)
        
        self.io_rem_btn = QPushButton("✕ Remove")
        self.io_rem_btn.setObjectName("btn_danger")
        self.io_rem_btn.setEnabled(False)
        self.io_rem_btn.clicked.connect(self._on_io_delete)
        
        toolbar.addWidget(self.io_add_btn)
        toolbar.addWidget(self.io_edit_btn)
        toolbar.addWidget(self.io_rem_btn)
        toolbar.addStretch()
        
        self.io_filter = QLineEdit()
        self.io_filter.setPlaceholderText("Filter by group...")
        self.io_filter.textChanged.connect(self._refresh_io_table)
        toolbar.addWidget(self.io_filter)
        layout.addLayout(toolbar)

        self.io_table = QTableWidget(0, 8)
        self.io_table.setHorizontalHeaderLabels([
            "#", "Display Name", "Register", "Address", "Type", 
            "Group", "ON/OFF Labels", "Show Value"
        ])
        self.io_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.io_table.itemSelectionChanged.connect(self._on_io_selection_changed)
        self.io_table.itemDoubleClicked.connect(self._on_io_edit)
        layout.addWidget(self.io_table)

        # Edit Form
        self.io_form_grp = QGroupBox("I/O Row Details")
        self.io_form_grp.hide()
        form_layout = QFormLayout(self.io_form_grp)
        
        self.io_name_edit = QLineEdit()
        self.io_reg_combo = QComboBox()
        self.io_group_edit = QLineEdit()
        self.io_order_spin = QSpinBox()
        self.io_val_cb = QCheckBox("Show Numeric Value")
        self.io_on_edit = QLineEdit("ON")
        self.io_off_edit = QLineEdit("OFF")
        
        form_layout.addRow("Display Name*:", self.io_name_edit)
        form_layout.addRow("Register*:", self.io_reg_combo)
        form_layout.addRow("Group Name:", self.io_group_edit)
        form_layout.addRow("Row Order:", self.io_order_spin)
        form_layout.addRow(self.io_val_cb)
        form_layout.addRow("ON Label:", self.io_on_edit)
        form_layout.addRow("OFF Label:", self.io_off_edit)
        
        btn_row = QHBoxLayout()
        self.io_save_btn = QPushButton("Save")
        self.io_save_btn.setObjectName("btn_primary")
        self.io_save_btn.clicked.connect(self._on_io_save)
        btn_row.addStretch()
        btn_row.addWidget(QPushButton("Cancel", clicked=self.io_form_grp.hide))
        btn_row.addWidget(self.io_save_btn)
        form_layout.addRow(btn_row)
        
        layout.addWidget(self.io_form_grp)
        
        banner = QLabel("Note: Changes take effect immediately. I/O List page auto-refreshes when visible.")
        banner.setStyleSheet("font-size: 11px; color: #5a7a9a; font-style: italic;")
        layout.addWidget(banner)

        self.tabs.addTab(page, "📋 I/O List")

    def _refresh_io_table(self) -> None:
        rows = self.app_state.io_repo.get_io_config(active_only=False)
        filter_text = self.io_filter.text().lower()
        
        self.io_table.setRowCount(0)
        for r in rows:
            if filter_text and filter_text not in (r["group_name"] or "").lower():
                continue
            
            row_idx = self.io_table.rowCount()
            self.io_table.insertRow(row_idx)
            self.io_table.setItem(row_idx, 0, QTableWidgetItem(str(r["id"])))
            self.io_table.setItem(row_idx, 1, QTableWidgetItem(r["display_name"]))
            self.io_table.setItem(row_idx, 2, QTableWidgetItem(r["library_name"]))
            self.io_table.setItem(row_idx, 3, QTableWidgetItem(str(r["register_address"])))
            self.io_table.setItem(row_idx, 4, QTableWidgetItem(r["register_type"]))
            self.io_table.setItem(row_idx, 5, QTableWidgetItem(r["group_name"] or ""))
            self.io_table.setItem(row_idx, 6, QTableWidgetItem(f"{r['on_label']} / {r['off_label']}"))
            self.io_table.setItem(row_idx, 7, QTableWidgetItem("Yes" if r["show_value"] else "No"))
            self.io_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

    def _on_io_selection_changed(self) -> None:
        has_sel = len(self.io_table.selectedItems()) > 0
        self.io_edit_btn.setEnabled(has_sel)
        self.io_rem_btn.setEnabled(has_sel)

    def _on_io_add(self) -> None:
        self._current_io_id = None
        self._populate_io_reg_combo()
        self.io_name_edit.clear()
        self.io_group_edit.clear()
        self.io_order_spin.setValue(0)
        self.io_val_cb.setChecked(True)
        self.io_on_edit.setText("ON")
        self.io_off_edit.setText("OFF")
        self.io_form_grp.setTitle("Add I/O Entry")
        self.io_form_grp.show()

    def _on_io_edit(self) -> None:
        rows = self.io_table.selectedItems()
        if not rows: return
        io_id = rows[0].data(Qt.ItemDataRole.UserRole)
        config = self.app_state.io_repo.get_io_config(active_only=False)
        r = next((x for x in config if x["id"] == io_id), None)
        if not r: return

        self._current_io_id = io_id
        self._populate_io_reg_combo()
        self.io_name_edit.setText(r["display_name"])
        self.io_reg_combo.setCurrentIndex(self.io_reg_combo.findData(r["register_id"]))
        self.io_group_edit.setText(r["group_name"] or "")
        self.io_order_spin.setValue(r["row_order"])
        self.io_val_cb.setChecked(bool(r["show_value"]))
        self.io_on_edit.setText(r["on_label"])
        self.io_off_edit.setText(r["off_label"])
        
        self.io_form_grp.setTitle(f"Edit I/O Entry: {r['display_name']}")
        self.io_form_grp.show()

    def _populate_io_reg_combo(self) -> None:
        self.io_reg_combo.clear()
        regs = self.app_state.library_repo.get_all_registers()
        for r in regs:
            self.io_reg_combo.addItem(f"{r['name']} (D{r['register_address']}, {r['register_type']})", r["id"])

    def _on_io_save(self) -> None:
        data = {
            "display_name": self.io_name_edit.text().strip(),
            "register_id": self.io_reg_combo.currentData(),
            "group_name": self.io_group_edit.text().strip(),
            "row_order": self.io_order_spin.value(),
            "show_value": self.io_val_cb.isChecked(),
            "on_label": self.io_on_edit.text().strip(),
            "off_label": self.io_off_edit.text().strip(),
        }
        if not data["display_name"]: return
        
        if self._current_io_id:
            self.app_state.io_repo.update_io_row(self._current_io_id, **data)
        else:
            self.app_state.io_repo.create_io_row(**data)
            
        self.io_form_grp.hide()
        self._refresh_io_table()

    def _on_io_delete(self) -> None:
        rows = self.io_table.selectedItems()
        if not rows: return
        io_id = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.io_table.item(self.io_table.currentRow(), 1).text()
        
        if ConfirmDialog.ask(self, "Remove I/O Entry", f"Remove '{name}' from I/O status list?"):
            self.app_state.io_repo.delete_io_row(io_id)
            self._refresh_io_table()

    # =========================================================================
    # TAB 4: CONTROL REGISTERS
    # =========================================================================
    def _init_tab_control(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        banner = QFrame()
        banner.setObjectName("card")
        banner.setStyleSheet("background: rgba(234, 179, 8, 0.1); border: 1px solid #eab308;")
        bl = QVBoxLayout(banner)
        msg = QLabel("⚠ These are the ONLY registers the app will write. Only READ_WRITE registers allowed. All writes are logged.")
        msg.setWordWrap(True)
        bl.addWidget(msg)
        layout.addWidget(banner)

        toolbar = QHBoxLayout()
        self.ctrl_add_btn = QPushButton("+ Add Entry")
        self.ctrl_add_btn.setObjectName("btn_success")
        self.ctrl_add_btn.clicked.connect(self._on_ctrl_add)
        
        self.ctrl_edit_btn = QPushButton("✎ Edit")
        self.ctrl_edit_btn.setEnabled(False)
        self.ctrl_edit_btn.clicked.connect(self._on_ctrl_edit)
        
        self.ctrl_del_btn = QPushButton("✕ Remove")
        self.ctrl_del_btn.setObjectName("btn_danger")
        self.ctrl_del_btn.setEnabled(False)
        self.ctrl_del_btn.clicked.connect(self._on_ctrl_delete)
        
        toolbar.addWidget(self.ctrl_add_btn)
        toolbar.addWidget(self.ctrl_edit_btn)
        toolbar.addWidget(self.ctrl_del_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.ctrl_table = QTableWidget(0, 7)
        self.ctrl_table.setHorizontalHeaderLabels([
            "Name", "Register", "Address", "Type", "Control Type", 
            "Write Value", "Pulse Reset"
        ])
        self.ctrl_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ctrl_table.itemSelectionChanged.connect(self._on_ctrl_selection_changed)
        layout.addWidget(self.ctrl_table)

        # Form
        self.ctrl_form_grp = QGroupBox("Control Button Details")
        self.ctrl_form_grp.hide()
        form_layout = QFormLayout(self.ctrl_form_grp)
        
        self.ctrl_name_edit = QLineEdit()
        self.ctrl_reg_combo = QComboBox()
        self.ctrl_type_combo = QComboBox(); self.ctrl_type_combo.addItems(CTRL_TYPES)
        self.ctrl_val_spin = QSpinBox(); self.ctrl_val_spin.setRange(0, 65535)
        self.ctrl_pulse_spin = QSpinBox(); self.ctrl_pulse_spin.setRange(0, 10000); self.ctrl_pulse_spin.setSuffix(" ms")
        self.ctrl_conf_cb = QCheckBox("Require Confirmation Dialog")
        
        form_layout.addRow("Button Name*:", self.ctrl_name_edit)
        form_layout.addRow("Register*:", self.ctrl_reg_combo)
        form_layout.addRow("Control Type*:", self.ctrl_type_combo)
        form_layout.addRow("Write Value:", self.ctrl_val_spin)
        form_layout.addRow("Pulse Reset:", self.ctrl_pulse_spin)
        form_layout.addRow(self.ctrl_conf_cb)
        
        btn_row = QHBoxLayout()
        self.ctrl_save_btn = QPushButton("Save")
        self.ctrl_save_btn.setObjectName("btn_primary")
        self.ctrl_save_btn.clicked.connect(self._on_ctrl_save)
        btn_row.addStretch()
        btn_row.addWidget(QPushButton("Cancel", clicked=self.ctrl_form_grp.hide))
        btn_row.addWidget(self.ctrl_save_btn)
        form_layout.addRow(btn_row)
        layout.addWidget(self.ctrl_form_grp)

        # Write Log
        layout.addWidget(QLabel("Recent Write Log (Audit Trail):"))
        self.ctrl_log_list = QListWidget()
        self.ctrl_log_list.setFixedHeight(120)
        layout.addWidget(self.ctrl_log_list)

        self.tabs.addTab(page, "🎮 Control Registers")

    def _refresh_control_table(self) -> None:
        rows = self.app_state.control_repo.get_all_controls()
        self.ctrl_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.ctrl_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.ctrl_table.setItem(i, 1, QTableWidgetItem(r["register_name"]))
            self.ctrl_table.setItem(i, 2, QTableWidgetItem(str(r["register_address"])))
            self.ctrl_table.setItem(i, 3, QTableWidgetItem(r["register_type"]))
            self.ctrl_table.setItem(i, 4, QTableWidgetItem(r["control_type"]))
            self.ctrl_table.setItem(i, 5, QTableWidgetItem(str(r["write_value"])))
            self.ctrl_table.setItem(i, 6, QTableWidgetItem(f"{r['reset_after_ms']}ms" if r["reset_after_ms"] > 0 else "None"))
            self.ctrl_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r["id"])
            
        # Refresh Log
        self.ctrl_log_list.clear()
        logs = self.app_state.db.fetchall("SELECT * FROM plc_write_log ORDER BY timestamp DESC LIMIT 10")
        for l in logs:
            status = "✓" if l["write_success"] else "✗"
            self.ctrl_log_list.addItem(f"[{l['timestamp']}] {status} {l['write_reason']} -> Addr:{l['register_address']} Val:{l['value_written']}")

    def _on_ctrl_selection_changed(self) -> None:
        has_sel = len(self.ctrl_table.selectedItems()) > 0
        self.ctrl_edit_btn.setEnabled(has_sel)
        self.ctrl_del_btn.setEnabled(has_sel)

    def _on_ctrl_add(self) -> None:
        self._current_ctrl_id = None
        self._populate_ctrl_reg_combo()
        self.ctrl_name_edit.clear()
        self.ctrl_val_spin.setValue(1)
        self.ctrl_pulse_spin.setValue(0)
        self.ctrl_conf_cb.setChecked(False)
        self.ctrl_form_grp.setTitle("Add Control Button")
        self.ctrl_form_grp.show()

    def _on_ctrl_edit(self) -> None:
        rows = self.ctrl_table.selectedItems()
        if not rows: return
        cid = rows[0].data(Qt.ItemDataRole.UserRole)
        config = self.app_state.control_repo.get_all_controls()
        r = next((x for x in config if x["id"] == cid), None)
        if not r: return

        self._current_ctrl_id = cid
        self._populate_ctrl_reg_combo()
        self.ctrl_name_edit.setText(r["name"])
        self.ctrl_reg_combo.setCurrentIndex(self.ctrl_reg_combo.findData(r["register_id"]))
        self.ctrl_type_combo.setCurrentText(r["control_type"])
        self.ctrl_val_spin.setValue(r["write_value"])
        self.ctrl_pulse_spin.setValue(r["reset_after_ms"])
        self.ctrl_conf_cb.setChecked(bool(r["confirm_required"]))
        
        self.ctrl_form_grp.setTitle(f"Edit Control: {r['name']}")
        self.ctrl_form_grp.show()

    def _populate_ctrl_reg_combo(self) -> None:
        self.ctrl_reg_combo.clear()
        regs = self.app_state.library_repo.get_writable_registers()
        for r in regs:
            self.ctrl_reg_combo.addItem(f"{r['name']} (D{r['register_address']}, {r['access']})", r["id"])

    def _on_ctrl_save(self) -> None:
        data = {
            "name": self.ctrl_name_edit.text().strip(),
            "register_id": self.ctrl_reg_combo.currentData(),
            "control_type": self.ctrl_type_combo.currentText(),
            "write_value": self.ctrl_val_spin.value(),
            "reset_after_ms": self.ctrl_pulse_spin.value(),
            "confirm_required": self.ctrl_conf_cb.isChecked(),
        }
        if not data["name"] or not data["register_id"]: return
        
        if self._current_ctrl_id:
            self.app_state.control_repo.update_control(self._current_ctrl_id, **data)
        else:
            self.app_state.control_repo.create_control(**data)
            
        self.ctrl_form_grp.hide()
        self._refresh_control_table()

    def _on_ctrl_delete(self) -> None:
        rows = self.ctrl_table.selectedItems()
        if not rows: return
        cid = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.ctrl_table.item(self.ctrl_table.currentRow(), 0).text()
        
        if ConfirmDialog.ask(self, "Remove Control", f"Remove button '{name}'?"):
            self.app_state.control_repo.delete_control(cid)
            self._refresh_control_table()

    # =========================================================================
    # TAB 5: MESSAGE REGISTER
    # =========================================================================
    def _init_tab_message(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. Source Register
        src_grp = QGroupBox("Message Source Register")
        src_layout = QVBoxLayout(src_grp)
        info = QLabel("Select a register whose value maps to status messages. Shown in dashboard status bar.")
        info.setWordWrap(True)
        src_layout.addWidget(info)
        
        row = QHBoxLayout()
        self.msg_reg_combo = QComboBox()
        self._populate_msg_reg_combo()
        row.addWidget(self.msg_reg_combo, 1)
        self.msg_set_btn = QPushButton("Set as Message Register")
        self.msg_set_btn.setObjectName("btn_primary")
        self.msg_set_btn.clicked.connect(self._on_msg_set_source)
        row.addWidget(self.msg_set_btn)
        src_layout.addLayout(row)
        
        self.msg_curr_lbl = QLabel("Current: None")
        self.msg_curr_lbl.setStyleSheet("font-weight: bold; color: #3b82f6;")
        src_layout.addWidget(self.msg_curr_lbl)
        layout.addWidget(src_grp)

        # 2. Mapping Table
        map_grp = QGroupBox("Value → Message Mapping")
        map_layout = QVBoxLayout(map_grp)
        
        toolbar = QHBoxLayout()
        self.msg_add_btn = QPushButton("+ Add Message")
        self.msg_add_btn.setObjectName("btn_success")
        self.msg_add_btn.clicked.connect(self._on_msg_add)
        
        self.msg_clear_btn = QPushButton("🔄 Clear All")
        self.msg_clear_btn.clicked.connect(self._on_msg_clear_all)
        
        toolbar.addWidget(self.msg_add_btn)
        toolbar.addWidget(self.msg_clear_btn)
        toolbar.addStretch()
        map_layout.addLayout(toolbar)

        self.msg_table = QTableWidget(0, 4)
        self.msg_table.setHorizontalHeaderLabels(["Value", "Message Text", "Color", "Severity"])
        self.msg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.msg_table.itemDoubleClicked.connect(self._on_msg_edit)
        map_layout.addWidget(self.msg_table)
        
        # Inline Edit Form
        self.msg_form_grp = QGroupBox("Mapping Details")
        self.msg_form_grp.hide()
        m_form = QFormLayout(self.msg_form_grp)
        self.msg_val_spin = QSpinBox(); self.msg_val_spin.setRange(0, 65535)
        self.msg_txt_edit = QLineEdit(); self.msg_txt_edit.setMaxLength(200)
        self.msg_color_combo = QComboBox(); self.msg_color_combo.addItems(["green", "red", "yellow", "white", "amber"])
        self.msg_sev_combo = QComboBox(); self.msg_sev_combo.addItems(["INFO", "WARNING", "ERROR", "CRITICAL"])
        
        m_form.addRow("Trigger Value*:", self.msg_val_spin)
        m_form.addRow("Message Text*:", self.msg_txt_edit)
        m_form.addRow("Color:", self.msg_color_combo)
        m_form.addRow("Severity:", self.msg_sev_combo)
        
        btn_row = QHBoxLayout()
        self.msg_save_btn = QPushButton("Save")
        self.msg_save_btn.setObjectName("btn_primary")
        self.msg_save_btn.clicked.connect(self._on_msg_save)
        self.msg_rem_btn = QPushButton("Remove")
        self.msg_rem_btn.setObjectName("btn_danger")
        self.msg_rem_btn.clicked.connect(self._on_msg_delete)
        btn_row.addWidget(self.msg_rem_btn)
        btn_row.addStretch()
        btn_row.addWidget(QPushButton("Cancel", clicked=self.msg_form_grp.hide))
        btn_row.addWidget(self.msg_save_btn)
        m_form.addRow(btn_row)
        map_layout.addWidget(self.msg_form_grp)
        
        layout.addWidget(map_grp)

        # Bulk Import
        bulk_grp = QGroupBox("Bulk Import (CSV)")
        bulk_layout = QVBoxLayout(bulk_grp)
        self.msg_bulk_edit = QTextEdit()
        self.msg_bulk_edit.setPlaceholderText("value,message,color,severity (one per line)\ne.g. 10,Emergency Stop,red,CRITICAL")
        self.msg_bulk_edit.setFixedHeight(80)
        bulk_layout.addWidget(self.msg_bulk_edit)
        self.msg_bulk_btn = QPushButton("Import Lines")
        self.msg_bulk_btn.clicked.connect(self._on_msg_bulk_import)
        bulk_layout.addWidget(self.msg_bulk_btn)
        layout.addWidget(bulk_grp)

        self.tabs.addTab(page, "💬 Message Register")

    def _populate_msg_reg_combo(self) -> None:
        self.msg_reg_combo.clear()
        regs = self.app_state.library_repo.get_all_registers()
        for r in regs:
            self.msg_reg_combo.addItem(f"{r['name']} (D{r['register_address']})", r["id"])

    def _refresh_message_tab(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        reg_id = profile.get("message_register_id")
        if reg_id:
            reg = self.app_state.library_repo.get_register(reg_id)
            self.msg_curr_lbl.setText(f"Current: {reg['name']} (addr {reg['register_address']})")
            idx = self.msg_reg_combo.findData(reg_id)
            if idx >= 0: self.msg_reg_combo.setCurrentIndex(idx)
            
            # Table
            mappings = self.app_state.msg_repo.get_all_mappings(reg_id)
            self.msg_table.setRowCount(len(mappings))
            for i, m in enumerate(mappings):
                self.msg_table.setItem(i, 0, QTableWidgetItem(str(m["trigger_value"])))
                self.msg_table.setItem(i, 1, QTableWidgetItem(m["message_text"]))
                
                # Color preview
                c_item = QTableWidgetItem(m["color"])
                # Map standard colors to hex for preview
                color_map = {"green": "#22c55e", "red": "#ef4444", "yellow": "#eab308", "white": "#ffffff", "amber": "#f59e0b"}
                c_item.setBackground(QColor(color_map.get(m["color"], "#000000")))
                c_item.setForeground(QColor("black" if m["color"] in ["yellow", "white", "amber"] else "white"))
                self.msg_table.setItem(i, 2, c_item)
                self.msg_table.setItem(i, 3, QTableWidgetItem(m["severity"]))
                self.msg_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, m["id"])
        else:
            self.msg_curr_lbl.setText("Current: None")
            self.msg_table.setRowCount(0)

    def _on_msg_set_source(self) -> None:
        reg_id = self.msg_reg_combo.currentData()
        if self.app_state.profile_repo.update_profile(message_register_id=reg_id):
            self.app_state.refresh_message_config()
            self._refresh_message_tab()

    def _on_msg_add(self) -> None:
        self._current_msg_map_id = None
        self.msg_val_spin.setValue(0)
        self.msg_txt_edit.clear()
        self.msg_rem_btn.hide()
        self.msg_form_grp.setTitle("Add Mapping")
        self.msg_form_grp.show()

    def _on_msg_edit(self) -> None:
        rows = self.msg_table.selectedItems()
        if not rows: return
        mid = rows[0].data(Qt.ItemDataRole.UserRole)
        profile = self.app_state.profile_repo.get_profile()
        mappings = self.app_state.msg_repo.get_all_mappings(profile.get("message_register_id"))
        m = next((x for x in mappings if x["id"] == mid), None)
        if not m: return

        self._current_msg_map_id = mid
        self.msg_val_spin.setValue(m["trigger_value"])
        self.msg_txt_edit.setText(m["message_text"])
        self.msg_color_combo.setCurrentText(m["color"])
        self.msg_sev_combo.setCurrentText(m["severity"])
        self.msg_rem_btn.show()
        self.msg_form_grp.setTitle("Edit Mapping")
        self.msg_form_grp.show()

    def _on_msg_save(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        reg_id = profile.get("message_register_id")
        if not reg_id: return

        data = {
            "trigger_value": self.msg_val_spin.value(),
            "message_text": self.msg_txt_edit.text().strip(),
            "color": self.msg_color_combo.currentText(),
            "severity": self.msg_sev_combo.currentText(),
        }
        if not data["message_text"]: return

        if self._current_msg_map_id:
            self.app_state.msg_repo.update_message_mapping(self._current_msg_map_id, **data)
        else:
            self.app_state.msg_repo.add_message_mapping(reg_id, **data)
        
        self.app_state.refresh_message_config()
        self.msg_form_grp.hide()
        self._refresh_message_tab()

    def _on_msg_delete(self) -> None:
        if not hasattr(self, "_current_msg_map_id") or not self._current_msg_map_id: return
        if ConfirmDialog.ask(self, "Delete Mapping", "Remove this message trigger?"):
            self.app_state.msg_repo.delete_message_mapping(self._current_msg_map_id)
            self.app_state.refresh_message_config()
            self.msg_form_grp.hide()
            self._refresh_message_tab()

    def _on_msg_clear_all(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        reg_id = profile.get("message_register_id")
        if not reg_id: return
        if ConfirmDialog.ask(self, "Clear All", "Delete ALL message mappings for this register?", danger=True):
            self.app_state.msg_repo.delete_messages_for_register(reg_id)
            self.app_state.refresh_message_config()
            self._refresh_message_tab()

    def _on_msg_bulk_import(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        reg_id = profile.get("message_register_id")
        if not reg_id: return
        
        text = self.msg_bulk_edit.toPlainText().strip()
        if not text: return
        
        lines = text.split("\n")
        count = 0
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    val = int(parts[0].strip())
                    txt = parts[1].strip()
                    color = parts[2].strip() if len(parts) > 2 else "white"
                    sev = parts[3].strip() if len(parts) > 3 else "INFO"
                    self.app_state.msg_repo.add_message_mapping(reg_id, val, txt, color, sev)
                    count += 1
                except: continue
        
        QMessageBox.information(self, "Imported", f"Added {count} messages.")
        self.msg_bulk_edit.clear()
        self.app_state.refresh_message_config()
        self._refresh_message_tab()

    # =========================================================================
    # TAB 6: EXPORT / IMPORT
    # =========================================================================
    def _init_tab_export(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Export
        exp_grp = QGroupBox("Export Configuration")
        el = QVBoxLayout(exp_grp)
        el.addWidget(QLabel("Export all settings to a JSON file. Select items to include:"))
        
        self.exp_lib_cb = QCheckBox("Register Library"); self.exp_lib_cb.setChecked(True)
        self.exp_mod_cb = QCheckBox("Models + Mappings"); self.exp_mod_cb.setChecked(True)
        self.exp_io_cb = QCheckBox("I/O List Config"); self.exp_io_cb.setChecked(True)
        self.exp_ctrl_cb = QCheckBox("Control Registers"); self.exp_ctrl_cb.setChecked(True)
        self.exp_msg_cb = QCheckBox("Message Register Config"); self.exp_msg_cb.setChecked(True)
        self.exp_conn_cb = QCheckBox("PLC Connection (Host/Port)"); self.exp_conn_cb.setChecked(False)
        
        el.addWidget(self.exp_lib_cb); el.addWidget(self.exp_mod_cb); el.addWidget(self.exp_io_cb)
        el.addWidget(self.exp_ctrl_cb); el.addWidget(self.exp_msg_cb); el.addWidget(self.exp_conn_cb)
        
        self.exp_btn = QPushButton("📥 Export to JSON")
        self.exp_btn.setObjectName("btn_primary")
        self.exp_btn.setFixedHeight(50)
        self.exp_btn.clicked.connect(self._on_export)
        el.addWidget(self.exp_btn)
        layout.addWidget(exp_grp)

        # Import
        imp_grp = QGroupBox("Import Configuration")
        il = QVBoxLayout(imp_grp)
        il.addWidget(QLabel("Import settings from JSON. Existing config will be merged."))
        
        self.imp_merge_rb = QCheckBox("Merge (Skip existing names)"); self.imp_merge_rb.setChecked(True)
        self.imp_btn = QPushButton("📤 Import from JSON")
        self.imp_btn.setObjectName("btn_secondary")
        self.imp_btn.setFixedHeight(50)
        self.imp_btn.clicked.connect(self._on_import)
        il.addWidget(self.imp_btn)
        layout.addWidget(imp_grp)
        
        # Templates
        tmp_grp = QGroupBox("Quick Setup Templates")
        tl = QHBoxLayout(tmp_grp)
        tl.addWidget(QPushButton("Mitsubishi FX5U — Standard", clicked=lambda: self._load_template("fx5u")))
        tl.addWidget(QPushButton("Delta DVP-ES2 — Standard", clicked=lambda: self._load_template("dvp")))
        tl.addStretch()
        layout.addWidget(tmp_grp)

        layout.addStretch()
        self.tabs.addTab(page, "📦 Export / Import")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "plc_monitor_config.json", "JSON (*.json)")
        if not path: return
        
        data = {}
        if self.exp_lib_cb.isChecked(): data["library"] = self.app_state.library_repo.get_all_registers()
        if self.exp_mod_cb.isChecked():
            data["models"] = self.app_state.model_repo.get_all_models()
            data["mappings"] = [] # Would need deep loop, simplified for now
        if self.exp_io_cb.isChecked(): data["io_list"] = self.app_state.io_repo.get_io_config(active_only=False)
        if self.exp_ctrl_cb.isChecked(): data["controls"] = self.app_state.control_repo.get_all_controls()
        if self.exp_msg_cb.isChecked(): data["messages"] = self.app_state.msg_repo.get_all_mappings()
        if self.exp_conn_cb.isChecked(): data["profile"] = self.app_state.profile_repo.get_profile()
        
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Success", "Configuration exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "JSON (*.json)")
        if not path: return
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            if ConfirmDialog.ask(self, "Import Configuration", "Import settings from this file? This will merge with existing data."):
                # Import logic per section
                if "library" in data:
                    self.app_state.library_repo.import_library(data["library"], 1, overwrite=not self.imp_merge_rb.isChecked())
                # ... other sections similarly
                QMessageBox.information(self, "Success", "Import completed (Library only in this preview).")
                self.app_state.refresh_poll_config()
                self._refresh_tab_data(self.tabs.currentIndex())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import: {e}")

    def _load_template(self, plc_type: str) -> None:
        # Simplified template loader
        QMessageBox.information(self, "Template", f"Loading template for {plc_type}... (Simulation)")
