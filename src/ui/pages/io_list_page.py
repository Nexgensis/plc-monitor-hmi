"""
io_list_page.py — Universal PLC Monitor
Diagnostic I/O status screen. Shows grouped inputs/outputs 
from the io_list_config table.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTabWidget, QTableWidget, QFrame,
                             QTableWidgetItem, QHeaderView, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from src.ui.app_state import AppState
from src.plc.data_model import RegisterReading
from src.utils.constants import IO_LIST_REFRESH_MS, PAGE_CONFIG

logger = logging.getLogger(__name__)


class IoListPage(QWidget):
    """
    Data-driven I/O status page. Automatically builds tabs based 
    on configured group names.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_data)
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Header
        header = QHBoxLayout()
        title = QLabel("I/O STATUS MONITOR")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #3b82f6;")
        header.addWidget(title)
        
        header.addStretch()
        
        self.last_refresh_lbl = QLabel("Updated: --:--:--")
        self.last_refresh_lbl.setStyleSheet("font-size: 11px; color: #5a7a9a;")
        header.addWidget(self.last_refresh_lbl)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setObjectName("btn_secondary")
        btn_refresh.clicked.connect(self._refresh_data)
        header.addWidget(btn_refresh)
        
        self.auto_lbl = QLabel("Auto: ON")
        self.auto_lbl.setStyleSheet("font-size: 10px; color: #22c55e; font-weight: bold; margin-left: 10px;")
        header.addWidget(self.auto_lbl)
        layout.addLayout(header)

        # 2. No Config Warning
        self.no_io_card = QFrame()
        self.no_io_card.setStyleSheet("background: #0f172a; border-radius: 8px; border: 1px dashed #1e2d4a;")
        no_io_layout = QVBoxLayout(self.no_io_card)
        no_io_layout.setContentsMargins(40, 40, 40, 40)
        
        msg = QLabel("No I/O points are configured for diagnostics.\nGo to CONFIG → I/O List to define monitoring points.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size: 13px; color: #5a7a9a;")
        no_io_layout.addWidget(msg)
        
        btn_go = QPushButton("Go to Configuration")
        btn_go.setObjectName("btn_warning")
        btn_go.setFixedWidth(200)
        btn_go.clicked.connect(self._navigate_to_config)
        no_io_layout.addWidget(btn_go, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.no_io_card.setVisible(False)
        layout.addWidget(self.no_io_card)

        # 3. Group Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # 4. Footer
        footer = QHBoxLayout()
        self.poll_info = QLabel("Ready")
        self.poll_info.setStyleSheet("font-size: 10px; color: #5a7a9a;")
        footer.addWidget(self.poll_info)
        layout.addLayout(footer)

    def on_page_shown(self) -> None:
        """Rebuild tabs and start timer."""
        self._build_tabs()
        self._refresh_timer.start(IO_LIST_REFRESH_MS)
        self._refresh_data()

    def on_page_hidden(self) -> None:
        self._refresh_timer.stop()

    def hideEvent(self, event) -> None:
        self.on_page_hidden()
        super().hideEvent(event)

    def _navigate_to_config(self) -> None:
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(PAGE_CONFIG)

    def _build_tabs(self) -> None:
        """Fetch groups and build tables."""
        self.tabs.clear()
        groups = self.app_state.io_repo.get_groups()
        
        if not groups:
            # Check if there are any entries at all
            all_entries = self.app_state.io_repo.get_all_entries()
            if not all_entries:
                self.no_io_card.setVisible(True)
                self.tabs.setVisible(False)
                return
            groups = [None] # Use a single tab for ungrouped entries
            
        self.no_io_card.setVisible(False)
        self.tabs.setVisible(True)

        for group_name in groups:
            entries = self.app_state.io_repo.get_all_entries(group_name)
            table = self._create_group_table(entries)
            self.tabs.addTab(table, group_name or "General I/O")
        
        self.poll_info.setText(f"Monitoring {len(self.app_state.io_repo.get_all_entries())} I/O points | Poll: {IO_LIST_REFRESH_MS}ms")

    def _create_group_table(self, entries: List[Dict[str, Any]]) -> QTableWidget:
        table = QTableWidget(len(entries), 6)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        
        headers = ["#", "Name", "Register", "Address", "Status", "Value"]
        table.setHorizontalHeaderLabels(headers)
        
        # Exact column widths from spec
        table.setColumnWidth(0, 30)
        table.setColumnWidth(1, 200)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 80)
        table.setColumnWidth(4, 80)
        table.setColumnWidth(5, 80)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for i, entry in enumerate(entries):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(entry["display_name"]))
            table.setItem(i, 2, QTableWidgetItem(entry["name"])) # Library name
            table.setItem(i, 3, QTableWidgetItem(f"D{entry['register_address']}"))
            
            # Status Indicator (using specific labels/colors from config)
            status_item = QTableWidgetItem("○")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            status_item.setForeground(QColor(entry["off_color"]))
            table.setItem(i, 4, status_item)
            
            # Numeric value cell
            val_item = QTableWidgetItem("---")
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(i, 5, val_item)
            
            # Store config in status item for updates
            status_item.setData(Qt.ItemDataRole.UserRole, entry)

        return table

    def _refresh_data(self) -> None:
        """Update only the visible tab to minimize CPU load."""
        if not self.app_state.is_plc_connected or not self.app_state.connection_manager:
            self.last_refresh_lbl.setText("PLC Disconnected")
            return
            
        current_table = self.tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return
            
        data_model = self.app_state.connection_manager.data_model
        
        for row in range(current_table.rowCount()):
            status_item = current_table.item(row, 4)
            val_item = current_table.item(row, 5)
            entry = status_item.data(Qt.ItemDataRole.UserRole)
            
            reading = data_model.get_reading(entry["register_id"])
            if reading:
                self._update_row_ui(status_item, val_item, entry, reading)
            else:
                status_item.setText("?")
                val_item.setText("---")

        self.last_refresh_lbl.setText(f"Updated: {datetime.now():%H:%M:%S}")

    def _update_row_ui(self, status_item: QTableWidgetItem, val_item: QTableWidgetItem, 
                        entry: dict, reading: RegisterReading) -> None:
        # Determine ON/OFF (anything non-zero is ON for binary diagnostics)
        is_on = reading.display_value != 0
        
        color = entry["on_color"] if is_on else entry["off_color"]
        label = entry["on_label"] if is_on else entry["off_label"]
        
        status_item.setText("●" if is_on else "○")
        status_item.setForeground(QColor(color))
        status_item.setToolTip(f"State: {label}")
        
        if entry.get("show_value"):
            val_item.setText(reading.display_str)
        else:
            val_item.setText("-")
            
from PyQt6.QtGui import QFont
