"""
write_manager.py — Universal PLC Monitor
Executes all write operations to the PLC asynchronously.
Schema v4.0 — all writes are driven by the control_registers table.
Schema v4.3 — bulk register-block writes (FC16/FC0F) via
execute_block_write(), audited with block_id in plc_write_log.
Uses QThreadPool + QRunnable so the main UI thread is NEVER blocked by
network I/O, time.sleep pulse delays, or DB logging.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .base_driver import PLCDriver
from src.utils.constants import (
    CTRL_CUSTOM,
    ACCESS_READ_ONLY,
    ACCESS_READ_WRITE,
    REG_TYPE_COIL,
    REG_TYPE_DISCRETE,
    REG_TYPE_INPUT,
    REASON_BLOCK_WRITE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal background worker (one per write operation)
# ---------------------------------------------------------------------------

class _WriteTaskSignals(QObject):
    """Qt signals emitted by the background write task back to the UI thread."""
    write_success     = pyqtSignal(str, int, object)  # name, address, value
    write_failed      = pyqtSignal(str, int, str)      # name, address, error
    verify_failed     = pyqtSignal(int, int, int)       # address, expected, actual
    write_log_updated = pyqtSignal()
    block_write_success = pyqtSignal(int, str, int)    # block_id, name, value_count
    block_write_failed  = pyqtSignal(int, str, str)    # block_id, name, error


def _summarize_values(values: list, limit: int = 16) -> str:
    """
    Compact text summary of a value list for the audit log.
    Short lists are stored in full; long lists (e.g. 1000-word blocks)
    are truncated so plc_write_log rows stay readable.
    """
    if len(values) <= limit:
        return str(list(values))
    head = ", ".join(str(v) for v in values[:limit])
    return f"[{head}, ... ({len(values)} values total)]"


class _WriteTask(QRunnable):
    """
    Background runnable that performs one atomic PLC write.
    Runs on a QThreadPool worker thread — never on the main UI thread.
    """

    def __init__(
        self,
        driver: PLCDriver,
        db,
        control_register: dict,
        operator_id: int,
        signals: _WriteTaskSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._driver     = driver
        self._db         = db
        self._reg        = control_register
        self._op_id      = operator_id
        self._signals    = signals

    def run(self) -> None:
        reg       = self._reg
        plc_addr  = reg["register_address"]
        reg_type  = reg["register_type"]
        write_val = int(reg["write_value"])
        pulse_ms  = reg.get("reset_after_ms", 0)
        ctrl_name = reg["name"]

        logger.info(
            "Executing control: %s (addr=%d type=%s val=%d pulse=%d)",
            ctrl_name, plc_addr, reg_type, write_val, pulse_ms
        )

        try:
            # 1. Perform the write
            if pulse_ms > 0 and reg_type == "COIL":
                # Momentary pulse (ON → Wait → OFF) — sleep is safe here (background thread)
                result = self._driver.write_coil_pulse(plc_addr, write_val, pulse_ms)
            else:
                result = self._driver.write_register(plc_addr, reg_type, write_val)

            # 2. Read-back verification (HOLDING registers only)
            if result.success and reg_type == "HOLDING":
                time.sleep(0.15)  # Wait for PLC scan — safe on background thread
                rb_res = self._driver.read_registers(plc_addr, reg_type, 1)
                if rb_res.success and rb_res.values:
                    actual = rb_res.values[0]
                    result.value_readback = actual
                    result.verified = (actual == write_val)
                    if not result.verified:
                        logger.error(
                            "Verify FAILED for %s at addr %d: expected %d, got %d",
                            ctrl_name, plc_addr, write_val, actual
                        )
                        self._signals.verify_failed.emit(plc_addr, write_val, actual)
                else:
                    logger.warning("Read-back verification failed for %s", ctrl_name)

            # 3. Log to audit trail
            self._log_write(
                reg            = reg,
                value_written  = write_val,
                value_readback = getattr(result, "value_readback", None),
                success        = result.success,
                error          = result.error,
                reason         = reg.get("control_type", CTRL_CUSTOM),
                operator_id    = self._op_id,
            )

            # 4. Emit result signals (safe — Qt queues them to the main thread)
            if result.success:
                self._signals.write_success.emit(ctrl_name, plc_addr, write_val)
            else:
                self._signals.write_failed.emit(ctrl_name, plc_addr, result.error or "Unknown error")

        except Exception as exc:
            logger.error("_WriteTask Exception for %s: %s", ctrl_name, exc)
            self._signals.write_failed.emit(ctrl_name, plc_addr, str(exc))

    def _log_write(
        self,
        reg: dict,
        value_written: Any,
        value_readback: Any,
        success: bool,
        error: "str | None",
        reason: "str | None",
        operator_id: int,
    ) -> None:
        """Writes the audit log entry to the database."""
        query = """
            INSERT INTO plc_write_log (
                register_id,
                register_address,
                register_name,
                value_written,
                value_readback,
                write_success,
                error_message,
                operator_id,
                write_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            reg["register_id"],
            reg["register_address"],
            reg["name"],
            str(value_written),
            str(value_readback) if value_readback is not None else None,
            1 if success else 0,
            error or None,
            operator_id,
            reason,
        )
        try:
            self._db.execute(query, params)
            self._signals.write_log_updated.emit()
        except Exception as exc:
            logger.error("Failed to log PLC write to DB: %s", exc)


# ---------------------------------------------------------------------------
# Lock-releasing wrapper — releases the write lock when the task finishes
# ---------------------------------------------------------------------------

class _LockReleasingWriteTask(_WriteTask):
    """Wraps _WriteTask and releases the manager's write lock when done."""

    def __init__(self, lock: threading.Lock, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lock = lock

    def run(self) -> None:
        try:
            super().run()
        finally:
            self._lock.release()


# ---------------------------------------------------------------------------
# Bulk register-block write (one per write operation)
# ---------------------------------------------------------------------------

class _BlockWriteTask(QRunnable):
    """
    Background runnable that writes one register block as a contiguous
    range (driver chunks to FC16/FC0F), verifies by read-back, and writes
    an audit row carrying block_id. Runs on a QThreadPool worker thread.
    """

    #: Max verify_failed emissions per block write (keeps a 2000-bit
    #: block-wide mismatch from flooding the UI signal queue).
    MAX_VERIFY_MISMATCH_EMISSIONS = 10

    def __init__(
        self,
        driver: PLCDriver,
        db,
        block: dict,
        values: list[int],
        operator_id: int,
        signals: _WriteTaskSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._driver  = driver
        self._db      = db
        self._block   = block
        self._values  = values
        self._op_id   = operator_id
        self._signals = signals

    def run(self) -> None:
        blk      = self._block
        block_id = int(blk.get("id") or blk.get("block_id") or 0)
        name     = blk.get("name", "Block")
        start    = int(blk["start_address"])
        reg_type = blk["register_type"]
        count    = int(blk["count"])
        values   = self._values
        readback: list[int] | None = None

        logger.info(
            "Executing block write: %s (id=%d type=%s start=%d count=%d)",
            name, block_id, reg_type, start, count
        )

        try:
            if self._driver is None:
                raise RuntimeError("No PLC driver available")

            # 1. Bulk write — driver chunks to FC16 (words) / FC0F (bits)
            result = self._driver.write_block(start, reg_type, values)

            # 2. Read-back verification (mirrors single-register verify)
            if result.success:
                time.sleep(0.15)  # Wait for PLC scan — safe on background thread
                rb_res = self._driver.read_block(start, reg_type, count)
                if rb_res.success and rb_res.values:
                    readback = list(rb_res.values[:count])
                    mismatches = [
                        (start + i, int(exp), int(act))
                        for i, (exp, act) in enumerate(zip(values, readback))
                        if int(exp) != int(act)
                    ]
                    if mismatches:
                        logger.error(
                            "Verify FAILED for block %s: %d of %d values mismatch",
                            name, len(mismatches), count
                        )
                        for addr, expected, actual in mismatches[:self.MAX_VERIFY_MISMATCH_EMISSIONS]:
                            self._signals.verify_failed.emit(addr, expected, actual)
                else:
                    logger.warning("Read-back verification failed for block %s", name)

            # 3. Audit trail (register_id NULL, block_id set)
            self._log_write(
                block          = blk,
                values_written = values,
                value_readback = readback,
                success        = result.success,
                error          = result.error,
                operator_id    = self._op_id,
            )

            # 4. Emit result signals (Qt queues them to the main thread)
            if result.success:
                self._signals.block_write_success.emit(block_id, name, len(values))
            else:
                self._signals.block_write_failed.emit(
                    block_id, name, result.error or "Unknown error"
                )

        except Exception as exc:
            logger.error("_BlockWriteTask Exception for %s: %s", name, exc)
            self._log_write(
                block          = blk,
                values_written = values,
                value_readback = None,
                success        = False,
                error          = str(exc),
                operator_id    = self._op_id,
            )
            self._signals.block_write_failed.emit(block_id, name, str(exc))

    def _log_write(
        self,
        block: dict,
        values_written: list[int],
        value_readback: list[int] | None,
        success: bool,
        error: "str | None",
        operator_id: int,
    ) -> None:
        """Writes the audit log entry (block_id column) to the database."""
        query = """
            INSERT INTO plc_write_log (
                register_id,
                block_id,
                register_address,
                register_name,
                value_written,
                value_readback,
                write_success,
                error_message,
                operator_id,
                write_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            None,
            int(block.get("id") or block.get("block_id") or 0),
            int(block["start_address"]),
            block.get("name", "Block"),
            _summarize_values(values_written),
            _summarize_values(value_readback) if value_readback is not None else None,
            1 if success else 0,
            error or None,
            operator_id,
            REASON_BLOCK_WRITE,
        )
        try:
            self._db.execute(query, params)
            self._signals.write_log_updated.emit()
        except Exception as exc:
            logger.error("Failed to log block write to DB: %s", exc)


class _LockReleasingBlockWriteTask(_BlockWriteTask):
    """Wraps _BlockWriteTask and releases the manager's write lock when done."""

    def __init__(self, lock: threading.Lock, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lock = lock

    def run(self) -> None:
        try:
            super().run()
        finally:
            self._lock.release()


# ---------------------------------------------------------------------------
# Public manager — thin dispatcher
# ---------------------------------------------------------------------------

class PLCWriteManager(QObject):
    """
    Manages atomic writes to the PLC with optional read-back verification.

    This is the ONLY way the application is permitted to send data to the PLC.
    All blocking operations run on a QThreadPool worker thread so the UI never
    freezes. Signals are forwarded from the internal _WriteTaskSignals object.
    """

    # Signals for UI feedback (forwarded from worker tasks)
    write_success     = pyqtSignal(str, int, object)  # name, address, value
    write_failed      = pyqtSignal(str, int, str)      # name, address, error
    verify_failed     = pyqtSignal(int, int, int)       # address, expected, actual
    plc_busy          = pyqtSignal(str)                 # "Write already in progress"
    write_log_updated = pyqtSignal()                    # Signals UI to refresh logs
    block_write_success = pyqtSignal(int, str, int)     # block_id, name, value_count
    block_write_failed  = pyqtSignal(int, str, str)     # block_id, name, error

    def __init__(self, driver: PLCDriver, db, app_state) -> None:
        """
        Args:
            driver:    Active PLCDriver instance.
            db:        Database manager instance.
            app_state: Global AppState (for safety checks).
        """
        super().__init__()
        self._driver     = driver
        self._db         = db
        self._app_state  = app_state
        self._write_lock = threading.Lock()

        # Shared signals object (created once, reused by all tasks)
        self._task_signals = _WriteTaskSignals()
        self._task_signals.write_success.connect(self.write_success)
        self._task_signals.write_failed.connect(self.write_failed)
        self._task_signals.verify_failed.connect(self.verify_failed)
        self._task_signals.write_log_updated.connect(self.write_log_updated)
        self._task_signals.block_write_success.connect(self.block_write_success)
        self._task_signals.block_write_failed.connect(self.block_write_failed)

    def execute_control(
        self,
        control_register: dict,
        operator_id: int,
    ) -> None:
        """
        Dispatches a configured write operation to a background thread.

        Returns immediately — the result is delivered via signals:
            • write_success(name, address, value)
            • write_failed(name, address, error)
            • verify_failed(address, expected, actual)

        Args:
            control_register: Row from control_registers table (as dict),
                              joined with register_library fields.
            operator_id:      ID of the user who triggered the write.
        """
        if not self._write_lock.acquire(blocking=False):
            logger.warning("execute_control: write lock busy")
            self.plc_busy.emit("A write operation is already in progress.")
            return

        # Release lock once the task completes (via a wrapping subclass)
        task = _LockReleasingWriteTask(
            driver           = self._driver,
            db               = self._db,
            control_register = control_register,
            operator_id      = operator_id,
            signals          = self._task_signals,
            lock             = self._write_lock,
        )
        QThreadPool.globalInstance().start(task)

    def execute_block_write(
        self,
        block: dict,
        values: list,
        operator_id: int,
    ) -> bool:
        """
        Dispatches a bulk write of one register block to a background thread.

        The driver chunks the range to FC16 (HOLDING words) / FC0F (coils)
        and the task verifies by read-back, then writes an audit row with
        block_id. Returns immediately — the result is delivered via signals:
            • block_write_success(block_id, name, value_count)
            • block_write_failed(block_id, name, error)
            • verify_failed(address, expected, actual)  — per mismatch
            • write_log_updated()
            • plc_busy(message)  — another write in progress

        Args:
            block:       Row from register_blocks table (as dict).
            values:      Raw words (0..65535) or bits (0/1) to write —
                         must be exactly `block["count"]` long.
            operator_id: ID of the user who triggered the write.

        Returns:
            True if a background task was dispatched, False if rejected
            (validation failure or busy) — in both rejection cases a
            block_write_failed / plc_busy signal carries the reason.
        """
        blk_id    = int(block.get("id") or block.get("block_id") or 0)
        name      = block.get("name", "Block")
        reg_type  = block.get("register_type")
        access    = block.get("access", ACCESS_READ_ONLY)
        count     = int(block.get("count", 0))

        def reject(reason: str) -> bool:
            logger.warning("execute_block_write rejected for block '%s': %s", name, reason)
            self.block_write_failed.emit(blk_id, name, reason)
            return False

        # 1. Block definition sanity
        if "start_address" not in block or not reg_type:
            return reject("Invalid block definition (missing start_address or register_type).")

        # 2. Read-only tables / blocks are never writable
        if reg_type in (REG_TYPE_DISCRETE, REG_TYPE_INPUT):
            return reject(f"{reg_type} blocks are read-only.")
        if access != ACCESS_READ_WRITE:
            return reject("Block access is READ_ONLY — enable READ_WRITE in CONFIG first.")

        # 3. Value validation (raw PLC words, engineering values are decoded
        #    by the UI before calling this)
        if not isinstance(values, (list, tuple)):
            return reject("Values must be a list.")
        if len(values) != count:
            return reject(f"Expected {count} values, got {len(values)}.")

        normalized: list[int] = []
        for i, v in enumerate(values):
            if isinstance(v, bool):
                v = 1 if v else 0
            if not isinstance(v, int):
                return reject(f"Value at index {i} is not an integer: {v!r}.")
            if reg_type == REG_TYPE_COIL:
                if v not in (0, 1):
                    return reject(f"Coil value at index {i} must be 0 or 1, got {v}.")
            elif not (0 <= v <= 65535):
                return reject(f"Word value at index {i} out of range 0-65535: {v}.")
            normalized.append(v)

        # 4. One write at a time (shared lock with single-register writes)
        if not self._write_lock.acquire(blocking=False):
            logger.warning("execute_block_write: write lock busy")
            self.plc_busy.emit("A write operation is already in progress.")
            return False

        # Release lock once the task completes (via a wrapping subclass)
        task = _LockReleasingBlockWriteTask(
            driver      = self._driver,
            db          = self._db,
            block       = block,
            values      = normalized,
            operator_id = operator_id,
            signals     = self._task_signals,
            lock        = self._write_lock,
        )
        QThreadPool.globalInstance().start(task)
        return True

    def stop(self) -> None:
        """Gracefully stop the write manager and wait for pending tasks."""
        QThreadPool.globalInstance().waitForDone(2000)
        logger.info("PLCWriteManager stopped")
