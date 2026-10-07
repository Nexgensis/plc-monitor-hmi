"""
mitsubishi_driver.py — Universal PLC Monitor
Mitsubishi FX5U / iQ-F series via Modbus TCP.

Tested hardware:
    FX5U-32MR/ES, FX5U-64MT/ESS, iQ-F FX5UC
    Communication via built-in Ethernet port or FX5-ENE-MB module.

Modbus address mapping (Mitsubishi):
    D register n  → holding address = MITSUBISHI_HOLDING_BASE + n  (= n)
    M coil n      → coil address    = MITSUBISHI_COIL_BASE + n     (= 1 + n)
    X discrete n  → discrete addr   = MITSUBISHI_X_BASE + n        (= 0x400 + n)
    Y coil (oct)  → coil address    = MITSUBISHI_Y_BASE + decimal  (= 1280 + dec)

All translation performed by validators.compute_modbus_address() so that this
file contains zero hardcoded numeric offsets.
"""
from __future__ import annotations

import logging
import time

from pymodbus.client import ModbusTcpClient

from .base_driver import PLCDriver, PLCReadResult, PLCWriteResult
from src.utils.validators import compute_modbus_address

logger = logging.getLogger(__name__)

_BRAND = "mitsubishi"


class MitsubishiDriver(PLCDriver):
    """
    Modbus TCP driver for Mitsubishi FX / iQ-F series PLCs.

    pymodbus 3.x API is used throughout (slave= keyword, not unit=).
    All read/write methods catch every exception and return a result
    object — they never propagate exceptions to the caller.
    """

    def __init__(
        self,
        host: str,
        port: int,
        slave_id: int = 1,
        timeout_ms: int = 3000,
    ) -> None:
        """
        Args:
            host:       PLC IP address (must be non-empty; set in CONFIG screen).
            port:       Modbus TCP port (default 502).
            slave_id:   Modbus Unit ID (default 1).
            timeout_ms: Request timeout in milliseconds.

        Raises:
            ValueError: If host is empty — guards against unconfigured profiles.
        """
        if not host or not host.strip():
            raise ValueError(
                "PLC host IP address is not configured. "
                "Go to CONFIG → PLC Connection to set it."
            )
        super().__init__(_BRAND, host, port, slave_id, timeout_ms)
        self._host      = host.strip()
        self._port      = port
        self._slave_id  = slave_id
        self._timeout   = timeout_ms / 1000.0   # pymodbus expects seconds
        self._client: ModbusTcpClient | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Opens the TCP socket and verifies communication.
        Reuses the existing client instance if available.
        """
        with self._lock:
            try:
                # If already connected, skip
                if self._client and self._client.connected:
                    self._connected = True
                    return True

                # Create client if missing
                if not self._client:
                    self._client = ModbusTcpClient(
                        host=self._host,
                        port=self._port,
                        timeout=self._timeout,
                    )

                # Attempt connection
                ok = self._client.connect()
                if not ok:
                    self.logger.error(
                        "TCP connect to %s:%d refused", self._host, self._port
                    )
                    self._connected = False
                    return False

                # Verify comms with a single-register read (address 0)
                probe = self._client.read_holding_registers(
                    address=0, count=1, slave=self._slave_id
                )
                self._connected = not probe.isError()
                if not self._connected:
                    self.logger.warning(
                        "Connected to %s:%d but probe read failed: %s",
                        self._host, self._port, probe,
                    )
                else:
                    self.logger.info(
                        "Mitsubishi TCP connected: %s:%d slave=%d",
                        self._host, self._port, self._slave_id,
                    )
                return self._connected

            except Exception as exc:
                self.logger.error("MitsubishiDriver.connect error: %s", exc)
                self._connected = False
                return False

    def disconnect(self) -> None:
        """Closes the TCP socket. Never raises."""
        with self._lock:
            try:
                if self._client:
                    self._client.close()
            except Exception as exc:
                self.logger.debug("MitsubishiDriver.disconnect error: %s", exc)
            finally:
                self._connected = False

    def is_connected(self) -> bool:
        """Returns the cached connection state from the last operation."""
        return self._connected

    # ------------------------------------------------------------------
    # Universal read
    # ------------------------------------------------------------------

    def read_registers(
        self,
        plc_address: int,
        register_type: str,
        count: int = 1,
    ) -> PLCReadResult:
        """
        Reads one or more registers/coils/inputs using the appropriate
        Modbus function code.

        Args:
            plc_address:   D-number, M-number, or X-number as in the PLC program.
            register_type: 'HOLDING', 'COIL', 'DISCRETE', or 'INPUT'.
            count:         Number of consecutive words/bits to read.

        Returns:
            PLCReadResult with raw unsigned 16-bit words in .values.
            COIL/DISCRETE bits are returned as 0 or 1 (not Python bool).
        """
        if not self._client:
            return PLCReadResult(
                success=False, error="Not connected", register_address=plc_address
            )

        modbus_addr = compute_modbus_address(plc_address, register_type, _BRAND)
        t0 = time.monotonic()

        with self._lock:
            try:
                if register_type == "HOLDING":
                    resp = self._client.read_holding_registers(
                        address=modbus_addr, count=count, slave=self._slave_id
                    )
                    values = [] if resp.isError() else list(resp.registers)

                elif register_type == "COIL":
                    resp = self._client.read_coils(
                        address=modbus_addr, count=count, slave=self._slave_id
                    )
                    values = (
                        [] if resp.isError()
                        else [1 if b else 0 for b in resp.bits[:count]]
                    )

                elif register_type == "DISCRETE":
                    resp = self._client.read_discrete_inputs(
                        address=modbus_addr, count=count, slave=self._slave_id
                    )
                    values = (
                        [] if resp.isError()
                        else [1 if b else 0 for b in resp.bits[:count]]
                    )

                elif register_type == "INPUT":
                    resp = self._client.read_input_registers(
                        address=modbus_addr, count=count, slave=self._slave_id
                    )
                    values = [] if resp.isError() else list(resp.registers)

                else:
                    return PLCReadResult(
                        success=False,
                        error=f"Unknown register_type: {register_type!r}",
                        register_address=modbus_addr,
                    )

                ms      = (time.monotonic() - t0) * 1000.0
                success = not resp.isError() and bool(values)
                self._track_request(success, ms)

                if success:
                    self._connected = True
                    return PLCReadResult(
                        success=True,
                        values=values,
                        register_address=modbus_addr,
                        count=count,
                        response_time_ms=ms,
                    )
                else:
                    self._connected = False
                    return PLCReadResult(
                        success=False,
                        error=str(resp),
                        register_address=modbus_addr,
                        response_time_ms=ms,
                    )

            except Exception as exc:
                ms = (time.monotonic() - t0) * 1000.0
                self._track_request(False, ms)
                self._connected = False
                self.logger.error(
                    "read_registers plc_addr=%d type=%s count=%d: %s",
                    plc_address, register_type, count, exc,
                )
                return PLCReadResult(
                    success=False,
                    error=str(exc),
                    register_address=modbus_addr,
                    response_time_ms=ms,
                )


    # ------------------------------------------------------------------
    # Universal write
    # ------------------------------------------------------------------

    def write_register(
        self,
        plc_address: int,
        register_type: str,
        value: int,
    ) -> PLCWriteResult:
        """
        Writes to a single HOLDING register (FC06) or COIL (FC05).

        Args:
            plc_address:   PLC-native D-number or M-number.
            register_type: 'HOLDING' or 'COIL'. Other types return failure.
            value:         Integer to write. For COIL: 0=False, non-zero=True.

        Returns:
            PLCWriteResult. Never raises.
        """
        if not self._client:
            return PLCWriteResult(
                success=False,
                error="Not connected",
                register_address=plc_address,
            )

        modbus_addr = compute_modbus_address(plc_address, register_type, _BRAND)

        with self._lock:
            try:
                if register_type == "HOLDING":
                    resp = self._client.write_register(
                        address=modbus_addr, value=value, slave=self._slave_id
                    )
                elif register_type == "COIL":
                    resp = self._client.write_coil(
                        address=modbus_addr, value=bool(value), slave=self._slave_id
                    )
                else:
                    return PLCWriteResult(
                        success=False,
                        error=f"register_type {register_type!r} is not writable",
                        register_address=modbus_addr,
                    )

                success = not resp.isError()
                self._track_request(success, 0.0)
                if not success:
                    self._connected = False

                return PLCWriteResult(
                    success=success,
                    register_address=modbus_addr,
                    value_written=value,
                    error="" if success else str(resp),
                )

            except Exception as exc:
                self._track_request(False, 0.0)
                self._connected = False
                self.logger.error(
                    "write_register plc_addr=%d type=%s value=%s: %s",
                    plc_address, register_type, value, exc,
                )
                return PLCWriteResult(
                    success=False,
                    error=str(exc),
                    register_address=modbus_addr,
                    value_written=value,
                )


    # ------------------------------------------------------------------
    # Bulk block write (FC16 / FC0F) — Phase 2: data blocks
    # ------------------------------------------------------------------

    def write_block(
        self,
        start_address: int,
        register_type: str,
        values: list[int],
    ) -> PLCWriteResult:
        """
        Bulk-write a contiguous range using FC16 (HOLDING) or FC0F (COIL).

        Values are written in chunks of at most
        MAX_WRITE_REGS_PER_REQUEST / MAX_WRITE_BITS_PER_REQUEST words/bits.
        Address translation uses self.brand, so Mitsubishi, Delta, and both
        RTU variants share this single implementation.

        Args:
            start_address: PLC-native address of the first element.
            register_type: 'HOLDING' or 'COIL' (other types fail).
            values:        Words 0..65535 (HOLDING) or bits 0/1 (COIL).

        Returns:
            PLCWriteResult. On failure, .error reports how many elements
            were written before the failure (partial write), and
            .value_written always carries the full intended list.
            Never raises.
        """
        if not self._client:
            return PLCWriteResult(
                success=False,
                error="Not connected",
                register_address=start_address,
                value_written=values,
            )
        if not values:
            return PLCWriteResult(
                success=False,
                error="Empty value list",
                register_address=start_address,
            )

        # --- Normalize and validate values -----------------------------
        norm: list[int] = []
        if register_type == "HOLDING":
            for i, v in enumerate(values):
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    return PLCWriteResult(
                        success=False,
                        register_address=start_address,
                        value_written=values,
                        error=f"value[{i}] is not an integer: {v!r}",
                    )
                if not (0 <= iv <= 65535):
                    return PLCWriteResult(
                        success=False,
                        register_address=start_address,
                        value_written=values,
                        error=f"value[{i}]={iv} out of range 0-65535",
                    )
                norm.append(iv)
            chunk_max = self.MAX_WRITE_REGS_PER_REQUEST
        elif register_type == "COIL":
            for i, v in enumerate(values):
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    return PLCWriteResult(
                        success=False,
                        register_address=start_address,
                        value_written=values,
                        error=f"value[{i}] is not an integer: {v!r}",
                    )
                if iv not in (0, 1):
                    return PLCWriteResult(
                        success=False,
                        register_address=start_address,
                        value_written=values,
                        error=f"value[{i}]={iv} invalid for COIL (expected 0 or 1)",
                    )
                norm.append(iv)
            chunk_max = self.MAX_WRITE_BITS_PER_REQUEST
        else:
            return PLCWriteResult(
                success=False,
                register_address=start_address,
                value_written=values,
                error=f"register_type {register_type!r} is not writable",
            )

        base_addr = compute_modbus_address(start_address, register_type, self.brand)
        written = 0

        for offset in range(0, len(norm), chunk_max):
            chunk = norm[offset:offset + chunk_max]
            modbus_addr = compute_modbus_address(
                start_address + offset, register_type, self.brand
            )
            tc = time.monotonic()
            try:
                with self._lock:
                    if register_type == "HOLDING":
                        resp = self._client.write_registers(
                            address=modbus_addr,
                            values=list(chunk),
                            slave=self._slave_id,
                        )
                    else:  # COIL
                        resp = self._client.write_coils(
                            address=modbus_addr,
                            values=[bool(v) for v in chunk],
                            slave=self._slave_id,
                        )
                success = not resp.isError()
                err = "" if success else str(resp)
            except Exception as exc:
                success = False
                err = str(exc)
            chunk_ms = (time.monotonic() - tc) * 1000.0
            self._track_request(success, chunk_ms)

            if not success:
                self._connected = False
                self.logger.error(
                    "write_block %s %d (+%d of %d): %s",
                    register_type, start_address + offset,
                    len(chunk), len(norm), err,
                )
                return PLCWriteResult(
                    success=False,
                    register_address=modbus_addr,
                    value_written=norm,
                    error=(
                        f"Block write failed at {register_type} "
                        f"{start_address + offset} (+{len(chunk)}): {err} "
                        f"({written} of {len(norm)} values written before failure)"
                    ),
                )
            written += len(chunk)

        self._connected = True
        return PLCWriteResult(
            success=True,
            register_address=base_addr,
            value_written=norm,
        )

    # ------------------------------------------------------------------
    # Pulse write (momentary control signal)
    # ------------------------------------------------------------------

    def write_coil_pulse(
        self,
        plc_address: int,
        on_value: int = 1,
        pulse_ms: int = 500,
    ) -> PLCWriteResult:
        """
        Writes *on_value* to a coil, waits *pulse_ms* milliseconds, then
        writes 0. Suitable for momentary Start / ACK / Reset signals.

        Returns the result of the initial ON write. Never raises.
        """
        result = self.write_register(plc_address, "COIL", on_value)
        if result.success and pulse_ms > 0:
            time.sleep(pulse_ms / 1000.0)
            self.write_register(plc_address, "COIL", 0)
        return result
