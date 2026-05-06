"""
connection_manager.py — Universal PLC Monitor
Background polling thread for all active PLC registers.
Groups registers by type for batch reading to optimize PLC round-trips.
Schema v4.0 — zero hardcoded addresses.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal

from .base_driver import PLCDriver
from .data_model import PLCDataModel, RegisterReading, PLCStatus
from .driver_factory import PLCDriverFactory
from src.utils.validators import convert_raw_to_value, get_register_count

logger = logging.getLogger(__name__)


class ConnectionManager(QThread):
    """
    Background worker thread that manages the PLC connection and polling loop.

    Polls registers from:
        1. active_model (from model_register_map)
        2. io_list_config
    Groups them by register_type to perform bulk Modbus requests.
    """

    # Signals
    connected                = pyqtSignal()
    disconnected             = pyqtSignal()
    connection_state_changed = pyqtSignal(bool)
    readings_updated         = pyqtSignal(dict)  # {register_id: RegisterReading}
    status_updated           = pyqtSignal(object) # PLCStatus
    message_changed          = pyqtSignal(int, str, str) # val, text, color
    quality_updated          = pyqtSignal(dict)  # stats dict
    comm_error               = pyqtSignal(str)

    def __init__(
        self,
        plc_profile: dict,
        registers_to_poll: list[dict],
        message_register: dict | None,
        message_lookup: dict[int, tuple[str, str]],
        data_model: PLCDataModel,
        driver: PLCDriver | None = None,
    ) -> None:
        """
        Args:
            plc_profile:       Row from plc_profile table.
            registers_to_poll: List of register_library rows (as dicts) to monitor.
            message_register:  Register to monitor for status bar messages (None if disabled).
            message_lookup:    Map of {value: (text, color)} for status messages.
            data_model:        Shared thread-safe PLCDataModel.
            driver:            Optional pre-created driver instance.
        """
        super().__init__()
        self._profile      = plc_profile
        self._registers    = registers_to_poll
        self._msg_reg      = message_register
        self._msg_lookup   = message_lookup
        self._model        = data_model
        self._running      = False
        self._prev_msg_val = -1
        self._driver       = driver

        if self._driver is None:
            try:
                self._driver = PLCDriverFactory.create(plc_profile)
            except ValueError as exc:
                logger.warning("ConnectionManager: Driver creation failed: %s", exc)

    def run(self) -> None:
        """The main polling loop."""
        if self._driver is None:
            logger.error("ConnectionManager: No driver available, polling aborted.")
            return

        self._running = True
        was_connected = False
        logger.info("ConnectionManager: Polling loop started")

        while self._running:
            # 1. Handle Connectivity
            if not self._driver.is_connected():
                ok = self._driver.connect()
                if ok and not was_connected:
                    logger.info("PLC Connected")
                    self.connected.emit()
                    self.connection_state_changed.emit(True)
                    self._driver.reset_stats()
                    was_connected = True
                elif not ok:
                    if was_connected:
                        logger.warning("PLC Disconnected")
                        self.disconnected.emit()
                        self.connection_state_changed.emit(False)
                        was_connected = False
                    self.msleep(int(self._profile.get("reconnect_delay_ms", 3000)))
                    continue

            # 2. Group registers by type for batch reading
            type_groups: dict[str, list[dict]] = {}
            for reg in self._registers:
                rt = reg["register_type"]
                type_groups.setdefault(rt, []).append(reg)

            # 3. Read each type group as batch
            all_readings: dict[int, RegisterReading] = {}
            for reg_type, regs in type_groups.items():
                addresses = [r["register_address"] for r in regs]
                result = self._driver.read_batch_by_type(addresses, reg_type)

                if not result.success:
                    self.comm_error.emit(f"{reg_type} batch read failed: {result.error}")
                    continue

                for i, reg in enumerate(regs):
                    if i >= len(result.values):
                        continue

                    # Extract words for this specific data type (handles 32-bit types)
                    count = get_register_count(reg["data_type"])
                    raw_words = self._extract_words(result.values, i, count)

                    # Convert raw bits to scaled engineering value
                    display = convert_raw_to_value(
                        raw_words,
                        reg["data_type"],
                        reg["scale_factor"],
                        bool(reg.get("word_swap", 0))
                    )

                    dp = reg.get("decimal_places", 2)
                    unit = reg.get("unit", "")
                    reading = RegisterReading(
                        register_id   = reg["register_id"],
                        name          = reg.get("display_name") or reg.get("library_name") or reg.get("name", "Unknown"),
                        plc_address   = reg["register_address"],
                        register_type = reg_type,
                        raw_words     = raw_words,
                        display_value = display,
                        display_str   = f"{display:.{dp}f} {unit}".strip(),
                        unit          = unit,
                        data_type     = reg["data_type"],
                        timestamp     = datetime.now(timezone.utc),
                        read_success  = True
                    )
                    self._model.update_reading(reg["register_id"], reading)
                    all_readings[reg["register_id"]] = reading

            # 4. Read message register separately
            if self._msg_reg:
                mr = self._msg_reg
                res = self._driver.read_registers(mr["register_address"], mr["register_type"], 1)
                if res.success and res.values:
                    val = res.values[0]
                    if val != self._prev_msg_val:
                        text, color = self._msg_lookup.get(val, ("", "white"))
                        self.message_changed.emit(val, text, color)
                        self._prev_msg_val = val

            # 5. Update overall status and quality
            if all_readings:
                self.readings_updated.emit(all_readings)

            stats = self._driver.get_quality_stats()
            status = PLCStatus(
                is_connected           = True,
                protocol               = self._profile["protocol"],
                host_or_port           = str(self._profile.get("host") or self._profile.get("com_port", "")),
                quality                = stats,
                last_updated           = datetime.now(timezone.utc),
                message_register_value = self._prev_msg_val,
                message_text           = self._msg_lookup.get(self._prev_msg_val, ("", ""))[0],
                message_color          = self._msg_lookup.get(self._prev_msg_val, ("", "white"))[1]
            )
            self._model.update_status(status)
            self.status_updated.emit(status)
            self.quality_updated.emit(stats)

            # Sleep for configured interval
            self.msleep(int(self._profile.get("poll_interval_ms", 500)))

        # Clean up on exit
        self._driver.disconnect()
        logger.info("ConnectionManager: Polling loop stopped")

    def update_poll_list(
        self,
        registers: list[dict],
        message_register: dict | None,
        message_lookup: dict[int, tuple[str, str]],
    ) -> None:
        """
        Thread-safe update of the polling targets (e.g. when the operator
        switches models).
        """
        self._registers  = registers
        self._msg_reg    = message_register
        self._msg_lookup = message_lookup
        self._prev_msg_val = -1  # Force status bar re-evaluation
        logger.info("ConnectionManager: Polling list updated (%d registers)", len(registers))

    def get_driver(self) -> PLCDriver | None:
        """Returns the internal driver for manual override writes."""
        return self._driver

    def get_quality_stats(self) -> dict:
        """Returns the current connection quality statistics from the driver."""
        if self._driver:
            return self._driver.get_quality_stats()
        return {}

    @property
    def data_model(self) -> PLCDataModel:
        """Returns the shared thread-safe data model."""
        return self._model

    def stop(self) -> None:
        """Gracefully stops the polling loop."""
        self._running = False
        self.wait(3000)

    def _extract_words(self, values: list[int], start_idx: int, count: int) -> list[int]:
        """Safely extracts a slice of words from a batch read result."""
        return [
            values[start_idx + i]
            if (start_idx + i) < len(values) else 0
            for i in range(count)
        ]
