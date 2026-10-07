# src/ui/dialogs/plc_profile_dialog.py
"""
Full-featured PLC profile editor dialog.
Covers brand, protocol, TCP/RTU connection, timing and key register addresses.
Includes a live connection test via a background QThread.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox,
    QGroupBox, QPushButton, QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QRegularExpression, QThread, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator

from src.ui.app_state import AppState
from src.utils.constants import (
    PLC_BRAND_LABELS,
    PLC_BRANDS,
    PLC_PROTOCOL_TCP,
    PLC_PROTOCOL_RTU,
    BAUD_RATES,
    DEFAULT_STATE_REGISTER,
    DEFAULT_START_COIL,
    DEFAULT_OVERALL_RESULT_REGISTER,
    DEFAULT_OK_COUNT_REGISTER,
    DEFAULT_NG_COUNT_REGISTER,
)
from src.utils.validators import validate_ip, validate_port

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background connection tester
# ---------------------------------------------------------------------------

class _ConnectionTester(QThread):
    """
    Tests PLC reachability in a background thread so the UI stays responsive.
    Emits result(success: bool, message: str).
    """

    result = pyqtSignal(bool, str)

    def __init__(self, params: dict, parent=None) -> None:
        super().__init__(parent)
        self._params = params

    def run(self) -> None:  # noqa: D401
        protocol = self._params.get("protocol", "TCP")
        try:
            if protocol == PLC_PROTOCOL_TCP:
                import socket
                host = self._params["host"]
                port = self._params["port"]
                with socket.create_connection((host, port), timeout=3):
                    pass
                self.result.emit(
                    True, f"✔  Connected to {host}:{port} successfully."
                )
            else:
                # RTU: just check that the COM port exists
                import serial
                com = self._params.get("com_port", "COM1")
                s = serial.Serial(com, timeout=1)
                s.close()
                self.result.emit(True, f"✔  Serial port {com} opened successfully.")
        except Exception as exc:
            self.result.emit(False, f"✘  Connection failed: {exc}")


# ---------------------------------------------------------------------------
# PLCProfileDialog
# ---------------------------------------------------------------------------

class PLCProfileDialog(QDialog):
    """
    Dialog to view and edit the global PLC connection profile.

    Changes are written to ``app_state.plc_profile_repo`` then synced
    back into ``app_state.plc_profile``.
    """

    def __init__(self, app_state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._tester: Optional[_ConnectionTester] = None

        self.setWindowTitle("PLC Connection Profile")
        self.setFixedSize(520, 680)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._setup_ui()
        self._load_profile()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        root.addWidget(self._build_brand_group())
        root.addWidget(self._build_tcp_group())
        root.addWidget(self._build_rtu_group())
        root.addWidget(self._build_timing_group())
        root.addWidget(self._build_registers_group())

        # ── Test button ───────────────────────────────────────────────
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setObjectName("btn_secondary")
        self.test_btn.setFixedWidth(160)
        self.test_btn.clicked.connect(self._on_test_connection)

        self.result_lbl = QLabel()
        self.result_lbl.hide()
        self.result_lbl.setWordWrap(True)

        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.result_lbl, stretch=1)
        root.addLayout(test_row)

        # ── Button box ────────────────────────────────────────────────
        btn_box = QDialogButtonBox(Qt.Orientation.Horizontal)
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(
            "background: #1e2d4a; color: white; min-width: 90px;"
        )
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("btn_secondary")

        btn_box.addButton(self.save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(self.cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # ── Sub-groups ─────────────────────────────────────────────────────

    def _build_brand_group(self) -> QGroupBox:
        grp = QGroupBox("PLC Brand & Protocol")
        form = QFormLayout(grp)

        self.brand_combo = QComboBox()
        for key, label in PLC_BRAND_LABELS.items():
            self.brand_combo.addItem(label, key)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems([PLC_PROTOCOL_TCP, PLC_PROTOCOL_RTU])
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_changed)

        form.addRow(QLabel("Brand:"), self.brand_combo)
        form.addRow(QLabel("Protocol:"), self.protocol_combo)
        return grp

    def _build_tcp_group(self) -> QGroupBox:
        self.tcp_group = QGroupBox("Network Connection (TCP)")
        form = QFormLayout(self.tcp_group)

        ip_regex = QRegularExpression(
            r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
        )
        self.host_field = QLineEdit()
        self.host_field.setPlaceholderText("192.168.1.1")
        self.host_field.setValidator(QRegularExpressionValidator(ip_regex))

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)

        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)

        form.addRow(QLabel("Host / IP:"), self.host_field)
        form.addRow(QLabel("Port:"), self.port_spin)
        form.addRow(QLabel("Slave ID:"), self.slave_spin)
        return self.tcp_group

    def _build_rtu_group(self) -> QGroupBox:
        self.rtu_group = QGroupBox("Serial Connection (RTU)")
        form = QFormLayout(self.rtu_group)

        self.com_field = QLineEdit()
        self.com_field.setPlaceholderText("COM1")

        self.baud_combo = QComboBox()
        for rate in BAUD_RATES:
            self.baud_combo.addItem(str(rate), rate)

        form.addRow(QLabel("COM Port:"), self.com_field)
        form.addRow(QLabel("Baud Rate:"), self.baud_combo)
        self.rtu_group.hide()          # hidden until protocol = RTU
        return self.rtu_group

    def _build_timing_group(self) -> QGroupBox:
        grp = QGroupBox("Timing")
        form = QFormLayout(grp)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(100, 5000)
        self.poll_spin.setSuffix(" ms")
        self.poll_spin.setValue(500)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setSuffix(" sec")
        self.timeout_spin.setValue(3)

        form.addRow(QLabel("Poll Interval:"), self.poll_spin)
        form.addRow(QLabel("Timeout:"), self.timeout_spin)
        return grp

    def _build_registers_group(self) -> QGroupBox:
        grp = QGroupBox("Key Register Addresses")
        layout = QVBoxLayout(grp)

        hint = QLabel(
            "Enter D register numbers (e.g. enter 20 for D20). "
            "Set Heartbeat to 0 to disable."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5a6a8a; font-size: 11px;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(6)

        def _reg_spin(default: int, allow_zero: bool = False) -> QSpinBox:
            s = QSpinBox()
            s.setRange(0, 65535)
            s.setValue(default)
            return s

        self.state_reg_spin   = _reg_spin(DEFAULT_STATE_REGISTER)
        self.start_coil_spin  = _reg_spin(DEFAULT_START_COIL)
        self.result_reg_spin  = _reg_spin(DEFAULT_OVERALL_RESULT_REGISTER)
        self.ok_reg_spin      = _reg_spin(DEFAULT_OK_COUNT_REGISTER)
        self.ng_reg_spin      = _reg_spin(DEFAULT_NG_COUNT_REGISTER)
        self.heartbeat_spin   = _reg_spin(0)   # 0 = disabled

        form.addRow(QLabel("State Register:"),   self.state_reg_spin)
        form.addRow(QLabel("Start Coil (M):"),   self.start_coil_spin)
        form.addRow(QLabel("Overall Result:"),   self.result_reg_spin)
        form.addRow(QLabel("OK Count Reg:"),     self.ok_reg_spin)
        form.addRow(QLabel("NG Count Reg:"),     self.ng_reg_spin)
        form.addRow(QLabel("Heartbeat Reg:"),    self.heartbeat_spin)

        layout.addLayout(form)
        return grp

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_profile(self) -> None:
        """Populate all widgets from the stored PLC profile."""
        try:
            profile: dict = self._app_state.profile_repo.get_profile()
        except Exception as exc:
            logger.error("Failed to load PLC profile: %s", exc)
            return

        # Brand
        brand_key = profile.get("brand", PLC_BRANDS[0])
        idx = self.brand_combo.findData(brand_key)
        if idx >= 0:
            self.brand_combo.setCurrentIndex(idx)

        # Protocol
        self.protocol_combo.setCurrentText(
            profile.get("protocol", PLC_PROTOCOL_TCP)
        )

        # TCP
        self.host_field.setText(profile.get("host", "127.0.0.1"))
        self.port_spin.setValue(profile.get("port", 502))
        self.slave_spin.setValue(profile.get("slave_id", 1))

        # RTU
        self.com_field.setText(profile.get("com_port", "COM1"))
        baud_idx = self.baud_combo.findData(profile.get("baud_rate", 9600))
        if baud_idx >= 0:
            self.baud_combo.setCurrentIndex(baud_idx)

        # Timing
        self.poll_spin.setValue(profile.get("poll_interval_ms", 500))
        self.timeout_spin.setValue(profile.get("timeout_sec", 3))

        # Key registers
        self.state_reg_spin.setValue(
            profile.get("state_register", DEFAULT_STATE_REGISTER)
        )
        self.start_coil_spin.setValue(
            profile.get("start_coil", DEFAULT_START_COIL)
        )
        self.result_reg_spin.setValue(
            profile.get("overall_result_register", DEFAULT_OVERALL_RESULT_REGISTER)
        )
        self.ok_reg_spin.setValue(
            profile.get("ok_count_register", DEFAULT_OK_COUNT_REGISTER)
        )
        self.ng_reg_spin.setValue(
            profile.get("ng_count_register", DEFAULT_NG_COUNT_REGISTER)
        )
        self.heartbeat_spin.setValue(profile.get("heartbeat_register", 0))

        # Trigger visibility
        self._on_protocol_changed(self.protocol_combo.currentText())

    def _on_save(self) -> None:
        """Validate and persist the profile then close."""
        protocol = self.protocol_combo.currentText()

        # Validate TCP fields when TCP
        if protocol == PLC_PROTOCOL_TCP:
            host = self.host_field.text().strip()
            if not validate_ip(host):
                self._show_result(False, "Invalid IP address.")
                return
            if not validate_port(self.port_spin.value()):
                self._show_result(False, "Invalid port number.")
                return

        brand_key = self.brand_combo.currentData()

        kwargs = dict(
            brand=brand_key,
            protocol=protocol,
            host=self.host_field.text().strip(),
            port=self.port_spin.value(),
            slave_id=self.slave_spin.value(),
            com_port=self.com_field.text().strip(),
            baud_rate=self.baud_combo.currentData(),
            poll_interval_ms=self.poll_spin.value(),
            timeout_sec=self.timeout_spin.value(),
            state_register=self.state_reg_spin.value(),
            start_coil=self.start_coil_spin.value(),
            overall_result_register=self.result_reg_spin.value(),
            ok_count_register=self.ok_reg_spin.value(),
            ng_count_register=self.ng_reg_spin.value(),
            heartbeat_register=self.heartbeat_spin.value(),
        )

        try:
            self._app_state.profile_repo.update_profile(**kwargs)
            updated = self._app_state.profile_repo.get_profile()
            self._app_state.set_plc_profile(updated)

            username = (
                self._app_state.current_user.get("username", "unknown")
                if self._app_state.current_user else "unknown"
            )
            logger.info("PLC profile updated by %s", username)
            self.accept()
        except Exception as exc:
            logger.error("Failed to save PLC profile: %s", exc)
            QMessageBox.critical(self, "Save Error", str(exc))

    # ------------------------------------------------------------------
    # Protocol toggle
    # ------------------------------------------------------------------

    def _on_protocol_changed(self, protocol: str) -> None:
        is_rtu = protocol == PLC_PROTOCOL_RTU
        self.tcp_group.setVisible(not is_rtu)
        self.rtu_group.setVisible(is_rtu)

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def _on_test_connection(self) -> None:
        """Start the background connection tester."""
        if self._tester and self._tester.isRunning():
            return

        self.test_btn.setEnabled(False)
        self.result_lbl.setText("Testing…")
        self.result_lbl.setStyleSheet("color: #d4890a; font-weight: 600;")
        self.result_lbl.show()

        params = {
            "protocol": self.protocol_combo.currentText(),
            "host": self.host_field.text().strip(),
            "port": self.port_spin.value(),
            "com_port": self.com_field.text().strip(),
        }
        self._tester = _ConnectionTester(params, parent=self)
        self._tester.result.connect(self._on_test_result)
        self._tester.finished.connect(lambda: self.test_btn.setEnabled(True))
        self._tester.start()

    def _on_test_result(self, success: bool, message: str) -> None:
        self._show_result(success, message)

    def _show_result(self, success: bool, message: str) -> None:
        colour = "#1a6b3a" if success else "#c0392b"
        self.result_lbl.setStyleSheet(f"color: {colour}; font-weight: 600;")
        self.result_lbl.setText(message)
        self.result_lbl.show()
