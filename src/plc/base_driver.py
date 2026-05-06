"""
base_driver.py — Universal PLC Monitor
Abstract base class and shared data structures for all PLC brand/protocol
drivers.

Design rules (Schema v4.0):
  - NO hardcoded register addresses anywhere in this file.
  - All addresses originate from register_library.register_address.
  - Address translation (PLC-native → Modbus protocol) is done inside
    each concrete driver using validators.compute_modbus_address().
  - read_registers() / write_register() are the ONLY two I/O primitives.
    Callers decode data types with validators.convert_raw_to_value().
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PLCReadResult:
    """
    Container for the outcome of a single PLC read operation.

    Fields:
        success:          True if Modbus returned valid data.
        values:           Raw 16-bit unsigned register words.
                          Callers decode using convert_raw_to_value().
        error:            Human-readable error string (empty on success).
        register_address: The Modbus protocol address that was polled.
        count:            Number of words requested.
        response_time_ms: Round-trip time for the Modbus request.
                          Used by get_quality_stats() for monitoring.
    """
    success: bool
    values: list[int] = field(default_factory=list)
    error: str = ""
    register_address: int = 0
    count: int = 0
    response_time_ms: float = 0.0


@dataclass
class PLCWriteResult:
    """
    Container for the outcome of a single PLC write operation.

    Fields:
        success:          True if the write was accepted by the PLC.
        register_address: The Modbus protocol address that was written.
        value_written:    The value sent to the PLC.
        value_readback:   Value read back after write (None if not verified).
        verified:         True if readback == value_written.
        error:            Human-readable error string (empty on success).
    """
    success: bool
    register_address: int = 0
    value_written: Any = None
    value_readback: Any = None
    verified: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Abstract base driver
# ---------------------------------------------------------------------------

class PLCDriver(ABC):
    """
    Abstract interface for all PLC brand/protocol implementations.

    Concrete subclasses (MitsubishiDriver, DeltaDriver, …) implement the
    three abstract methods. All other logic lives here.

    Address contract:
        - Callers pass PLC-programmer addresses (D-number, M-number, etc.).
        - Each concrete driver converts to Modbus addresses internally via
          validators.compute_modbus_address(plc_address, register_type, brand).
        - This file never references specific numeric addresses.
    """

    def __init__(
        self,
        brand: str,
        host_or_port: str,
        port_or_baud: int,
        slave_id: int = 1,
        timeout_ms: int = 3000,
    ) -> None:
        """
        Args:
            brand:         PLC brand string ('mitsubishi', 'delta', 'generic').
            host_or_port:  IP address (TCP) or COM port string (RTU).
            port_or_baud:  TCP port number or serial baud rate.
            slave_id:      Modbus Unit ID / station address.
            timeout_ms:    Request timeout in milliseconds.
        """
        self.brand         = brand
        self.slave_id      = slave_id
        self.timeout_ms    = timeout_ms
        self._connected    = False

        # Quality tracking counters (updated by _track_request)
        self._total_requests  : int   = 0
        self._failed_requests : int   = 0
        self._consec_errors   : int   = 0
        self._avg_response_ms : float = 0.0
        self._lock            = threading.Lock()

        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Abstract interface — implemented by every concrete driver
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """
        Establishes the communication channel to the PLC.
        Returns True on success, False on failure. Never raises.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """
        Closes the communication channel. Never raises.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Returns the current connection state.
        Should reflect the last known-good communication, not a live probe.
        """
        ...

    @abstractmethod
    def read_registers(
        self,
        plc_address: int,
        register_type: str,
        count: int = 1,
    ) -> PLCReadResult:
        """
        Universal read method for any register type.

        Args:
            plc_address:   PLC-native address (e.g. 100 for D100, 10 for M10).
                           This is the number as written in the PLC program.
            register_type: One of 'HOLDING', 'COIL', 'DISCRETE', 'INPUT'.
            count:         Number of consecutive registers/coils to read.

        Returns:
            PLCReadResult with raw 16-bit words in .values list.
            The caller converts words to engineering values using
            validators.convert_raw_to_value().

        Implementation must:
            1. Call compute_modbus_address(plc_address, register_type, brand)
               to get the Modbus protocol address.
            2. Call the appropriate pymodbus function.
            3. Call self._track_request(success, response_ms).
            4. Never raise — return PLCReadResult(success=False, error=...).
        """
        ...

    @abstractmethod
    def write_register(
        self,
        plc_address: int,
        register_type: str,
        value: int,
    ) -> PLCWriteResult:
        """
        Write a single register or coil.

        Args:
            plc_address:   PLC-native address.
            register_type: 'HOLDING' or 'COIL' (write-capable types only).
            value:         Integer value to write.
                           For COIL: non-zero = True, 0 = False.

        Returns:
            PLCWriteResult. Never raises.
        """
        ...

    @abstractmethod
    def write_coil_pulse(
        self,
        plc_address: int,
        on_value: int = 1,
        pulse_ms: int = 500,
    ) -> PLCWriteResult:
        """
        Write *on_value* to a coil, wait *pulse_ms*, then write 0.
        Used for momentary control signals (Start, ACK, Reset).

        Returns the result of the initial write. Never raises.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helper — contiguous batch read optimiser
    # ------------------------------------------------------------------

    def read_batch_by_type(
        self,
        addresses: list[int],
        register_type: str,
    ) -> PLCReadResult:
        """
        Read multiple PLC-native addresses in ONE Modbus request.

        Finds the min and max PLC address, reads the full contiguous block,
        then extracts only the requested offsets. This minimises round trips
        when polling many registers on each scan cycle.

        Constraint: all addresses must share the same register_type.

        Args:
            addresses:     List of PLC-native addresses (D-numbers, M-numbers…).
            register_type: Common Modbus table for all addresses.

        Returns:
            PLCReadResult whose .values list corresponds index-for-index
            with the input *addresses* list. Returns failure result on error.
        """
        if not addresses:
            return PLCReadResult(success=False, error="Empty address list")

        min_addr = min(addresses)
        max_addr = max(addresses)
        span     = max_addr - min_addr + 1

        # Single bulk read of the contiguous block
        bulk = self.read_registers(min_addr, register_type, span)
        if not bulk.success:
            return bulk

        # Extract only the values that were requested, preserving input order
        extracted = [
            bulk.values[addr - min_addr]
            if (addr - min_addr) < len(bulk.values) else 0
            for addr in addresses
        ]
        return PLCReadResult(
            success=True,
            values=extracted,
            register_address=bulk.register_address,
            count=len(addresses),
            response_time_ms=bulk.response_time_ms,
        )

    # ------------------------------------------------------------------
    # Quality / diagnostics
    # ------------------------------------------------------------------

    def get_quality_stats(self) -> dict:
        """
        Returns connection quality metrics for the status bar and CONFIG
        diagnostics panel.

        Keys:
            total_requests    — total Modbus requests since last reset.
            failed_requests   — count of failed requests.
            success_rate_pct  — percentage success rate (0–100).
            avg_response_ms   — exponential moving average response time.
            consecutive_errors — run of failures without a success.
        """
        total = max(self._total_requests, 1)
        return {
            "total_requests":     self._total_requests,
            "failed_requests":    self._failed_requests,
            "success_rate_pct":   round((1 - self._failed_requests / total) * 100, 1),
            "avg_response_ms":    round(self._avg_response_ms, 1),
            "consecutive_errors": self._consec_errors,
        }

    def reset_stats(self) -> None:
        """Resets all quality counters. Call after reconnect."""
        self._total_requests  = 0
        self._failed_requests = 0
        self._consec_errors   = 0
        self._avg_response_ms = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track_request(self, success: bool, response_ms: float) -> None:
        """
        Called by concrete read/write implementations after every Modbus
        operation to update quality metrics.

        Uses an exponential moving average (α=0.2) for response time so
        that brief spikes don't dominate the displayed average.
        """
        self._total_requests += 1
        if not success:
            self._failed_requests += 1
            self._consec_errors   += 1
            if self._consec_errors >= 5:
                self.logger.warning(
                    "%s: %d consecutive Modbus errors — PLC may be unreachable",
                    self.brand,
                    self._consec_errors,
                )
        else:
            self._consec_errors = 0
            alpha = 0.2
            self._avg_response_ms = (
                alpha * response_ms + (1.0 - alpha) * self._avg_response_ms
            )

    def update_params(self, profile: dict) -> None:
        """
        Updates driver parameters based on the provided profile.

        Args:
            profile: Dictionary containing parameter keys and values.
        """
        self.slave_id = int(profile.get("slave_id", self.slave_id))
        self.timeout_ms = int(profile.get("timeout_ms", self.timeout_ms))
        # Add additional parameter updates as needed
        pass
