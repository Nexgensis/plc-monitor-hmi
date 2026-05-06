"""
write_manager.py — Universal PLC Monitor
Executes all write operations to the PLC.
Schema v4.0 — all writes are driven by the control_registers table.
Executes on the main thread; uses a lock to prevent concurrent write collisions.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from .base_driver import PLCDriver, PLCWriteResult
from src.utils.constants import CTRL_CUSTOM

logger = logging.getLogger(__name__)


class PLCWriteManager(QObject):
    """
    Manages atomic writes to the PLC with optional read-back verification.

    This is the ONLY way the application is permitted to send data to the PLC.
    All operations are logged to the plc_write_log table for auditability.
    """

    # Signals for UI feedback
    write_success      = pyqtSignal(str, int, object)  # name, address, value
    write_failed       = pyqtSignal(str, int, str)     # name, address, error
    verify_failed      = pyqtSignal(int, int, int)      # address, expected, actual
    plc_busy           = pyqtSignal(str)                # "Write already in progress"
    write_log_updated  = pyqtSignal()                   # Signals UI to refresh logs

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

    def execute_control(
        self,
        control_register: dict,
        operator_id: int,
    ) -> PLCWriteResult:
        """
        Executes a configured write operation from the control_registers table.

        Args:
            control_register: Row from control_registers table (as dict),
                              joined with register_library fields.
            operator_id:      ID of the user who triggered the write.

        Returns:
            PLCWriteResult. Never raises.
        """
        if not self._write_lock.acquire(blocking=False):
            logger.warning("execute_control: write lock busy")
            self.plc_busy.emit("A write operation is already in progress.")
            return PLCWriteResult(success=False, error="Write lock busy")

        try:
            reg = control_register
            plc_addr  = reg["register_address"]
            reg_type  = reg["register_type"]
            write_val = int(reg["write_value"])
            pulse_ms  = reg.get("reset_after_ms", 0)
            ctrl_name = reg["name"]

            logger.info(
                "Executing control: %s (addr=%d type=%s val=%d pulse=%d)",
                ctrl_name, plc_addr, reg_type, write_val, pulse_ms
            )

            # 1. Perform the write
            if pulse_ms > 0 and reg_type == "COIL":
                # Momentary pulse (ON -> Wait -> OFF)
                result = self._driver.write_coil_pulse(plc_addr, write_val, pulse_ms)
            else:
                # Direct register write
                result = self._driver.write_register(plc_addr, reg_type, write_val)

            # 2. Read-back verification (for HOLDING registers)
            if result.success and reg_type == "HOLDING":
                # Wait briefly for PLC to process the scan
                time.sleep(0.15)
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
                        self.verify_failed.emit(plc_addr, write_val, actual)
                else:
                    logger.warning("Read-back verification failed for %s", ctrl_name)

            # 3. Log to audit trail
            self._log_write(
                reg            = reg,
                value_written  = write_val,
                value_readback = result.value_readback,
                success        = result.success,
                error          = result.error,
                reason         = reg.get("control_type", CTRL_CUSTOM),
                operator_id    = operator_id
            )

            # 4. Emit results
            if result.success:
                self.write_success.emit(ctrl_name, plc_addr, write_val)
            else:
                self.write_failed.emit(ctrl_name, plc_addr, result.error)

            return result

        except Exception as exc:
            logger.error("execute_control Exception: %s", exc)
            return PLCWriteResult(success=False, error=str(exc))

        finally:
            self._write_lock.release()

    def _log_write(
        self,
        reg: dict,
        value_written: Any,
        value_readback: Any,
        success: bool,
        error: str,
        reason: str,
        operator_id: int,
    ) -> None:
        """Internal helper to write the audit log entry."""
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
            reason
        )

        try:
            self._db.execute(query, params)
            self.write_log_updated.emit()
        except Exception as exc:
            logger.error("Failed to log PLC write to DB: %s", exc)
