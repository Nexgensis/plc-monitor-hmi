# src/ui/components/plc_config_panel.py
"""
PLCConfigPanel — "Connection" tab (Tab 4) inside SettingsWindow.

Shows a summary of the current PLC profile with an "Edit PLC Profile"
button that opens PLCProfileDialog, a quick connection test, and a
live status display.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QFormLayout,
)
from PyQt6.QtCore import QThread, pyqtSignal

from src.ui.app_state import AppState
from src.utils.constants import PLC_BRAND_LABELS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight connection tester thread
# ---------------------------------------------------------------------------

class _QuickTester(QThread):
    """Tests TCP socket reachability in a background thread."""

    test_passed = pyqtSignal(str)   # heartbeat / success message
    test_failed = pyqtSignal(str)   # error message

    def __init__(self, host: str, port: int,
                 slave_id: int, timeout_sec: int,
                 parent=None) -> None:
        super().__init__(parent)
        self._host       = host
        self._port       = port
        self._slave_id   = slave_id
        self._timeout    = timeout_sec

    def run(self) -> None:  # noqa: D401
        try:
            import socket
            with socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            ):
                pass
            self.test_passed.emit(
                f"Connected to {self._host}:{self._port} ✓"
            )
        except Exception as exc:
            self.test_failed.emit(str(exc))


# ---------------------------------------------------------------------------
# PLCConfigPanel
# ---------------------------------------------------------------------------

class PLCConfigPanel(QWidget):
    """
    Connection tab — displays PLC profile summary, edit button,
    quick test, and live status.

    Signals
    -------
    config_saved(dict)
        Emitted after the PLCProfileDialog is accepted and profile saved.
    """

    config_saved = pyqtSignal(dict)

    def __init__(self, app_state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._tester: Optional[_QuickTester] = None

        self._setup_ui()
        self.refresh_from_profile()

    # ==================================================================
    # UI Construction
    # ==================================================================

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # Info banner
        info_lbl = QLabel(
            "Changes take effect after reconnecting.  "
            "Brand and protocol changes require an app restart."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setObjectName("config_info_banner")
        root.addWidget(info_lbl)

        # Profile summary card
        self.summary_grp = QGroupBox("Current PLC Profile")
        summary_layout = QVBoxLayout(self.summary_grp)
        summary_layout.setSpacing(4)

        self.brand_proto_lbl = QLabel("—")
        self.brand_proto_lbl.setObjectName("config_brand_proto_lbl")

        self.host_port_lbl = QLabel("—")
        self.host_port_lbl.setObjectName("config_host_port_lbl")

        self.btn_edit = QPushButton("Edit PLC Profile")
        self.btn_edit.setObjectName("btn_primary")
        self.btn_edit.setFixedWidth(180)
        self.btn_edit.clicked.connect(self._on_edit_profile)

        summary_layout.addWidget(self.brand_proto_lbl)
        summary_layout.addWidget(self.host_port_lbl)
        summary_layout.addSpacing(4)
        summary_layout.addWidget(self.btn_edit)
        root.addWidget(self.summary_grp)

        # Connection test group
        test_grp = QGroupBox("Connection Test")
        test_layout = QHBoxLayout(test_grp)

        self.btn_test = QPushButton("Test Connection Now")
        self.btn_test.setObjectName("btn_secondary")
        self.btn_test.clicked.connect(self._on_test_connection)

        self.test_result_lbl = QLabel()
        self.test_result_lbl.setWordWrap(True)
        self.test_result_lbl.setObjectName("config_test_result_lbl")
        self.test_result_lbl.hide()

        test_layout.addWidget(self.btn_test)
        test_layout.addWidget(self.test_result_lbl, stretch=1)
        root.addWidget(test_grp)

        # Status group
        status_grp = QGroupBox("Current Status")
        form = QFormLayout(status_grp)
        form.setSpacing(6)

        self.poll_lbl      = QLabel("—")
        self.timeout_lbl   = QLabel("—")
        self.state_reg_lbl = QLabel("—")
        self.start_coil_lbl = QLabel("—")
        self.connected_lbl  = QLabel("● Disconnected")
        self.connected_lbl.setObjectName("config_connected_lbl")
        self.connected_lbl.setProperty("connected", False)

        form.addRow(QLabel("Poll Interval:"),  self.poll_lbl)
        form.addRow(QLabel("Timeout:"),        self.timeout_lbl)
        form.addRow(QLabel("State Register:"), self.state_reg_lbl)
        form.addRow(QLabel("Start Coil:"),     self.start_coil_lbl)
        form.addRow(QLabel("Connection:"),     self.connected_lbl)

        root.addWidget(status_grp)
        root.addStretch()

    # ==================================================================
    # Public API
    # ==================================================================

    def refresh_from_profile(self) -> None:
        """Refresh all display labels from the stored PLC profile."""
        try:
            profile: dict = (
                self._app_state.plc_profile
                or self._app_state.profile_repo.get_profile()
            )
        except Exception as exc:
            logger.warning("PLCConfigPanel: could not load profile — %s", exc)
            return

        brand_key = profile.get("brand", "mitsubishi")
        brand_lbl = PLC_BRAND_LABELS.get(brand_key, brand_key)
        proto     = profile.get("protocol", "—")

        self.brand_proto_lbl.setText(f"{brand_lbl}  ·  {proto}")
        self.host_port_lbl.setText(
            f"Host: {profile.get('host', '—')}:{profile.get('port', '—')}"
            f"  |  Slave ID: {profile.get('slave_id', '—')}"
        )
        self.poll_lbl.setText(f"{profile.get('poll_interval_ms', '—')} ms")
        self.timeout_lbl.setText(f"{profile.get('timeout_sec', '—')} s")
        self.state_reg_lbl.setText(f"D{profile.get('state_register', '—')}")
        self.start_coil_lbl.setText(f"M{profile.get('start_coil', '—')}")

        # Reflect current connection state
        connected = self._app_state.is_plc_connected
        self._set_connected_label(connected)

    # ==================================================================
    # Slots
    # ==================================================================

    def _on_edit_profile(self) -> None:
        from src.ui.dialogs.plc_profile_dialog import PLCProfileDialog
        dlg = PLCProfileDialog(self._app_state, parent=self)
        if dlg.exec():
            self.refresh_from_profile()
            profile = self._app_state.plc_profile or {}
            self.config_saved.emit(profile)
            logger.info("PLCConfigPanel: PLC profile edited and saved")

    def _on_test_connection(self) -> None:
        if self._tester and self._tester.isRunning():
            return

        try:
            profile: dict = (
                self._app_state.plc_profile
                or self._app_state.profile_repo.get_profile()
            )
        except Exception as exc:
            self._show_test_result(False, f"Cannot read profile: {exc}")
            return

        if profile.get("protocol", "TCP") != "TCP":
            self._show_test_result(
                False,
                "Auto-test only supported for TCP connections. "
                "Use 'Edit PLC Profile' to verify RTU settings."
            )
            return

        self.btn_test.setEnabled(False)
        self.test_result_lbl.setText("Testing…")
        self.test_result_lbl.setProperty("status", "testing")
        self.test_result_lbl.style().unpolish(self.test_result_lbl)
        self.test_result_lbl.style().polish(self.test_result_lbl)
        self.test_result_lbl.show()

        self._tester = _QuickTester(
            host        = profile.get("host", "127.0.0.1"),
            port        = profile.get("port", 502),
            slave_id    = profile.get("slave_id", 1),
            timeout_sec = profile.get("timeout_sec", 3),
            parent      = self,
        )
        self._tester.test_passed.connect(
            lambda msg: self._show_test_result(True, msg)
        )
        self._tester.test_failed.connect(
            lambda err: self._show_test_result(False, f"Failed ✗ — {err}")
        )
        self._tester.finished.connect(
            lambda: self.btn_test.setEnabled(True)
        )
        self._tester.start()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _show_test_result(self, success: bool, msg: str) -> None:
        self.test_result_lbl.setText(msg)
        self.test_result_lbl.setProperty("status", "pass" if success else "fail")
        self.test_result_lbl.style().unpolish(self.test_result_lbl)
        self.test_result_lbl.style().polish(self.test_result_lbl)
        self.test_result_lbl.show()

    def _set_connected_label(self, connected: bool) -> None:
        if connected:
            self.connected_lbl.setText("● Connected")
        else:
            self.connected_lbl.setText("● Disconnected")
        self.connected_lbl.setProperty("connected", connected)
        self.connected_lbl.style().unpolish(self.connected_lbl)
        self.connected_lbl.style().polish(self.connected_lbl)
