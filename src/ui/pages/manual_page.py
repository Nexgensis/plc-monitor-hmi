"""
manual_page.py — Universal PLC Monitor
Manual control panel for triggering specific PLC actions and 
monitoring live register values.
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QScrollArea)
from PyQt6.QtCore import QTimer

from src.ui.app_state import AppState
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.utils.constants import (
    CTRL_START_TEST, CTRL_STOP_TEST
)

logger = logging.getLogger(__name__)


class ManualPage(QWidget):
    """
    Control interface for maintenance and manual machine operation.
    All manual actions are recorded in the audit trail.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.setAccessibleName("Manual control page")
        self.app_state = app_state
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._refresh_live_table)
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 1. Header
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title = QLabel("MANUAL OPERATION")
        title.setObjectName("manual_page_title")
        title_v.addWidget(title)
        
        self.plc_status_lbl = QLabel("PLC: Disconnected")
        self.plc_status_lbl.setObjectName("manual_plc_status")
        title_v.addWidget(self.plc_status_lbl)
        header.addLayout(title_v)
        
        header.addStretch()
        
        btn_refresh = QPushButton("🔄 Force Refresh")
        btn_refresh.setObjectName("btn_secondary")
        btn_refresh.setAccessibleName("Force refresh")
        btn_refresh.setToolTip("Force refresh of register values from PLC")
        btn_refresh.clicked.connect(self._refresh_live_table)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        # 2. Main Content Split
        content = QHBoxLayout()
        content.setSpacing(15)
        layout.addLayout(content, 1)

        # LEFT: Control Panel
        ctrl_frame = QFrame()
        ctrl_frame.setFixedWidth(300)
        ctrl_frame.setObjectName("manual_ctrl_frame")
        ctrl_layout = QVBoxLayout(ctrl_frame)
        
        lbl_ctrl = QLabel("CONTROL COMMANDS")
        lbl_ctrl.setObjectName("manual_ctrl_label")
        ctrl_layout.addWidget(lbl_ctrl)

        # Scroll area for many buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("manual_scroll")
        self.btn_container = QWidget()
        self.btn_vbox = QVBoxLayout(self.btn_container)
        self.btn_vbox.setContentsMargins(0, 0, 0, 0)
        self.btn_vbox.setSpacing(8)
        scroll.setWidget(self.btn_container)
        ctrl_layout.addWidget(scroll)
        
        ctrl_layout.addStretch()
        lbl_audit = QLabel("⚠ All manual writes are logged to audit trail.")
        lbl_audit.setObjectName("manual_audit_label")
        lbl_audit.setWordWrap(True)
        ctrl_layout.addWidget(lbl_audit)
        
        content.addWidget(ctrl_frame)

        # RIGHT: Live Value Table
        live_frame = QFrame()
        live_frame.setObjectName("manual_live_frame")
        live_layout = QVBoxLayout(live_frame)
        
        live_header = QHBoxLayout()
        lbl_live = QLabel("LIVE REGISTER MONITOR")
        lbl_live.setObjectName("manual_live_label")
        live_header.addWidget(lbl_live)
        
        live_header.addStretch()
        
        self.model_filter = QComboBox()
        self.model_filter.setFixedWidth(180)
        self.model_filter.setAccessibleName("Filter by model")
        self.model_filter.setToolTip("Filter registers by product model")
        self.model_filter.currentIndexChanged.connect(self._on_filter_changed)
        live_header.addWidget(self.model_filter)
        live_layout.addLayout(live_header)

        self.live_table = QTableWidget(0, 6)
        self.live_table.setHorizontalHeaderLabels(["Name", "Address", "Type", "Raw", "Display", "Unit"])
        self.live_table.setAccessibleName("Live register values")
        self.live_table.setToolTip("Shows current register values read from the PLC")
        self.live_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.live_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.live_table.setAlternatingRowColors(True)
        self.live_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        live_layout.addWidget(self.live_table)
        
        content.addWidget(live_frame, 1)

    def on_page_shown(self) -> None:
        """Called when page becomes visible."""
        self._refresh_controls()
        self._refresh_filters()
        self._refresh_live_table()
        self._live_timer.start(250)
        
        self.on_plc_state_changed(self.app_state.is_plc_connected)

    def on_page_hidden(self) -> None:
        self._live_timer.stop()

    def hideEvent(self, event) -> None:
        self.on_page_hidden()
        super().hideEvent(event)

    def on_plc_state_changed(self, connected: bool) -> None:
        status = "✓ PLC Online" if connected else "● PLC Offline"
        self.plc_status_lbl.setText(status)
        if connected:
            self.plc_status_lbl.setProperty("status", "connected")
        else:
            self.plc_status_lbl.setProperty("status", "disconnected")
        self.plc_status_lbl.style().unpolish(self.plc_status_lbl)
        self.plc_status_lbl.style().polish(self.plc_status_lbl)
        
        # Disable buttons if offline
        for i in range(self.btn_vbox.count()):
            w = self.btn_vbox.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setEnabled(connected)

    def _refresh_controls(self) -> None:
        """Build buttons for all configured controls in DB."""
        while self.btn_vbox.count():
            item = self.btn_vbox.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
                
        controls = self.app_state.control_repo.get_all_controls()
        for ctrl in controls:
            btn = QPushButton(ctrl["name"])
            
            # Styling based on type
            if ctrl["control_type"] == CTRL_START_TEST:
                btn.setObjectName("btn_success")
            elif ctrl["control_type"] == CTRL_STOP_TEST:
                btn.setObjectName("btn_danger")
            else:
                btn.setObjectName("btn_secondary")
                
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, c=ctrl: self._execute_control(c))
            self.btn_vbox.addWidget(btn)

    def _refresh_filters(self) -> None:
        """Fill combobox with models."""
        self.model_filter.blockSignals(True)
        self.model_filter.clear()
        self.model_filter.addItem("Current Model Only", 0)
        self.model_filter.addItem("Show All Mapped", -1)
        
        models = self.app_state.model_repo.get_all_models()
        for m in models:
            self.model_filter.addItem(m["name"], m["id"])
            
        # Select current model if set
        if self.app_state.current_model_id:
            idx = self.model_filter.findData(self.app_state.current_model_id)
            if idx >= 0:
                self.model_filter.setCurrentIndex(idx)
        self.model_filter.blockSignals(False)

    def _on_filter_changed(self) -> None:
        self._refresh_live_table()

    def _refresh_live_table(self) -> None:
        """Updates live readings for filtered registers."""
        if not self.app_state.connection_manager:
            return
            
        model_id_filter = self.model_filter.currentData()
        
        # Get target registers
        if model_id_filter == 0: # Current
            regs = self.app_state.map_repo.get_model_mappings(self.app_state.current_model_id, enabled_only=True)
        elif model_id_filter == -1: # All mapped — aggregate from all models
            all_models = self.app_state.model_repo.get_all_models()
            seen = set()
            regs = []
            for m in all_models:
                for r in self.app_state.map_repo.get_model_mappings(m["id"], enabled_only=True):
                    rid = r.get("register_id")
                    if rid and rid not in seen:
                        seen.add(rid)
                        regs.append(r)
        else:
            regs = self.app_state.map_repo.get_model_mappings(model_id_filter, enabled_only=True)

        self.live_table.setRowCount(len(regs))
        data_model = self.app_state.connection_manager.data_model
        
        for i, r in enumerate(regs):
            self.live_table.setItem(i, 0, QTableWidgetItem(r["display_name"]))
            self.live_table.setItem(i, 1, QTableWidgetItem(self._format_address(r)))
            self.live_table.setItem(i, 2, QTableWidgetItem(r["register_type"]))
            
            reading = data_model.get_reading(r["register_id"])
            if reading:
                self.live_table.setItem(i, 3, QTableWidgetItem(str(reading.raw_words[0] if reading.raw_words else 0)))
                self.live_table.setItem(i, 4, QTableWidgetItem(reading.display_str))
                self.live_table.setItem(i, 5, QTableWidgetItem(r["unit"]))
            else:
                self.live_table.setItem(i, 3, QTableWidgetItem("---"))
                self.live_table.setItem(i, 4, QTableWidgetItem("PENDING"))
                self.live_table.setItem(i, 5, QTableWidgetItem(r["unit"]))

    def _format_address(self, reg: dict) -> str:
        prefix_by_type = {
            "HOLDING": "D",
            "COIL": "M",
            "DISCRETE": "X",
            "INPUT": "AI",
        }
        prefix = prefix_by_type.get(reg.get("register_type"), "")
        return f"{prefix}{reg['register_address']}"

    def _execute_control(self, control: dict) -> None:
        from PyQt6.QtWidgets import QMessageBox
        
        if control.get("confirm_required"):
            if not ConfirmDialog.ask(self, "Manual Operation", f"Trigger manual action: {control['name']}?"):
                return
        
        if self.app_state.write_manager:
            user_id = self.app_state.current_user["id"] if self.app_state.current_user else None
            if not user_id:
                QMessageBox.warning(self, "Auth Error", "No user logged in.")
                return
            logger.info("Manual page executing control %s", control["name"])
            try:
                self.app_state.write_manager.execute_control(control, user_id)
                QMessageBox.information(self, "Write Success", f"Control '{control['name']}' executed successfully.")
            except Exception as e:
                logger.error("Manual write failed: %s", e)
                QMessageBox.critical(self, "Write Failed", f"Failed to execute '{control['name']}':\n{e}")
        else:
            QMessageBox.warning(self, "Write Manager Offline", "PLC write manager is not available.")
