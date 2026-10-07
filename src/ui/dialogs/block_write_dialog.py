"""
block_write_dialog.py — Universal PLC Monitor
Dialog for bulk-writing one register block (raw PLC words / bits) via
PLCWriteManager.execute_block_write (FC16/FC0F + read-back verify).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QPushButton)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from src.utils.constants import REG_TYPE_COIL

logger = logging.getLogger(__name__)


class BlockWriteDialog(QDialog):
    """
    Edit-and-send dialog for one register block.

    Rows are raw PLC values (words for HOLDING, bits for COIL) — exactly
    what execute_block_write() expects. The dialog stays open until the
    background write reports success (accepts) or failure (shows the error
    and re-enables a retry).
    """

    def __init__(
        self,
        parent=None,
        block: Optional[dict] = None,
        values: Optional[list] = None,
        dispatch: Optional[Callable[[dict, list], bool]] = None,
        write_manager=None,
    ) -> None:
        super().__init__(parent)
        self._block = block or {}
        self._dispatch = dispatch
        self._write_manager = write_manager
        self._writing = False

        count = int(self._block.get("count", 0))
        initial = list(values or [])
        if len(initial) < count:
            initial += [0] * (count - len(initial))
        self._initial = initial[:count]

        name = self._block.get("name", "Block")
        self.setWindowTitle(f"Write Block — {name}")
        self.setModal(True)
        self.setMinimumSize(460, 480)
        self.setAccessibleName("Block write dialog")

        self._init_ui()
        self._connect_manager()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        blk = self._block
        start = int(blk.get("start_address", 0))
        count = int(blk.get("count", 0))
        reg_type = blk.get("register_type", "")
        is_bit = reg_type == REG_TYPE_COIL

        info = QLabel(
            f"{blk.get('name', 'Block')} — {reg_type} "
            f"{start}..{start + count - 1} ({count} {'bits' if is_bit else 'words'})"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        note = QLabel(
            "Values are raw PLC values"
            + (" (0/1)." if is_bit else " (0-65535).")
            + " Edit cells, then write — read-back verification follows automatically."
        )
        note.setWordWrap(True)
        note.setObjectName("config_info_lbl")
        layout.addWidget(note)

        self.table = QTableWidget(count, 3)
        self.table.setHorizontalHeaderLabels(["#", "Address", "Value"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Block write values")
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 90)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        font = QFont("Consolas", 10)

        for i in range(count):
            idx_item = QTableWidgetItem(str(i))
            idx_item.setFlags(idx_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            addr_item = QTableWidgetItem(str(start + i))
            addr_item.setFlags(addr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            val_item = QTableWidgetItem(str(int(self._initial[i])))
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            val_item.setFont(font)

            self.table.setItem(i, 0, idx_item)
            self.table.setItem(i, 1, addr_item)
            self.table.setItem(i, 2, val_item)
        layout.addWidget(self.table, 1)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.write_btn = QPushButton(f"Write {count} Values to PLC")
        self.write_btn.setObjectName("btn_danger")
        # A bulk PLC write must be an explicit click — Enter must never fire it.
        self.write_btn.setAutoDefault(False)
        self.write_btn.setDefault(False)
        self.write_btn.clicked.connect(self._on_write)
        btn_row.addWidget(self.write_btn)
        layout.addLayout(btn_row)

    #: Editing allowed again once a write attempt finishes (failed/busy).
    _EDIT_TRIGGERS = (QAbstractItemView.EditTrigger.DoubleClicked
                      | QAbstractItemView.EditTrigger.SelectedClicked)

    # ------------------------------------------------------------------
    # Manager signals
    # ------------------------------------------------------------------
    def _connect_manager(self) -> None:
        mgr = self._write_manager
        if mgr is None:
            return
        mgr.block_write_success.connect(self._on_success)
        mgr.block_write_failed.connect(self._on_failed)
        mgr.plc_busy.connect(self._on_busy)
        try:
            mgr.verify_failed.connect(self._on_verify_mismatch)
        except AttributeError:
            pass  # manager without verify signals (older/mock)

    def _disconnect_manager(self) -> None:
        mgr = self._write_manager
        if mgr is None:
            return
        for signal, slot in (
            (mgr.block_write_success, self._on_success),
            (mgr.block_write_failed, self._on_failed),
            (mgr.plc_busy, self._on_busy),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            mgr.verify_failed.disconnect(self._on_verify_mismatch)
        except (AttributeError, TypeError, RuntimeError):
            pass

    def closeEvent(self, event) -> None:
        self._disconnect_manager()
        super().closeEvent(event)

    def reject(self) -> None:
        self._disconnect_manager()
        super().reject()

    def accept(self) -> None:
        self._disconnect_manager()
        super().accept()

    def _on_success(self, block_id: int, name: str, count: int) -> None:
        if int(block_id) != int(self._block.get("id") or -1):
            return
        self._writing = False
        self._show_status(f"✓ Block '{name}' written and verified ({count} values).", ok=True)
        self.write_btn.setEnabled(True)
        self.accept()

    def _on_failed(self, block_id: int, name: str, error: str) -> None:
        if int(block_id) != int(self._block.get("id") or -1):
            return
        self._writing = False
        self.write_btn.setEnabled(True)
        self.table.setEditTriggers(self._EDIT_TRIGGERS)
        # Rejected-before-dispatch reasons (validation) and PLC errors both
        # arrive here — show and let the operator edit + retry.
        self._show_status(f"✗ {error}", ok=False)

    def _on_busy(self, message: str) -> None:
        self._writing = False
        self.write_btn.setEnabled(True)
        self.table.setEditTriggers(self._EDIT_TRIGGERS)
        self._show_status(f"✗ {message}", ok=False)

    def _on_verify_mismatch(self, address: int, expected: int, actual: int) -> None:
        """Highlight the mismatched row (read-back differed from written value)."""
        start = int(self._block.get("start_address", 0))
        count = int(self._block.get("count", 0))
        if not (start <= int(address) <= start + count - 1):
            return  # mismatch belongs to a different write
        for row in range(self.table.rowCount()):
            addr_item = self.table.item(row, 1)
            if addr_item is not None and addr_item.text() == str(address):
                cell = self.table.item(row, 2)
                if cell is not None:
                    cell.setForeground(QColor("#ef4444"))
                    cell.setToolTip(f"Wrote {expected}, read back {actual}")
                break
        self._show_status(
            f"✗ Verify mismatch at addr {address}: wrote {expected}, "
            f"read back {actual}.",
            ok=False,
        )

    def _clear_mismatch_highlights(self) -> None:
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 2)
            if cell is not None:
                cell.setForeground(QColor())  # reset to palette default
                cell.setToolTip("")

    def _show_status(self, text: str, ok: bool) -> None:
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(
            "color: #22c55e;" if ok else "color: #ef4444;"
        )
        self.status_lbl.setVisible(True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def _gather_values(self) -> Optional[list]:
        """Parse the value column; returns None (with status set) on error."""
        is_bit = self._block.get("register_type") == REG_TYPE_COIL
        values: list[int] = []
        for row in range(self.table.rowCount()):
            text = (self.table.item(row, 2).text() if self.table.item(row, 2) else "").strip()
            try:
                v = int(text, 10)
            except ValueError:
                self._show_status(f"✗ Row {row}: '{text}' is not a whole number.", ok=False)
                self.table.setCurrentCell(row, 2)
                return None
            if is_bit and v not in (0, 1):
                self._show_status(f"✗ Row {row}: coil values must be 0 or 1 (got {v}).", ok=False)
                self.table.setCurrentCell(row, 2)
                return None
            if not is_bit and not (0 <= v <= 65535):
                self._show_status(f"✗ Row {row}: value out of range 0-65535 ({v}).", ok=False)
                self.table.setCurrentCell(row, 2)
                return None
            values.append(v)
        return values

    def _on_write(self) -> None:
        if self._writing:
            return
        values = self._gather_values()
        if values is None:
            return
        if self._dispatch is None:
            self._show_status("✗ No write manager available.", ok=False)
            return

        self._clear_mismatch_highlights()
        self._writing = True
        self.write_btn.setEnabled(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._show_status("Writing to PLC…", ok=True)

        try:
            dispatched = bool(self._dispatch(self._block, values))
        except Exception as exc:  # never leave the dialog stuck
            logger.error("Block write dispatch failed: %s", exc)
            self._writing = False
            self.write_btn.setEnabled(True)
            self.table.setEditTriggers(self._EDIT_TRIGGERS)
            self._show_status(f"✗ {exc}", ok=False)
            return

        if not dispatched and self._writing:
            # Rejection signals are delivered synchronously and normally
            # reset _writing already; this is only a safety net so the
            # dialog can never stay stuck in "writing" state.
            self._writing = False
            self.write_btn.setEnabled(True)
            self.table.setEditTriggers(self._EDIT_TRIGGERS)
            self._show_status("✗ Write rejected.", ok=False)
