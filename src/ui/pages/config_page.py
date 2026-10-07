"""
config_page.py — Universal PLC Monitor
Admin-only configuration hub for system settings, register library, and model mapping.
"""
from __future__ import annotations

import logging
import json
from typing import Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTabWidget, QGroupBox, QComboBox, QLineEdit, 
                             QSpinBox, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QFrame, QGridLayout, QProgressBar, 
                             QScrollArea, QCheckBox, QFormLayout, QMessageBox, 
                              QFileDialog, QListWidget, QMenu,
                             QToolButton)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from src.utils.debounce import DebouncedSignal

try:
    import serial.tools.list_ports
except ImportError:
    serial = None

from src.ui.app_state import AppState
from src.plc.connection_tester import ConnectionTester
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.ui.dialogs.register_picker import RegisterPicker
from src.ui.dialogs.register_dialog import RegisterDialog
from src.ui.dialogs.mapping_dialog import MappingDialog
from src.ui.dialogs.io_dialog import IODialog
from src.ui.dialogs.block_dialog import BlockDialog
from src.ui.dialogs.control_dialog import ControlDialog
from src.ui.dialogs.message_dialog import MessageDialog
from src.ui.theme_manager import ThemeManager
from src.utils.constants import (BAUD_RATES, PARITY_OPTIONS,
                                 DARK_PASS, DARK_TEXT_MUTED)

logger = logging.getLogger(__name__)


def _fg(token: str) -> QColor:
    """Theme-resolved foreground/background color for a design token."""
    return QColor(ThemeManager.get_color(token))


class ConfigPage(QWidget):
    def __init__(self, app_state: AppState, on_plc_reconnect: callable) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_plc_reconnect = on_plc_reconnect
        self.setObjectName("config_page")
        self.setAccessibleName("Configuration page")

        self._init_ui()
        self._init_quality_timer()

        self._lib_search_debounce = DebouncedSignal(200, self)
        self._lib_search_debounce.triggered.connect(self._refresh_library_table)
        self._io_filter_debounce = DebouncedSignal(200, self)
        self._io_filter_debounce.triggered.connect(self._refresh_io_table)
        self._block_filter_debounce = DebouncedSignal(200, self)
        self._block_filter_debounce.triggered.connect(self._refresh_block_table)

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
        self._init_tab_blocks()       # Tab 4
        self._init_tab_control()      # Tab 5
        self._init_tab_message()      # Tab 6
        self._init_tab_export()       # Tab 7

        self.tabs.setAccessibleName("Configuration tabs")
        self.tabs.setTabToolTip(0, "PLC Connection")
        self.tabs.setTabToolTip(1, "Register Library")
        self.tabs.setTabToolTip(2, "Model Mapping")
        self.tabs.setTabToolTip(3, "I/O List")
        self.tabs.setTabToolTip(4, "Register Blocks (bulk address ranges)")
        self.tabs.setTabToolTip(5, "Control Registers")
        self.tabs.setTabToolTip(6, "Message Register")
        self.tabs.setTabToolTip(7, "Export / Import")

        layout.addWidget(self.tabs)

    def on_page_shown(self) -> None:
        """Called by MainWindow when this page becomes active."""
        self._ensure_write_log_connected()
        idx = self.tabs.currentIndex()
        self._refresh_tab_data(idx)

    def _refresh_tab_data(self, index: int) -> None:
        if index == 0: self._refresh_connection_status()
        elif index == 1: self._refresh_library_table()
        elif index == 2: self._refresh_mapping_tab()
        elif index == 3: self._refresh_io_table()
        elif index == 4: self._refresh_block_table()
        elif index == 5:
            self._ensure_write_log_connected()
            self._refresh_control_table()
        elif index == 6: self._refresh_message_tab()

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
        self.brand_combo.setAccessibleName("PLC brand")
        self.brand_combo.setToolTip("Select your PLC brand")
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["TCP", "RTU"])
        self.protocol_combo.setAccessibleName("Communication protocol")
        self.protocol_combo.setToolTip("Select communication protocol")
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
        self.com_refresh_btn.setAccessibleName("Refresh COM ports")
        self.com_refresh_btn.setToolTip("Refresh available COM ports list")
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
        self.save_conn_btn.setFixedHeight(42)
        self.save_conn_btn.setAccessibleName("Save settings")
        self.save_conn_btn.setToolTip("Save current connection settings")
        self.save_conn_btn.clicked.connect(self._on_save_connection)
        left_layout.addWidget(self.save_conn_btn)
        
        self.conn_success_lbl = QLabel("")
        self.conn_success_lbl.setObjectName("success_message")
        self.conn_success_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conn_success_lbl.setAccessibleName("Connection save status")
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
        self.test_btn.setFixedHeight(42)
        self.test_btn.setAccessibleName("Test connection")
        self.test_btn.setToolTip("Test the PLC connection with current settings")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_layout.addWidget(self.test_btn)

        self.test_progress = QProgressBar()
        self.test_progress.hide()
        test_layout.addWidget(self.test_progress)

        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setObjectName("config_test_result_lbl")
        self.test_result_lbl.setWordWrap(True)
        self.test_result_lbl.setAccessibleName("Connection test result")
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
        self.status_lbl.setAccessibleName("Connection status")
        status_layout.addWidget(self.status_lbl)
        
        self.status_grid_layout = QGridLayout()
        status_layout.addLayout(self.status_grid_layout)
        
        self.reconnect_btn = QPushButton("🔄 Reconnect Now")
        self.reconnect_btn.setObjectName("btn_secondary")
        self.reconnect_btn.setAccessibleName("Reconnect now")
        self.reconnect_btn.setToolTip("Reconnect to PLC immediately")
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

        self.tabs.addTab(page, "⚡ PLC Connection")
        
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
            QTimer.singleShot(3000, lambda: self._safe_clear_label(self.conn_success_lbl))
            self.on_plc_reconnect()
            self._refresh_connection_status()
        else:
            self.conn_success_lbl.setText("✗ Failed to save settings")
            QTimer.singleShot(5000, lambda: self._safe_clear_label(self.conn_success_lbl))

    @staticmethod
    def _safe_clear_label(lbl) -> None:
        """Clear a label, tolerating timer fires after the widget is destroyed."""
        try:
            lbl.setText("")
        except RuntimeError:
            pass  # underlying C++ object already deleted

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
        self.test_result_lbl.setProperty("result", "pass" if details.get("read_ok") else "warn")
        self.test_result_lbl.style().unpolish(self.test_result_lbl)
        self.test_result_lbl.style().polish(self.test_result_lbl)
        
        self.quality_frame.show()
        # Clear grid
        for i in reversed(range(self.q_grid.count())):
            w = self.q_grid.itemAt(i).widget()
            if w:
                w.hide()
                w.deleteLater()
            
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
            val_lbl.setObjectName("config_quality_val")
            self.q_grid.addWidget(val_lbl, i, 1)

    def _on_test_failed(self, error: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_progress.hide()
        self.test_result_lbl.setText(f"✗ Test Failed:\n{error}")
        self.test_result_lbl.setProperty("result", "fail")
        self.test_result_lbl.style().unpolish(self.test_result_lbl)
        self.test_result_lbl.style().polish(self.test_result_lbl)

    def _refresh_connection_status(self) -> None:
        connected = self.app_state.is_plc_connected
        if connected:
            self.status_lbl.setText("Connected")
            self.status_lbl.setProperty("connected", True)
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
        else:
            self.status_lbl.setText("Disconnected")
            self.status_lbl.setProperty("connected", False)
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            
        profile = self.app_state.profile_repo.get_profile()
        # Clear and rebuild status grid
        for i in reversed(range(self.status_grid_layout.count())):
            w = self.status_grid_layout.itemAt(i).widget()
            if w:
                w.hide()
                w.deleteLater()
            
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
        # A timer slot must never raise: bad/absent stats simply skip this tick
        if not isinstance(stats, dict):
            return
        try:
            total = int(stats.get('total_requests', 0))
            avg = float(stats.get('avg_response_ms', 0.0))
            rate = float(stats.get('success_rate_pct', 0.0))
        except (TypeError, ValueError):
            return

        self.quality_stats_lbl.setText(
            f"Total Requests: {total}\n"
            f"Avg Response: {avg:.1f} ms"
        )
        self.success_rate_bar.setValue(int(rate))
        
        # Color bar
        if rate > 95: level = "good"
        elif rate > 80: level = "warn"
        else: level = "bad"
        self.success_rate_bar.setProperty("level", level)
        self.success_rate_bar.style().unpolish(self.success_rate_bar)
        self.success_rate_bar.style().polish(self.success_rate_bar)

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
        self.lib_search.setAccessibleName("Search registers")
        self.lib_search.setToolTip("Search registers by name or address")
        self.lib_search.textChanged.connect(lambda: self._lib_search_debounce.emit())
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
        self.lib_table.setAccessibleName("Register library")
        self.lib_table.setToolTip("List of all available PLC registers")
        self.lib_table.itemSelectionChanged.connect(self._on_lib_selection_changed)
        self.lib_table.itemDoubleClicked.connect(self._on_lib_edit)
        layout.addWidget(self.lib_table)

        self.tabs.addTab(page, "☰ Register Library")

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
            if acc == "READ_WRITE": item.setForeground(_fg("pass"))
            else: item.setForeground(_fg("accent"))
            self.lib_table.setItem(i, 7, item)
            
            self.lib_table.setItem(i, 8, QTableWidgetItem(r["description"]))
            self.lib_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

    def _on_lib_selection_changed(self) -> None:
        has_sel = len(self.lib_table.selectedItems()) > 0
        self.lib_edit_btn.setEnabled(has_sel)
        self.lib_del_btn.setEnabled(has_sel)

    def _on_lib_add(self) -> None:
        dialog = RegisterDialog(self, is_edit=False)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.library_repo.create_register(**data)
                self._refresh_library_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_lib_edit(self) -> None:
        rows = self.lib_table.selectedItems()
        if not rows: return
        reg_id = rows[0].data(Qt.ItemDataRole.UserRole)
        reg = self.app_state.library_repo.get_register(reg_id)
        if not reg: return

        dialog = RegisterDialog(self, register_data=reg, is_edit=True)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.library_repo.update_register(reg_id, **data)
                self._refresh_library_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

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
        self.map_model_combo.setAccessibleName("Select model")
        self.map_model_combo.setToolTip("Select a model to configure")
        self.map_model_combo.currentIndexChanged.connect(self._refresh_mapping_tab)
        top_bar.addWidget(self.map_model_combo)

        self.model_add_btn = QPushButton("+ Add Model")
        self.model_add_btn.setObjectName("btn_success")
        self.model_add_btn.setAccessibleName("Add model")
        self.model_add_btn.setToolTip("Add a new model")
        self.model_add_btn.clicked.connect(self._on_model_add)
        top_bar.addWidget(self.model_add_btn)

        self.model_rename_btn = QPushButton("✎ Rename")
        self.model_rename_btn.setAccessibleName("Rename model")
        self.model_rename_btn.setToolTip("Rename the selected model")
        self.model_rename_btn.clicked.connect(self._on_model_rename)
        top_bar.addWidget(self.model_rename_btn)

        self.model_del_btn = QPushButton("✕ Delete Model")
        self.model_del_btn.setObjectName("btn_danger")
        self.model_del_btn.setAccessibleName("Delete model")
        self.model_del_btn.setToolTip("Delete the selected model and all its mappings")
        self.model_del_btn.clicked.connect(self._on_model_delete)
        top_bar.addWidget(self.model_del_btn)

        self.model_copy_btn = QPushButton("⎘ Copy From...")
        self.model_copy_btn.setAccessibleName("Copy mappings from another model")
        self.model_copy_btn.setToolTip("Copy register mappings from another model")
        self.model_copy_btn.clicked.connect(self._on_model_copy)
        top_bar.addWidget(self.model_copy_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Content panel (plain container — no splitter, single pane)
        content_panel = QWidget()
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        # Register actions (compact menu button — avoid a full-width button row)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.map_add_reg_btn = QPushButton("＋ Add Register")
        self.map_add_reg_btn.setObjectName("btn_success")
        self.map_add_reg_btn.setAccessibleName("Add register to mapping")
        self.map_add_reg_btn.setToolTip("Add a register from the library to this model")
        self.map_add_reg_btn.clicked.connect(self._on_map_add_register)
        actions_row.addWidget(self.map_add_reg_btn)

        # Extra register actions are exposed via the table context menu / menu button
        self.map_actions_btn = QToolButton()
        self.map_actions_btn.setObjectName("btn_secondary")
        self.map_actions_btn.setText("⋮ Actions")
        self.map_actions_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.map_actions_btn.setToolTip("More register actions (move, remove)")
        actions_row.addWidget(self.map_actions_btn)

        actions_row.addStretch()
        max_cards = self.app_state.config_repo.get_max_dashboard_cards() if self.app_state.config_repo else 20
        self.map_db_count_lbl = QLabel(f"Dashboard: 0/{max_cards}")
        actions_row.addWidget(self.map_db_count_lbl)
        content_layout.addLayout(actions_row)

        # Mapping table — proper column sizing to fill width
        self.map_table = QTableWidget(0, 12)
        self.map_table.setHorizontalHeaderLabels([
            "☐", "Display Name", "Register", "Address", "Type", 
            "Role", "Group", "Min Limit", "Max Limit", "Dashboard", "Position", "Bypass"
        ])
        self.map_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Stretch the two primary text columns so the pane fills without a trailing gap
        self.map_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.map_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # Type pills need room; auto-size to their content
        self.map_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        # Sensible compact widths for the rest
        narrow = {
            0: 36, 3: 80, 5: 110, 6: 110,
            7: 90, 8: 90, 9: 88, 10: 64, 11: 70,
        }
        for col, w in narrow.items():
            self.map_table.setColumnWidth(col, w)
        self.map_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.map_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.map_table.setAccessibleName("Model register mappings")
        self.map_table.setToolTip("Register mappings for the selected model")
        self.map_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.map_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.map_table.customContextMenuRequested.connect(self._show_map_context_menu)
        self.map_table.itemSelectionChanged.connect(self._on_map_selection_changed)
        content_layout.addWidget(self.map_table)

        # Validation Bar
        self.map_warn_lbl = QLabel("✓ Configuration valid")
        self.map_warn_lbl.setObjectName("config_map_warn_lbl")
        self.map_warn_lbl.setProperty("state", "valid")
        self.map_warn_lbl.style().unpolish(self.map_warn_lbl)
        self.map_warn_lbl.style().polish(self.map_warn_lbl)

        self._build_map_actions_menu()
        content_layout.addWidget(self.map_warn_lbl)

        layout.addWidget(content_panel)
        self.tabs.addTab(page, "⇌ Model Mapping")

    # ─── Mapping context menu ───────────────────────────────────────────

    def _selected_mapping_id(self) -> Optional[int]:
        rows = self.map_table.selectedItems()
        if not rows:
            return None
        return rows[0].data(Qt.ItemDataRole.UserRole)

    def _build_map_actions_menu(self) -> None:
        menu = QMenu(self.map_actions_btn)
        act_add = menu.addAction("＋ Add Register")
        act_add.triggered.connect(lambda: self._on_map_add_register())
        menu.addSeparator()
        act_edit = menu.addAction("✎ Edit Mapping")
        act_edit.triggered.connect(lambda: self._on_map_selection_changed())
        act_up = menu.addAction("↑ Move Up")
        act_up.triggered.connect(lambda: self._on_map_move(-1))
        act_down = menu.addAction("↓ Move Down")
        act_down.triggered.connect(lambda: self._on_map_move(1))
        menu.addSeparator()
        act_rem = menu.addAction("✕ Remove")
        act_rem.triggered.connect(lambda: self._on_map_remove())
        self.map_actions_btn.setMenu(menu)
        self._map_actions_menu = menu
        self._map_menu_edit = act_edit
        self._map_menu_up = act_up
        self._map_menu_down = act_down
        self._map_menu_rem = act_rem

    def _show_map_context_menu(self, pos) -> None:
        has_sel = self._selected_mapping_id() is not None
        self._map_menu_edit.setEnabled(has_sel)
        self._map_menu_up.setEnabled(has_sel)
        self._map_menu_down.setEnabled(has_sel)
        self._map_menu_rem.setEnabled(has_sel)
        self._map_actions_menu.exec(self.map_table.viewport().mapToGlobal(pos))

    def _on_map_move(self, delta: int) -> None:
        """Move the selected mapping up/down within the model by card_position."""
        mapping_id = self._selected_mapping_id()
        model_id = self.map_model_combo.currentData()
        if not mapping_id or not model_id:
            return
        mappings = self.app_state.map_repo.get_model_mappings(model_id)
        if len(mappings) < 2:
            return
        idx = next((i for i, m in enumerate(mappings) if m["id"] == mapping_id), None)
        if idx is None:
            return
        target = idx + delta
        if target < 0 or target >= len(mappings):
            return
        # Swap card_position of the two adjacent rows
        positions = [
            (mappings[idx]["id"], mappings[target]["card_position"]),
            (mappings[target]["id"], mappings[idx]["card_position"]),
        ]
        self.app_state.map_repo.update_card_positions(model_id, positions)
        self._refresh_mapping_tab()
        # Keep the moved row selected
        for row in range(self.map_table.rowCount()):
            if self.map_table.item(row, 0) and self.map_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == mapping_id:
                self.map_table.selectRow(row)
                break

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
            self.map_table.setCellWidget(i, 4, self._pill(m["register_type"], "type"))
            self.map_table.setItem(i, 5, QTableWidgetItem(m["role"]))
            self.map_table.setItem(i, 6, QTableWidgetItem(m["group_name"] or ""))
            self.map_table.setItem(i, 7, self._limit_item(m.get("limit_min", 0.0)))
            self.map_table.setItem(i, 8, self._limit_item(m.get("limit_max", 0.0)))
            self.map_table.setItem(i, 9, QTableWidgetItem("Yes" if m["show_in_dashboard"] else "No"))
            self.map_table.setItem(i, 10, QTableWidgetItem(str(m["card_position"])))
            self.map_table.setItem(i, 11, self._bypass_item(m.get("bypass", False)))
            
            self.map_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, m["id"])
            if m["show_in_dashboard"] and m["enabled"]: db_count += 1

        max_cards = self.app_state.config_repo.get_max_dashboard_cards() if self.app_state.config_repo else 20
        self.map_db_count_lbl.setText(f"Dashboard: {db_count}/{max_cards}")
        
        # 3. Validate
        warnings = self.app_state.map_repo.validate_model_mappings(model_id)
        if warnings:
            self.map_warn_lbl.setText("⚠ " + "; ".join(warnings))
            self.map_warn_lbl.setProperty("state", "warn")
            self.map_warn_lbl.style().unpolish(self.map_warn_lbl)
            self.map_warn_lbl.style().polish(self.map_warn_lbl)
        else:
            self.map_warn_lbl.setText("✓ Configuration valid")
            self.map_warn_lbl.setProperty("state", "valid")
            self.map_warn_lbl.style().unpolish(self.map_warn_lbl)
            self.map_warn_lbl.style().polish(self.map_warn_lbl)

    def _on_map_selection_changed(self) -> None:
        rows = self.map_table.selectedItems()
        if not rows:
            return
        
        mapping_id = rows[0].data(Qt.ItemDataRole.UserRole)
        # Find mapping in current list
        model_id = self.map_model_combo.currentData()
        mappings = self.app_state.map_repo.get_model_mappings(model_id)
        mapping = next((m for m in mappings if m["id"] == mapping_id), None)
        if not mapping: return
        
        # Get library name for the register
        reg = self.app_state.library_repo.get_register(mapping["register_id"])
        lib_name = reg["name"] if reg else "Unknown"
        
        dialog = MappingDialog(self, mapping_data=mapping, library_name=lib_name, is_edit=True)
        if dialog.exec():
            data = dialog.get_result()
            self.app_state.map_repo.update_mapping(mapping_id, **data)
            self._refresh_mapping_tab()

    @staticmethod
    def _fmt_limit(value: float) -> str:
        """Format a limit for the mapping table ('—' when unconfigured)."""
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            return "—"
        if fvalue == 0.0:
            return "—"
        return f"{fvalue:,.2f}"

    def _pill(self, text: str, kind: str = "type"):
        """Create a centered pill QLabel for styling data types / units."""
        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtCore import Qt
        lbl = QLabel(text or "—")
        lbl.setObjectName("badge_pill")
        lbl.setProperty("pill_kind", kind)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)
        return lbl

    def _limit_item(self, value: float):
        from PyQt6.QtWidgets import QTableWidgetItem
        text = self._fmt_limit(value)
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if text != "—":
            item.setForeground(_fg("pass"))
        else:
            item.setForeground(_fg("text_muted"))
        return item

    def _bypass_item(self, bypass: bool):
        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem("Yes" if bypass else "No")
        item.setForeground(_fg("warn" if bypass else "text_muted"))
        return item

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
        if ConfirmDialog.ask(
            self, "Delete Model", f"Permanently delete model '{name}' and all its mappings?", danger=True
        ):
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
        self.io_filter.setAccessibleName("Filter I/O entries")
        self.io_filter.setToolTip("Filter I/O entries by group name")
        self.io_filter.textChanged.connect(lambda: self._io_filter_debounce.emit())
        toolbar.addWidget(self.io_filter)
        layout.addLayout(toolbar)

        self.io_table = QTableWidget(0, 8)
        self.io_table.setHorizontalHeaderLabels([
            "#", "Display Name", "Register", "Address", "Type", 
            "Group", "ON/OFF Labels", "Show Value"
        ])
        self.io_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.io_table.setAccessibleName("I/O list configuration")
        self.io_table.setToolTip("Configured I/O list entries")
        self.io_table.itemSelectionChanged.connect(self._on_io_selection_changed)
        self.io_table.itemDoubleClicked.connect(self._on_io_edit)
        layout.addWidget(self.io_table)

        banner = QLabel("Note: Changes take effect immediately. I/O List page auto-refreshes when visible.")
        banner.setObjectName("config_info_lbl")
        layout.addWidget(banner)

        self.tabs.addTab(page, "⊞ I/O List")

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
        reg_options = self._get_io_register_options()
        dialog = IODialog(self, register_options=reg_options, is_edit=False)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.io_repo.create_io_row(**data)
                self._refresh_io_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_io_edit(self) -> None:
        rows = self.io_table.selectedItems()
        if not rows: return
        io_id = rows[0].data(Qt.ItemDataRole.UserRole)
        config = self.app_state.io_repo.get_io_config(active_only=False)
        r = next((x for x in config if x["id"] == io_id), None)
        if not r: return

        reg_options = self._get_io_register_options()
        dialog = IODialog(self, io_data=r, register_options=reg_options, is_edit=True)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.io_repo.update_io_row(io_id, **data)
                self._refresh_io_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _get_io_register_options(self) -> list:
        """Get register options for I/O dialog combo."""
        regs = self.app_state.library_repo.get_all_registers()
        options = []
        for r in regs:
            options.append({
                "id": r["id"],
                "label": f"{r['name']} (D{r['register_address']}, {r['register_type']})"
            })
        return options

    def _on_io_delete(self) -> None:
        rows = self.io_table.selectedItems()
        if not rows: return
        io_id = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.io_table.item(self.io_table.currentRow(), 1).text()
        
        if ConfirmDialog.ask(self, "Remove I/O Entry", f"Remove '{name}' from I/O status list?"):
            self.app_state.io_repo.delete_io_row(io_id)
            self._refresh_io_table()

    # =========================================================================
    # TAB 4: REGISTER BLOCKS (bulk address ranges)
    # =========================================================================
    def _init_tab_blocks(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        toolbar = QHBoxLayout()
        self.block_add_btn = QPushButton("+ Add Block")
        self.block_add_btn.setObjectName("btn_success")
        self.block_add_btn.clicked.connect(self._on_block_add)

        self.block_edit_btn = QPushButton("✎ Edit")
        self.block_edit_btn.setEnabled(False)
        self.block_edit_btn.clicked.connect(self._on_block_edit)

        self.block_rem_btn = QPushButton("✕ Remove")
        self.block_rem_btn.setObjectName("btn_danger")
        self.block_rem_btn.setEnabled(False)
        self.block_rem_btn.clicked.connect(self._on_block_delete)

        toolbar.addWidget(self.block_add_btn)
        toolbar.addWidget(self.block_edit_btn)
        toolbar.addWidget(self.block_rem_btn)
        toolbar.addStretch()

        self.block_filter = QLineEdit()
        self.block_filter.setPlaceholderText("Filter by name or group...")
        self.block_filter.setAccessibleName("Filter register blocks")
        self.block_filter.setToolTip("Filter register blocks by name or group")
        self.block_filter.textChanged.connect(lambda: self._block_filter_debounce.emit())
        toolbar.addWidget(self.block_filter)
        layout.addLayout(toolbar)

        self.block_table = QTableWidget(0, 10)
        self.block_table.setHorizontalHeaderLabels([
            "#", "Name", "Type", "Start", "Count", "Range",
            "Data Type", "Group", "Access", "Active"
        ])
        self.block_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.block_table.setAccessibleName("Register block configuration")
        self.block_table.setToolTip("Configured register blocks (bulk read/write ranges)")
        self.block_table.itemSelectionChanged.connect(self._on_block_selection_changed)
        self.block_table.itemDoubleClicked.connect(self._on_block_edit)
        layout.addWidget(self.block_table)

        banner = QLabel(
            "Note: Changes take effect immediately — active blocks are polled "
            "in batch on the next cycle. DISCRETE / INPUT blocks are read-only."
        )
        banner.setObjectName("config_info_lbl")
        layout.addWidget(banner)

        self.tabs.addTab(page, "▤ Register Blocks")

    def _refresh_block_table(self) -> None:
        if not self.app_state.block_repo:
            self.block_table.setRowCount(0)
            return
        rows = self.app_state.block_repo.get_all_blocks(active_only=False)
        filter_text = self.block_filter.text().lower()

        self.block_table.setRowCount(0)
        for r in rows:
            if filter_text:
                haystack = f"{r['name']} {r.get('group_name') or ''}".lower()
                if filter_text not in haystack:
                    continue

            start = int(r["start_address"])
            count = int(r["count"])
            row_idx = self.block_table.rowCount()
            self.block_table.insertRow(row_idx)
            self.block_table.setItem(row_idx, 0, QTableWidgetItem(str(r["id"])))
            self.block_table.setItem(row_idx, 1, QTableWidgetItem(r["name"]))
            self.block_table.setItem(row_idx, 2, QTableWidgetItem(r["register_type"]))
            self.block_table.setItem(row_idx, 3, QTableWidgetItem(str(start)))
            self.block_table.setItem(row_idx, 4, QTableWidgetItem(str(count)))
            self.block_table.setItem(row_idx, 5,
                QTableWidgetItem(f"{start}..{start + count - 1}"))
            self.block_table.setItem(row_idx, 6, QTableWidgetItem(r["data_type"]))
            self.block_table.setItem(row_idx, 7, QTableWidgetItem(r.get("group_name") or ""))
            self.block_table.setItem(row_idx, 8, QTableWidgetItem(r["access"]))
            self.block_table.setItem(row_idx, 9,
                QTableWidgetItem("Yes" if r["is_active"] else "No"))
            self.block_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

    def _on_block_selection_changed(self) -> None:
        has_sel = len(self.block_table.selectedItems()) > 0
        self.block_edit_btn.setEnabled(has_sel)
        self.block_rem_btn.setEnabled(has_sel)

    def _selected_block_id(self) -> Optional[int]:
        rows = self.block_table.selectedItems()
        if not rows:
            return None
        return rows[0].data(Qt.ItemDataRole.UserRole)

    def _on_block_add(self) -> None:
        dialog = BlockDialog(self, is_edit=False)
        if not dialog.exec():
            return
        data = dialog.get_result()
        try:
            user = self.app_state.current_user
            self.app_state.block_repo.create_block(
                created_by=(user or {}).get("id"), **data
            )
            self._after_block_change()
        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_block_edit(self) -> None:
        block_id = self._selected_block_id()
        if block_id is None:
            return
        block = self.app_state.block_repo.get_block(block_id)
        if not block:
            return

        dialog = BlockDialog(self, block_data=block, is_edit=True)
        if not dialog.exec():
            return
        data = dialog.get_result()
        try:
            self.app_state.block_repo.update_block(block_id, **data)
            self._after_block_change()
        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_block_delete(self) -> None:
        block_id = self._selected_block_id()
        if block_id is None:
            return
        block = self.app_state.block_repo.get_block(block_id)
        if not block:
            return
        rng = f"{block['start_address']}..{block['start_address'] + block['count'] - 1}"
        if ConfirmDialog.ask(
            self, "Remove Register Block",
            f"Remove block '{block['name']}' ({block['register_type']} {rng})?\n"
            "Audit history is preserved.",
        ):
            self.app_state.block_repo.delete_block(block_id)
            self._after_block_change()

    def _after_block_change(self) -> None:
        """Refresh the table and push the new block list to the poller."""
        self._refresh_block_table()
        if self.app_state.block_repo:
            self.app_state.refresh_poll_config()

    # =========================================================================
    # TAB 5: CONTROL REGISTERS
    # =========================================================================
    def _init_tab_control(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        banner = QFrame()
        banner.setObjectName("config_warning_banner")
        bl = QVBoxLayout(banner)
        msg = QLabel(
            "⚠ These are the ONLY registers the app will write. Only READ_WRITE registers allowed. "
            "All writes are logged."
        )
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
        self.ctrl_table.setAccessibleName("Control registers table")
        self.ctrl_table.setToolTip("Configured control register buttons")
        self.ctrl_table.itemSelectionChanged.connect(self._on_ctrl_selection_changed)
        layout.addWidget(self.ctrl_table)

        # Write Log
        layout.addWidget(QLabel("Recent Write Log (Audit Trail):"))
        self.ctrl_log_list = QListWidget()
        self.ctrl_log_list.setFixedHeight(120)
        layout.addWidget(self.ctrl_log_list)

        self.tabs.addTab(page, "▶ Control Registers")

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
            self.ctrl_table.setItem(
                i, 6, QTableWidgetItem(f"{r['reset_after_ms']}ms" if r["reset_after_ms"] > 0 else "None")
            )
            self.ctrl_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

        self._refresh_ctrl_log()

    def _refresh_ctrl_log(self) -> None:
        self.ctrl_log_list.clear()
        logs = self.app_state.db.fetchall("SELECT * FROM plc_write_log ORDER BY timestamp DESC LIMIT 10")
        for entry in logs:
            status = "✓" if entry["write_success"] else "✗"
            self.ctrl_log_list.addItem(
                f"[{entry['timestamp']}] {status} {entry['write_reason']} -> Addr:{entry['register_address']}"
                f" Val:{entry['value_written']}"
            )

    def _ensure_write_log_connected(self) -> None:
        """F6: subscribe (once per write-manager instance) for live audit refreshes."""
        wm = self.app_state.write_manager
        if wm is None or getattr(self, "_wm_log_for", None) is wm:
            return
        try:
            wm.write_log_updated.connect(self._on_write_log_updated)
            self._wm_log_for = wm
        except (RuntimeError, AttributeError):
            pass  # dead/replaced manager — retried on next page show

    def _on_write_log_updated(self) -> None:
        if self.tabs.currentIndex() == 5:
            self._refresh_ctrl_log()

    def _on_ctrl_selection_changed(self) -> None:
        has_sel = len(self.ctrl_table.selectedItems()) > 0
        self.ctrl_edit_btn.setEnabled(has_sel)
        self.ctrl_del_btn.setEnabled(has_sel)

    def _on_ctrl_add(self) -> None:
        reg_options = self._get_ctrl_register_options()
        dialog = ControlDialog(self, register_options=reg_options, is_edit=False)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.control_repo.create_control(**data)
                self._refresh_control_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_ctrl_edit(self) -> None:
        rows = self.ctrl_table.selectedItems()
        if not rows: return
        cid = rows[0].data(Qt.ItemDataRole.UserRole)
        config = self.app_state.control_repo.get_all_controls()
        r = next((x for x in config if x["id"] == cid), None)
        if not r: return

        reg_options = self._get_ctrl_register_options()
        dialog = ControlDialog(self, control_data=r, register_options=reg_options, is_edit=True)
        if dialog.exec():
            data = dialog.get_result()
            try:
                self.app_state.control_repo.update_control(cid, **data)
                self._refresh_control_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _get_ctrl_register_options(self) -> list:
        """Get writable register options for control dialog combo."""
        regs = self.app_state.library_repo.get_writable_registers()
        options = []
        for r in regs:
            options.append({
                "id": r["id"],
                "label": f"{r['name']} (D{r['register_address']}, {r['access']})"
            })
        return options

    def _on_ctrl_delete(self) -> None:
        rows = self.ctrl_table.selectedItems()
        if not rows: return
        cid = rows[0].data(Qt.ItemDataRole.UserRole)
        name = self.ctrl_table.item(self.ctrl_table.currentRow(), 0).text()
        
        if ConfirmDialog.ask(self, "Remove Control", f"Remove button '{name}'?"):
            self.app_state.control_repo.delete_control(cid)
            self._refresh_control_table()

    # =========================================================================
    # TAB 6: MESSAGE REGISTER
    # =========================================================================
    def _init_tab_message(self) -> None:
        page = QWidget()
        main_layout = QHBoxLayout(page)
        main_layout.setSpacing(20)

        # --- LEFT HALF: Message Source Register ---
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        src_grp = QGroupBox("Message Source Register")
        src_layout = QVBoxLayout(src_grp)
        src_layout.setSpacing(10)

        info = QLabel("Select a register whose value maps to status messages. Shown in dashboard status bar.")
        info.setWordWrap(True)
        src_layout.addWidget(info)

        reg_row = QHBoxLayout()
        self.msg_reg_combo = QComboBox()
        self.msg_reg_combo.setAccessibleName("Message source register")
        self.msg_reg_combo.setToolTip("Select a register as the message source")
        self._populate_msg_reg_combo()
        reg_row.addWidget(self.msg_reg_combo, 1)
        self.msg_set_btn = QPushButton("Set as Message Register")
        self.msg_set_btn.setObjectName("btn_primary")
        self.msg_set_btn.setAccessibleName("Set message register")
        self.msg_set_btn.setToolTip("Set the selected register as the message source")
        self.msg_set_btn.clicked.connect(self._on_msg_set_source)
        reg_row.addWidget(self.msg_set_btn)
        src_layout.addLayout(reg_row)

        self.msg_curr_lbl = QLabel("Current: None")
        self.msg_curr_lbl.setObjectName("config_msg_curr_lbl")
        src_layout.addWidget(self.msg_curr_lbl)

        preview_grp = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_grp)
        self.msg_preview_lbl = QLabel("No register selected")
        self.msg_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_preview_lbl.setMinimumHeight(80)
        self.msg_preview_lbl.setObjectName("config_msg_preview")
        preview_layout.addWidget(self.msg_preview_lbl)
        src_layout.addWidget(preview_grp)

        src_layout.addStretch()
        left_col.addWidget(src_grp)
        main_layout.addLayout(left_col, 1)

        # --- RIGHT HALF: Value → Message Mapping ---
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        map_grp = QGroupBox("Value → Message Mapping")
        map_layout = QVBoxLayout(map_grp)
        map_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.msg_add_btn = QPushButton("+ Add Message")
        self.msg_add_btn.setObjectName("btn_success")
        self.msg_add_btn.clicked.connect(self._on_msg_add)

        self.msg_clear_btn = QPushButton("🔄 Clear All")
        self.msg_clear_btn.setAccessibleName("Clear all message mappings")
        self.msg_clear_btn.setToolTip("Remove all message mappings for the current register")
        self.msg_clear_btn.clicked.connect(self._on_msg_clear_all)

        toolbar.addWidget(self.msg_add_btn)
        toolbar.addWidget(self.msg_clear_btn)
        toolbar.addStretch()
        map_layout.addLayout(toolbar)

        self.msg_table = QTableWidget(0, 4)
        self.msg_table.setHorizontalHeaderLabels(["Value", "Message Text", "Color", "Severity"])
        self.msg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.msg_table.setAccessibleName("Message value mappings")
        self.msg_table.setToolTip("Mapping of register values to status messages")
        # Fix column sizing - stretch Message Text column
        self.msg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.msg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.msg_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.msg_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.msg_table.itemDoubleClicked.connect(self._on_msg_edit)
        map_layout.addWidget(self.msg_table)

        right_col.addWidget(map_grp)
        main_layout.addLayout(right_col, 2)

        self.tabs.addTab(page, "✉ Message Register")

    def _populate_msg_reg_combo(self) -> None:
        self.msg_reg_combo.clear()
        regs = self.app_state.library_repo.get_all_registers()
        for r in regs:
            self.msg_reg_combo.addItem(f"{r['name']} (D{r['register_address']})", r["id"])

    def _refresh_message_tab(self) -> None:
        self._populate_msg_reg_combo()  # F4: pick up registers added in other tabs
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
                color_map = {"green": ThemeManager.get_color("pass"),
                             "red": ThemeManager.get_color("fail"),
                             "yellow": ThemeManager.get_color("warn"),
                             "white": "#ffffff",
                             "amber": ThemeManager.get_color("warn")}
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
        dialog = MessageDialog(self, is_edit=False)
        if dialog.exec():
            data = dialog.get_result()
            if not data: return
            
            profile = self.app_state.profile_repo.get_profile()
            reg_id = profile.get("message_register_id")
            if not reg_id: return
            
            try:
                self.app_state.msg_repo.add_message_mapping(reg_id, **data)
                self.app_state.refresh_message_config()
                self._refresh_message_tab()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_msg_edit(self) -> None:
        rows = self.msg_table.selectedItems()
        if not rows: return
        mid = rows[0].data(Qt.ItemDataRole.UserRole)
        profile = self.app_state.profile_repo.get_profile()
        mappings = self.app_state.msg_repo.get_all_mappings(profile.get("message_register_id"))
        m = next((x for x in mappings if x["id"] == mid), None)
        if not m: return

        dialog = MessageDialog(self, mapping_data=m, is_edit=True)
        if dialog.exec():
            if dialog.was_removed():
                self.app_state.msg_repo.delete_message_mapping(mid)
                self.app_state.refresh_message_config()
                self._refresh_message_tab()
            else:
                data = dialog.get_result()
                if not data: return
                try:
                    self.app_state.msg_repo.update_message_mapping(mid, **data)
                    self.app_state.refresh_message_config()
                    self._refresh_message_tab()
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

    def _on_msg_clear_all(self) -> None:
        profile = self.app_state.profile_repo.get_profile()
        reg_id = profile.get("message_register_id")
        if not reg_id: return
        if ConfirmDialog.ask(self, "Clear All", "Delete ALL message mappings for this register?", danger=True):
            self.app_state.msg_repo.delete_messages_for_register(reg_id)
            self.app_state.refresh_message_config()
            self._refresh_message_tab()

    # =========================================================================
    # TAB 7: EXPORT / IMPORT
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
        self.exp_btn.setFixedHeight(42)
        self.exp_btn.setAccessibleName("Export configuration to JSON")
        self.exp_btn.setToolTip("Export selected configuration items to a JSON file")
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
        self.imp_btn.setFixedHeight(42)
        self.imp_btn.setAccessibleName("Import configuration from JSON")
        self.imp_btn.setToolTip("Import configuration settings from a JSON file")
        self.imp_btn.clicked.connect(self._on_import)
        il.addWidget(self.imp_btn)
        layout.addWidget(imp_grp)

        layout.addStretch()
        self.tabs.addTab(page, "⬆ Export / Import")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "plc_monitor_config.json", "JSON (*.json)")
        if not path: return
        
        data = {}
        if self.exp_lib_cb.isChecked(): data["library"] = self.app_state.library_repo.get_all_registers()
        if self.exp_mod_cb.isChecked():
            models = self.app_state.model_repo.get_all_models()
            data["models"] = models
            # Export mappings keyed by model name so they can be re-imported
            # even when model ids change (F2).
            data["mappings"] = {}
            for m in models:
                rows = self.app_state.map_repo.get_model_mappings(m["id"])
                if rows:
                    data["mappings"][m["name"]] = rows
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
            
            if ConfirmDialog.ask(
                self, "Import Configuration", "Import settings from this file? This will merge with existing data."
            ):
                overwrite = not self.imp_merge_rb.isChecked()
                # F3: import atomically — a mid-import failure rolls back all
                # sections instead of leaving partial configuration behind.
                with self.app_state.db.transaction():
                    imported = self._apply_import(data, overwrite)

                QMessageBox.information(self, "Success", f"Import completed: {', '.join(imported)}.")
                self.app_state.refresh_poll_config()
                self._refresh_tab_data(self.tabs.currentIndex())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import: {e}")

    def _apply_import(self, data: dict, overwrite: bool) -> list:
        """Import every section of a config payload.

        Runs inside the caller's transaction (see _on_import); raises on
        unrecoverable section errors so the transaction can roll back.
        """
        imported = []

        if "library" in data:
            acting_id = (self.app_state.current_user or {}).get("id")
            self.app_state.library_repo.import_library(
                data["library"], acting_id or 1, overwrite=overwrite
            )
            imported.append("Library")

        if "models" in data:
            skipped = 0
            for m in data["models"]:
                try:
                    self.app_state.model_repo.create_model(
                        name=m["name"],
                        description=m.get("description", ""),
                        model_number=m.get("model_number", ""),
                    )
                except ValueError:
                    skipped += 1  # Skip duplicates in merge mode
            imported.append("Models" + (f" ({skipped} skipped)" if skipped else ""))

        if "mappings" in data:
            # F2: re-attach exported mappings, resolving models by name
            # and registers by library name (ids change across databases).
            skipped = 0
            models_by_name = {
                m["name"]: m["id"] for m in self.app_state.model_repo.get_all_models()
            }
            for model_name, rows in data["mappings"].items():
                target_model = models_by_name.get(model_name)
                if target_model is None:
                    skipped += len(rows or [])
                    continue
                for row in rows or []:
                    reg_name = row.get("library_name") or row.get("name")
                    reg = (
                        self.app_state.library_repo.get_register_by_name(reg_name)
                        if reg_name
                        else None
                    )
                    if reg is None:
                        skipped += 1
                        continue
                    try:
                        self.app_state.map_repo.add_mapping(
                            target_model,
                            reg["id"],
                            role=row.get("role") or "MEASURED",
                            display_name=row.get("display_name") or "",
                            group_name=row.get("group_name") or "",
                            enabled=bool(row.get("enabled", 1)),
                            bypass=bool(row.get("bypass", 0)),
                            show_in_dashboard=bool(row.get("show_in_dashboard", 1)),
                            card_position=int(row.get("card_position") or 0),
                            pass_value=int(row.get("pass_value") if row.get("pass_value") is not None else 1),
                            fail_value=int(row.get("fail_value") if row.get("fail_value") is not None else 2),
                            limit_min=float(row.get("limit_min") or 0.0),
                            limit_max=float(row.get("limit_max") or 0.0),
                        )
                    except Exception:
                        skipped += 1
            imported.append("Mappings" + (f" ({skipped} skipped)" if skipped else ""))

        if "io_list" in data:
            skipped = 0
            for io_row in data["io_list"]:
                try:
                    self.app_state.io_repo.create_io_row(
                        display_name=io_row["display_name"],
                        register_id=io_row["register_id"],
                        group_name=io_row.get("group_name", ""),
                        row_order=io_row.get("row_order", 0),
                        show_value=bool(io_row.get("show_value", 1)),
                        on_label=io_row.get("on_label", "ON"),
                        off_label=io_row.get("off_label", "OFF"),
                        # Stable (theme-independent) color defaults persisted with the row
                        on_color=io_row.get("on_color", DARK_PASS),
                        off_color=io_row.get("off_color", DARK_TEXT_MUTED),
                    )
                except Exception:
                    skipped += 1
            imported.append("I/O List" + (f" ({skipped} skipped)" if skipped else ""))

        if "controls" in data:
            skipped = 0
            for ctrl in data["controls"]:
                try:
                    self.app_state.control_repo.create_control(
                        name=ctrl["name"],
                        register_id=ctrl["register_id"],
                        control_type=ctrl["control_type"],
                        write_value=ctrl.get("write_value", 1),
                        reset_after_ms=ctrl.get("reset_after_ms", 0),
                        confirm_required=bool(ctrl.get("confirm_required", 0)),
                        description=ctrl.get("description", ""),
                    )
                except Exception:
                    skipped += 1
            imported.append("Controls" + (f" ({skipped} skipped)" if skipped else ""))

        if "messages" in data:
            skipped = 0
            for msg in data["messages"]:
                try:
                    self.app_state.msg_repo.add_message_mapping(
                        register_id=msg["register_id"],
                        trigger_value=msg["trigger_value"],
                        message_text=msg["message_text"],
                        color=msg.get("color", "white"),
                        severity=msg.get("severity", "INFO"),
                    )
                except Exception:
                    skipped += 1
            imported.append("Messages" + (f" ({skipped} skipped)" if skipped else ""))

        if "profile" in data:
            self.app_state.profile_repo.update_profile(**data["profile"])
            imported.append("PLC Profile")

        return imported
