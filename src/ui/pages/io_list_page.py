"""
io_list_page.py — Universal PLC Monitor
Diagnostic I/O status screen. Shows grouped inputs/outputs
from the io_list_config table, plus live Register Block viewers
(batched address ranges) merged in as tabs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Any

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTabWidget, QTableWidget, QFrame,
                             QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from src.ui.app_state import AppState
from src.ui.dialogs.block_write_dialog import BlockWriteDialog
from src.plc.data_model import RegisterReading
from src.utils.validators import format_value, get_register_count
from src.utils.constants import (IO_LIST_REFRESH_MS, PAGE_CONFIG,
                                 ACCESS_READ_WRITE, REG_TYPE_COIL,
                                 REG_TYPE_HOLDING, ROLE_ADMIN,
                                 ROLE_SUPERVISOR, DARK_PASS,
                                 DARK_TEXT_MUTED)

logger = logging.getLogger(__name__)


class IoListPage(QWidget):
    """
    Data-driven I/O status page. Automatically builds tabs based 
    on configured group names.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.setAccessibleName("I/O list monitoring page")
        self.app_state = app_state
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_data)
        # Block viewer registry: container widget -> (block_row, table)
        self._block_view: Dict[QWidget, tuple] = {}
        # Write-manager instance we currently listen to for toasts
        self._bound_write_mgr = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Header
        header = QHBoxLayout()
        title = QLabel("I/O STATUS MONITOR")
        title.setObjectName("io_page_title")
        header.addWidget(title)
        
        header.addStretch()
        
        self.last_refresh_lbl = QLabel("Updated: --:--:--")
        self.last_refresh_lbl.setObjectName("io_last_refresh")
        header.addWidget(self.last_refresh_lbl)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setObjectName("btn_secondary")
        btn_refresh.clicked.connect(self._refresh_data)
        header.addWidget(btn_refresh)
        
        self.auto_btn = QPushButton("Auto: ON")
        self.auto_btn.setObjectName("btn_secondary")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(True)
        self.auto_btn.setAccessibleName("Toggle auto-refresh")
        self.auto_btn.setToolTip("Toggle automatic I/O list refresh")
        self.auto_btn.clicked.connect(self._toggle_auto_refresh)
        header.addWidget(self.auto_btn)
        layout.addLayout(header)

        # 2. No Config Warning
        self.no_io_card = QFrame()
        self.no_io_card.setObjectName("io_no_card")
        no_io_layout = QVBoxLayout(self.no_io_card)
        no_io_layout.setContentsMargins(40, 40, 40, 40)
        
        msg = QLabel("No I/O points are configured for diagnostics.\n"
                     "Go to CONFIG → I/O List to define monitoring points.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setObjectName("io_no_msg")
        no_io_layout.addWidget(msg)
        
        btn_go = QPushButton("Go to Configuration")
        btn_go.setObjectName("btn_warning")
        btn_go.setFixedWidth(200)
        btn_go.setAccessibleName("Go to configuration")
        btn_go.setToolTip("Navigate to I/O configuration page")
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
        self.poll_info.setObjectName("io_poll_info")
        footer.addWidget(self.poll_info)
        layout.addLayout(footer)

    def on_page_shown(self) -> None:
        """Rebuild tabs and start timer if PLC is connected."""
        self._build_tabs()
        if self.app_state.is_plc_connected and self.auto_btn.isChecked():
            self._refresh_timer.start(IO_LIST_REFRESH_MS)
        self._refresh_data()

    def on_page_hidden(self) -> None:
        self._refresh_timer.stop()

    def hideEvent(self, event) -> None:
        self.on_page_hidden()
        super().hideEvent(event)

    def _toggle_auto_refresh(self, checked: bool) -> None:
        if checked:
            self.auto_btn.setText("Auto: ON")
            if self.app_state.is_plc_connected:
                self._refresh_timer.start(IO_LIST_REFRESH_MS)
        else:
            self.auto_btn.setText("Auto: OFF")
            self._refresh_timer.stop()

    def _navigate_to_config(self) -> None:
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(PAGE_CONFIG)

    def _build_tabs(self) -> None:
        """Fetch I/O groups and register blocks, then build tab tables."""
        self.tabs.clear()
        self._block_view.clear()
        groups = self.app_state.io_repo.get_groups()
        all_entries = self.app_state.io_repo.get_all_entries()
        block_rows = self._get_active_blocks()

        if not groups and not all_entries and not block_rows:
            # Nothing configured at all — same empty state as before
            self.no_io_card.setVisible(True)
            self.tabs.setVisible(False)
            return

        if not groups and all_entries:
            groups = [None]  # Use a single tab for ungrouped entries

        self.no_io_card.setVisible(False)
        self.tabs.setVisible(True)

        for group_name in groups:
            entries = self.app_state.io_repo.get_all_entries(group_name)
            table = self._create_group_table(entries)
            self.tabs.addTab(table, group_name or "General I/O")

        # Register Block viewer tabs (merged into this page)
        for blk in block_rows:
            container = self._create_block_view(blk)
            self.tabs.addTab(container, blk["name"])
            rng = f"{blk['start_address']}..{blk['start_address'] + blk['count'] - 1}"
            self.tabs.setTabToolTip(
                self.tabs.indexOf(container),
                f"{blk['register_type']} {rng} | group: {blk.get('group_name') or '-'}",
            )

        parts = []
        if all_entries:
            parts.append(f"Monitoring {len(all_entries)} I/O points")
        if block_rows:
            parts.append(f"{len(block_rows)} blocks")
        parts.append(f"Poll: {IO_LIST_REFRESH_MS}ms")
        self.poll_info.setText(" | ".join(parts))

    def _get_active_blocks(self) -> List[Dict[str, Any]]:
        """Active register blocks for the viewer (repo may be unbound)."""
        if not self.app_state.block_repo:
            return []
        try:
            return self.app_state.block_repo.get_all_blocks(active_only=True)
        except Exception as exc:
            logger.warning("Failed to load register blocks: %s", exc)
            return []

    def _create_group_table(self, entries: List[Dict[str, Any]]) -> QTableWidget:
        table = QTableWidget(len(entries), 6)
        table.setAlternatingRowColors(True)
        table.setAccessibleName("I/O status list")
        table.setToolTip("Shows current digital input/output states")
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
            
            # LED-style status indicator (cell widget with glowing dot)
            led, status_lbl = self._make_status_cell()
            table.setCellWidget(i, 4, led)
            
            # Numeric value cell
            val_item = QTableWidgetItem("---")
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            val_item.setFont(QFont("Consolas", 11))
            table.setItem(i, 5, val_item)
            
            # Store config for updates (referenced via the LED dot objectName)
            led.setProperty("entry", entry)
            led.setProperty("row", i)

        return table

    # ------------------------------------------------------------------
    # Register Block viewer tabs
    # ------------------------------------------------------------------
    def _create_block_view(self, block: Dict[str, Any]) -> QWidget:
        """
        Builds the viewer for one register block: info header (+ write
        button when allowed) over a value grid (one row per element for
        word blocks, one row per bit for bit blocks).
        """
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(6)

        start = int(block["start_address"])
        count = int(block["count"])
        reg_type = block["register_type"]
        is_bit = reg_type == REG_TYPE_COIL
        end = start + count - 1

        head = QHBoxLayout()
        info = QLabel(
            f"{reg_type} {start}..{end} · {count} "
            f"{'bits' if is_bit else 'words'} · {block['data_type']}"
            + (f" · {block['unit']}" if block.get("unit") else "")
        )
        info.setObjectName("io_last_refresh")
        head.addWidget(info)
        head.addStretch()

        writable = (
            block.get("access") == ACCESS_READ_WRITE
            and reg_type in (REG_TYPE_HOLDING, REG_TYPE_COIL)
        )
        if writable:
            write_btn = QPushButton("✏ Write to PLC")
            write_btn.setObjectName("btn_danger")
            write_btn.setAccessibleName(f"Write block {block['name']}")
            if not self._can_write_blocks():
                write_btn.setEnabled(False)
                write_btn.setToolTip("Requires ADMIN or SUPERVISOR role")
            else:
                write_btn.setToolTip(
                    f"Write {count} values to {reg_type} {start}..{end} "
                    "with read-back verification"
                )
            write_btn.clicked.connect(lambda _=False, b=block: self._on_write_block(b))
            head.addWidget(write_btn)
        v.addLayout(head)

        stride = get_register_count(block["data_type"])
        rows = count if is_bit else max(1, count // max(stride, 1))
        table = QTableWidget(rows, 4)
        table.setAlternatingRowColors(True)
        table.setAccessibleName(f"Block viewer {block['name']}")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setHorizontalHeaderLabels(
            ["#", "Address", "Raw", "State" if is_bit else "Value"]
        )
        table.setColumnWidth(0, 45)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 110)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for i in range(rows):
            table.setItem(i, 0, QTableWidgetItem(str(i)))
            addr = start + i if is_bit else start + i * stride
            addr_item = QTableWidgetItem(str(addr))
            addr_item.setFont(QFont("Consolas", 10))
            table.setItem(i, 1, addr_item)

            raw_item = QTableWidgetItem("---")
            raw_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            raw_item.setFont(QFont("Consolas", 10))
            table.setItem(i, 2, raw_item)

            val_item = QTableWidgetItem("---")
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(i, 3, val_item)

        v.addWidget(table, 1)
        self._block_view[container] = (block, table)
        return container

    def _can_write_blocks(self) -> bool:
        """Block writes are gated to ADMIN and SUPERVISOR."""
        user = self.app_state.current_user or {}
        return str(user.get("role", "")).upper() in (ROLE_ADMIN, ROLE_SUPERVISOR)

    # ------------------------------------------------------------------
    # Block write flow
    # ------------------------------------------------------------------
    def _on_write_block(self, block: Dict[str, Any]) -> None:
        if not self._can_write_blocks():
            QMessageBox.warning(self, "Access Denied",
                                "Block writes require ADMIN or SUPERVISOR role.")
            return
        mgr = self.app_state.write_manager
        if mgr is None:
            QMessageBox.warning(self, "PLC Not Connected",
                                "Connect to the PLC before writing.")
            return

        count = int(block["count"])
        initial: list = [0] * count
        if self.app_state.is_plc_connected and self.app_state.connection_manager:
            reading = self.app_state.connection_manager.data_model.get_block_reading(
                block["id"]
            )
            if reading and len(reading.raw_words) == count:
                initial = list(reading.raw_words)

        self._ensure_write_signals(mgr)
        dialog = BlockWriteDialog(
            self,
            block=block,
            values=initial,
            dispatch=self._dispatch_block_write,
            write_manager=mgr,
        )
        dialog.exec()

    def _dispatch_block_write(self, block: Dict[str, Any], values: list) -> bool:
        mgr = self.app_state.write_manager
        if mgr is None:
            return False
        user = self.app_state.current_user or {}
        operator_id = user.get("id")
        if operator_id is None:
            logger.error("Block write rejected: no logged-in operator")
            return False
        return bool(mgr.execute_block_write(block, values, int(operator_id)))

    def _ensure_write_signals(self, mgr) -> None:
        """Bind toast feedback once per write-manager instance."""
        if mgr is self._bound_write_mgr:
            return
        if self._bound_write_mgr is not None:
            for signal, slot in (
                (self._bound_write_mgr.block_write_success, self._on_block_written),
                (self._bound_write_mgr.block_write_failed, self._on_block_write_error),
                (self._bound_write_mgr.plc_busy, self._on_write_busy),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        mgr.block_write_success.connect(self._on_block_written)
        mgr.block_write_failed.connect(self._on_block_write_error)
        mgr.plc_busy.connect(self._on_write_busy)
        self._bound_write_mgr = mgr

    def _toast(self):
        return getattr(self.window(), "toast", None)

    def _on_block_written(self, block_id: int, name: str, count: int) -> None:
        toast = self._toast()
        if toast:
            toast.success(f"Block '{name}' written and verified ({count} values)")

    def _on_block_write_error(self, block_id: int, name: str, error: str) -> None:
        toast = self._toast()
        if toast:
            toast.error(f"Block '{name}': {error}")

    def _on_write_busy(self, message: str) -> None:
        toast = self._toast()
        if toast:
            toast.warning(message)

    def _make_status_cell(self):
        """Create a LED dot + state label cell widget."""
        cell = QFrame()
        cell.setObjectName("led_cell")
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        dot = QLabel("●")
        dot.setObjectName("led_dot")
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(dot)

        lbl = QLabel("—")
        lbl.setObjectName("led_label")
        lay.addWidget(lbl)
        return cell, (dot, lbl)

    def _refresh_data(self) -> None:
        """Update only the visible tab to minimize CPU load."""
        if not self.app_state.is_plc_connected or not self.app_state.connection_manager:
            self.last_refresh_lbl.setText("PLC Disconnected")
            return

        current_widget = self.tabs.currentWidget()

        # Register Block viewer tab?
        if current_widget in self._block_view:
            self._refresh_block_view(current_widget)
            block, _ = self._block_view[current_widget]
            reading = self.app_state.connection_manager.data_model.get_block_reading(
                block["id"]
            )
            suffix = " (STALE)" if (reading and reading.stale) else ""
            self.last_refresh_lbl.setText(
                f"Updated: {datetime.now():%H:%M:%S}{suffix}"
            )
            return

        if not isinstance(current_widget, QTableWidget):
            return

        data_model = self.app_state.connection_manager.data_model

        for row in range(current_widget.rowCount()):
            cell = current_widget.cellWidget(row, 4)
            val_item = current_widget.item(row, 5)
            entry = cell.property("entry") if cell else None

            reading = data_model.get_reading(entry["register_id"])
            if reading:
                self._update_row_ui(cell, val_item, entry, reading)
            else:
                if cell:
                    dot, lbl = cell.findChildren(QLabel)
                    lbl.setText("?")
                val_item.setText("---")

        self.last_refresh_lbl.setText(f"Updated: {datetime.now():%H:%M:%S}")

    def _refresh_block_view(self, container: QWidget) -> None:
        """Fill one block's grid from the latest BlockReading (or dashes)."""
        block, table = self._block_view[container]
        data_model = self.app_state.connection_manager.data_model
        reading = data_model.get_block_reading(block["id"])

        rows = table.rowCount()
        if reading is None:
            for i in range(rows):
                table.item(i, 2).setText("---")
                table.item(i, 3).setText("---")
            container.setToolTip("No data yet")
            return

        raw = reading.raw_words
        is_bit = block["register_type"] == REG_TYPE_COIL
        stride = get_register_count(block["data_type"])
        dp = int(block.get("decimal_places", 2))
        unit = block.get("unit", "") or ""

        for i in range(rows):
            if is_bit:
                bit = raw[i] if i < len(raw) else 0
                table.item(i, 2).setText(str(int(bool(bit))))
                state_item = table.item(i, 3)
                if bit:
                    state_item.setText(block.get("on_label", "ON"))
                    state_item.setForeground(QColor(block.get("on_color", DARK_PASS)))
                else:
                    state_item.setText(block.get("off_label", "OFF"))
                    state_item.setForeground(QColor(block.get("off_color", DARK_TEXT_MUTED)))
            else:
                words = raw[i * stride:(i + 1) * stride]
                table.item(i, 2).setText(",".join(str(w) for w in words))
                if i < len(reading.elements):
                    table.item(i, 3).setText(
                        format_value(reading.elements[i], dp, unit)
                    )

        if reading.stale:
            container.setToolTip(
                f"LAST READ FAILED — showing previous values\n{reading.error}"
            )
        else:
            container.setToolTip("")

    def _update_row_ui(self, cell, val_item: QTableWidgetItem, 
                        entry: dict, reading: RegisterReading) -> None:
        # Determine ON/OFF (anything non-zero is ON for binary diagnostics)
        is_on = reading.display_value != 0
        label = entry["on_label"] if is_on else entry["off_label"]
        
        dot, lbl = cell.findChildren(QLabel) or (None, None)
        if dot is not None:
            color = entry["on_color"] if is_on else entry["off_color"]
            dot.setStyleSheet("color: %s;" % color)
        if lbl is not None:
            lbl.setText(label)
        cell.setToolTip(f"State: {label}")
        
        if entry.get("show_value"):
            val_item.setText(reading.display_str)
        else:
            val_item.setText("-")
