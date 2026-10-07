"""
connection_manager.py — Universal PLC Monitor
Background polling thread for all active PLC registers and data blocks.

Per-register reads use each entry's own Modbus table (one request per
entry); data blocks (contiguous address ranges) are read with the
driver's chunked read_block() so a range costs ceil(count / chunk)
requests instead of `count`.
Schema v4.0 — zero hardcoded addresses.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal

from .base_driver import PLCDriver
from .data_model import PLCDataModel, RegisterReading, PLCStatus, BlockReading
from .driver_factory import PLCDriverFactory
from src.utils.validators import convert_raw_to_value, get_register_count

logger = logging.getLogger(__name__)


class ConnectionManager(QThread):
    """
    Background worker thread that manages the PLC connection and polling loop.

    Polls from:
        1. active_model (from model_register_map)
        2. io_list_config
        3. register_blocks (contiguous ranges, batched via read_block)
    """

    # Signals
    connected                = pyqtSignal()
    disconnected             = pyqtSignal()
    connection_state_changed = pyqtSignal(bool)
    readings_updated         = pyqtSignal(dict)  # {register_id: RegisterReading}
    blocks_updated           = pyqtSignal(dict)  # {block_id: BlockReading}
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
        blocks_to_poll: list[dict] | None = None,
    ) -> None:
        """
        Args:
            plc_profile:       Row from plc_profile table.
            registers_to_poll: List of register_library rows (as dicts) to monitor.
            message_register:  Register to monitor for status bar messages (None if disabled).
            message_lookup:    Map of {value: (text, color)} for status messages.
            data_model:        Shared thread-safe PLCDataModel.
            driver:            Optional pre-created driver instance.
            blocks_to_poll:    List of register_blocks rows (as dicts) to poll
                               in batch. Optional — defaults to no blocks,
                               which is exactly the pre-block behaviour.
        """
        super().__init__()
        self._profile      = plc_profile
        self._registers    = registers_to_poll
        self._blocks       = blocks_to_poll or []
        self._msg_reg      = message_register
        self._msg_lookup   = message_lookup
        self._model        = data_model
        self._stop_event   = threading.Event()
        self._prev_msg_val = -1
        self._driver       = driver
        # Guards _registers / _blocks / _msg_reg / _msg_lookup against
        # GUI-thread swaps while the poll loop is iterating.
        self._list_lock    = threading.Lock()

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

        self._stop_event.clear()
        was_connected = False
        max_reconnect = int(self._profile.get("max_retries", 3))
        consecutive_failures = 0
        logger.info("ConnectionManager: Polling loop started (max_reconnect=%d)", max_reconnect)

        while not self._stop_event.is_set():
            # 1. Handle Connectivity
            if not self._driver.is_connected():
                ok = self._driver.connect()
                if ok and not was_connected:
                    logger.info("PLC Connected")
                    self.connected.emit()
                    self.connection_state_changed.emit(True)
                    self._driver.reset_stats()
                    was_connected = True
                    consecutive_failures = 0
                elif not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= max_reconnect:
                        msg = f"PLC connection failed after {consecutive_failures} attempts — polling stopped"
                        logger.error(msg)
                        self.comm_error.emit(msg)
                        self.disconnected.emit()
                        self.connection_state_changed.emit(False)
                        was_connected = False
                        break
                    logger.warning(
                        "PLC connect failed (%d/%d), retrying in %d ms",
                        consecutive_failures, max_reconnect,
                        int(self._profile.get("reconnect_delay_ms", 3000)),
                    )
                    if was_connected:
                        self.disconnected.emit()
                        self.connection_state_changed.emit(False)
                        was_connected = False
                    # Use event wait instead of msleep so stop() can interrupt
                    self._stop_event.wait(int(self._profile.get("reconnect_delay_ms", 3000)) / 1000.0)
                    continue

            # 2. Snapshot the poll targets once per cycle (GUI thread may
            #    swap them concurrently via update_poll_list/update_block_list).
            with self._list_lock:
                registers  = self._registers
                blocks     = self._blocks
                msg_reg    = self._msg_reg
                msg_lookup = self._msg_lookup

            # 3. Read each configured register using its own Modbus table.
            # A previous grouped read path only returned one value per address,
            # which broke sparse coils/discrete inputs and multi-word values.
            all_readings: dict[int, RegisterReading] = {}
            for reg in registers:
                reading = self._read_configured_register(reg)
                if reading is None:
                    continue

                self._model.update_reading(reg["register_id"], reading)
                all_readings[reg["register_id"]] = reading

            # 4. Read data blocks (contiguous ranges, chunked batch requests)
            all_blocks: dict[int, BlockReading] = {}
            for blk in blocks:
                block_reading = self._read_configured_block(blk)
                if block_reading is None:
                    continue

                self._model.update_block_reading(blk["block_id"], block_reading)
                all_blocks[blk["block_id"]] = block_reading

            # 5. Read message register separately
            if msg_reg:
                res = self._driver.read_registers(
                    msg_reg["register_address"], msg_reg["register_type"], 1
                )
                if res.success and res.values:
                    val = res.values[0]
                    if val != self._prev_msg_val:
                        text, color = msg_lookup.get(val, ("", "white"))
                        self.message_changed.emit(val, text, color)
                        self._prev_msg_val = val

            # 6. Update overall status and quality
            if all_readings:
                self.readings_updated.emit(all_readings)
            if all_blocks:
                self.blocks_updated.emit(all_blocks)

            stats = self._driver.get_quality_stats()
            status = PLCStatus(
                is_connected           = True,
                protocol               = self._profile["protocol"],
                host_or_port           = str(self._profile.get("host") or self._profile.get("com_port", "")),
                quality                = stats,
                last_updated           = datetime.now(timezone.utc),
                message_register_value = self._prev_msg_val,
                message_text           = msg_lookup.get(self._prev_msg_val, ("", ""))[0],
                message_color          = msg_lookup.get(self._prev_msg_val, ("", "white"))[1]
            )
            self._model.update_status(status)
            self.status_updated.emit(status)
            self.quality_updated.emit(stats)

            # Sleep for configured interval (interruptible by stop)
            self._stop_event.wait(int(self._profile.get("poll_interval_ms", 500)) / 1000.0)

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
        with self._list_lock:
            self._registers  = registers
            self._msg_reg    = message_register
            self._msg_lookup = message_lookup
            self._prev_msg_val = -1  # Force status bar re-evaluation
        logger.info("ConnectionManager: Polling list updated (%d registers)", len(registers))

    def update_block_list(self, blocks: list[dict]) -> None:
        """
        Thread-safe update of the data-block poll targets (e.g. when the
        operator edits Register Blocks in CONFIG).
        """
        with self._list_lock:
            self._blocks = list(blocks)
        logger.info("ConnectionManager: Block list updated (%d blocks)", len(blocks))

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
        self._stop_event.set()
        self.wait(3000)

    def _read_configured_register(self, reg: dict) -> RegisterReading | None:
        """
        Reads one register-library entry with the correct Modbus function.

        This intentionally uses the universal driver method instead of a
        holding-register shortcut so HOLDING, INPUT, COIL, and DISCRETE entries
        all follow the register_type selected in CONFIG.
        """
        if self._driver is None:
            return None

        reg_type = reg["register_type"]
        count = get_register_count(reg["data_type"])
        result = self._driver.read_registers(reg["register_address"], reg_type, count)

        if not result.success:
            name = reg.get("display_name") or reg.get("library_name") or reg.get("name", "Unknown")
            self.comm_error.emit(
                f"{name} ({reg_type} {reg['register_address']}) read failed: {result.error}"
            )
            return None

        raw_words = result.values[:count]
        if len(raw_words) < count:
            raw_words += [0] * (count - len(raw_words))

        display = convert_raw_to_value(
            raw_words,
            reg["data_type"],
            reg["scale_factor"],
            bool(reg.get("word_swap", 0))
        )

        dp = reg.get("decimal_places", 2)
        unit = reg.get("unit", "")
        return RegisterReading(
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

    def _extract_words(self, values: list[int], start_idx: int, count: int) -> list[int]:
        """Safely extracts a slice of words from a batch read result."""
        return [
            values[start_idx + i]
            if (start_idx + i) < len(values) else 0
            for i in range(count)
        ]

    def _read_configured_block(self, blk: dict) -> BlockReading | None:
        """
        Reads one register_blocks row as a contiguous range via the
        driver's chunked read_block().

        On failure: keeps the previous successful values (marked stale)
        so the UI can show last-known data, and emits comm_error once
        per failed block per cycle (mirrors per-register behaviour).
        Returns None only when there is nothing at all to show (failed
        with no prior successful poll).
        """
        if self._driver is None:
            return None

        block_id = int(blk["block_id"])
        reg_type = blk["register_type"]
        start = int(blk["start_address"])
        count = int(blk["count"])
        data_type = blk.get("data_type", "INT16")
        stride = get_register_count(data_type)

        result = self._driver.read_block(start, reg_type, count)

        if not result.success:
            name = blk.get("name", "Block")
            self.comm_error.emit(
                f"Block '{name}' ({reg_type} {start}+{count}) read failed: {result.error}"
            )
            prev = self._model.get_block_reading(block_id)
            if prev is None:
                return None
            return BlockReading(
                block_id      = block_id,
                name          = prev.name,
                start_address = prev.start_address,
                register_type = prev.register_type,
                count         = prev.count,
                raw_words     = prev.raw_words,
                elements      = prev.elements,
                read_success  = False,
                error         = result.error or "read failed",
                stale         = True,
                timestamp     = datetime.now(timezone.utc),
            )

        raw_words = list(result.values[:count])
        if len(raw_words) < count:
            raw_words += [0] * (count - len(raw_words))

        if reg_type in ("COIL", "DISCRETE"):
            elements = [float(v) for v in raw_words]
        else:
            elements = []
            for i in range(0, count, stride):
                chunk = raw_words[i:i + stride]
                if len(chunk) < stride:
                    chunk += [0] * (stride - len(chunk))
                elements.append(
                    convert_raw_to_value(
                        chunk, data_type,
                        blk.get("scale_factor", 1.0),
                        bool(blk.get("word_swap", 0)),
                    )
                )

        return BlockReading(
            block_id      = block_id,
            name          = blk.get("name", "Block"),
            start_address = start,
            register_type = reg_type,
            count         = count,
            raw_words     = raw_words,
            elements      = elements,
            read_success  = True,
            error         = "",
            stale         = False,
            timestamp     = datetime.now(timezone.utc),
        )
