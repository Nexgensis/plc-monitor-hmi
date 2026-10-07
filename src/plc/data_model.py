"""
data_model.py — Universal PLC Monitor
Thread-safe shared state for PLC readings and connection status.
Pure Python/threading — no Qt dependencies.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RegisterReading:
    """
    Thread-safe snapshot of a single register's state.

    Fields:
        register_id:   Primary key in register_library.
        name:          User-defined name (e.g., 'Dipper LOW Current').
        plc_address:   User-configured PLC address (e.g., 100 for D100).
        register_type: HOLDING, COIL, DISCRETE, or INPUT.
        raw_words:     List of raw 16-bit register words from PLC.
        display_value: Engineering value after scale_factor applied.
        display_str:   Formatted string with unit (e.g., '34.56 mV').
        unit:          Unit of measure (e.g., 'V', 'A', 'rpm').
        data_type:     INT16, FLOAT32, etc.
        timestamp:     UTC timestamp of the reading.
        read_success:  True if the last poll succeeded.
    """
    register_id: int
    name: str
    plc_address: int
    register_type: str
    raw_words: list[int]
    display_value: float
    display_str: str
    unit: str
    data_type: str
    timestamp: datetime
    read_success: bool


# Alias for backward compatibility with UI components
ParameterReading = RegisterReading


@dataclass
class BlockReading:
    """
    Thread-safe snapshot of one data block's (address range) latest poll.

    Fields:
        block_id:      register_blocks.id.
        name:          Block name from CONFIG.
        start_address: First PLC-native address of the range.
        register_type: HOLDING, COIL, DISCRETE, or INPUT.
        count:         Words (HOLDING/INPUT) or bits (COIL/DISCRETE) polled.
        raw_words:     Raw values index 0 = start_address (words 0..65535,
                       bits 0/1). Last-good values when stale=True.
        elements:      Decoded element values (data_type stride applied,
                       scale_factor included) — display-ready.
        read_success:  True if the last poll fully succeeded.
        error:         Error text when read_success is False.
        stale:         True when read_success is False but raw_words/elements
                       still hold the previous successful poll.
        timestamp:     UTC timestamp of this snapshot.
    """
    block_id: int
    name: str
    start_address: int
    register_type: str
    count: int
    raw_words: list[int]
    elements: list[float]
    read_success: bool
    error: str
    stale: bool
    timestamp: datetime


@dataclass
class PLCStatus:
    """
    Thread-safe snapshot of the PLC connection and status bar state.

    Fields:
        is_connected:           Current connection state.
        protocol:               TCP or RTU.
        host_or_port:           IP address or COM port.
        quality:                Dictionary from driver.get_quality_stats().
        last_updated:           UTC timestamp of last poll cycle.
        message_register_value: Current value of the configured status register.
        message_text:           Resolved text for the current value.
        message_color:          Resolved UI color (green, red, etc.).
    """
    is_connected: bool = False
    protocol: str = "TCP"
    host_or_port: str = ""
    quality: dict = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now())
    message_register_value: int = 0
    message_text: str = "INITIALIZING..."
    message_color: str = "white"


class PLCDataModel:
    """
    Central thread-safe repository for all live PLC data.

    The ConnectionManager (background thread) writes to this model,
    and the UI (main thread) reads from it to update dashboards.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._readings: dict[int, RegisterReading] = {}  # key: register_id
        self._block_readings: dict[int, BlockReading] = {}  # key: block_id
        self._status = PLCStatus()

    def update_reading(self, register_id: int, reading: RegisterReading) -> None:
        """Atomic update of a single register reading."""
        with self._lock:
            self._readings[register_id] = reading

    def get_reading(self, register_id: int) -> RegisterReading | None:
        """Returns a snapshot of a single register reading."""
        with self._lock:
            return self._readings.get(register_id)

    def get_all_readings(self) -> dict[int, RegisterReading]:
        """Returns a copy of the entire readings dictionary."""
        with self._lock:
            return self._readings.copy()

    def get_readings_by_ids(self, ids: list[int]) -> dict[int, RegisterReading]:
        """Returns readings for a specific subset of IDs."""
        with self._lock:
            return {
                rid: self._readings[rid]
                for rid in ids
                if rid in self._readings
            }

    def update_status(self, status: PLCStatus) -> None:
        """Atomic update of the global PLC status."""
        with self._lock:
            self._status = status

    # ── Data block readings ─────────────────────────────────────────

    def update_block_reading(self, block_id: int, reading: BlockReading) -> None:
        """Atomic update of a single block reading."""
        with self._lock:
            self._block_readings[block_id] = reading

    def get_block_reading(self, block_id: int) -> BlockReading | None:
        """Returns a snapshot of a single block reading."""
        with self._lock:
            return self._block_readings.get(block_id)

    def get_all_block_readings(self) -> dict[int, BlockReading]:
        """Returns a copy of all block readings."""
        with self._lock:
            return self._block_readings.copy()

    def get_status(self) -> PLCStatus:
        """Returns a snapshot of the current PLC status."""
        with self._lock:
            # dataclasses are mutable; we return the object but UI should
            # treat it as a read-only snapshot.
            return self._status

    def reset(self) -> None:
        """Clears all readings and resets status to default."""
        with self._lock:
            self._readings.clear()
            self._block_readings.clear()
            self._status = PLCStatus()
