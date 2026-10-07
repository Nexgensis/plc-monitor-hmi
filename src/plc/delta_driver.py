"""
delta_driver.py — Universal PLC Monitor
Delta DVP / AS series via Modbus TCP.

Tested hardware:
    DVP-ES2, DVP-EH3, DVP-SX2, DVP-SS2, DVP-14SS2,
    AS200, AS300 series (Modbus TCP via built-in port or DVPEN01 module).

Modbus address mapping (Delta):
    D register n  → holding address = DELTA_HOLDING_BASE + n   (= n, same as Mitsubishi)
    M coil n      → coil address    = DELTA_COIL_BASE + n      (= 2048 + n)
    X discrete n  → discrete addr   = DELTA_X_BASE + n         (= 1024 + n)
    Y coil (oct)  → coil address    = DELTA_Y_BASE + decimal   (= 1280 + dec)

The ONLY difference from MitsubishiDriver is the coil and discrete input
base offsets. All translation is handled by validators.compute_modbus_address()
with brand='delta', so this file contains zero hardcoded numeric offsets.

Inheritance strategy:
    DeltaDriver inherits MitsubishiDriver and overrides:
      - brand attribute → 'delta'
      - read_registers() → passes brand='delta' to compute_modbus_address()
      - write_register() → passes brand='delta' to compute_modbus_address()
    connect(), disconnect(), is_connected(), write_coil_pulse() are
    identical to MitsubishiDriver and are NOT overridden.
"""
from __future__ import annotations

import logging
import time

from .mitsubishi_driver import MitsubishiDriver
from .base_driver import PLCReadResult, PLCWriteResult
from src.utils.validators import compute_modbus_address

logger = logging.getLogger(__name__)

_BRAND = "delta"


class DeltaDriver(MitsubishiDriver):
    """
    Modbus TCP driver for Delta DVP / AS series PLCs.

    Inherits the full TCP connection lifecycle from MitsubishiDriver.
    Only overrides read_registers() and write_register() to pass
    brand='delta' into compute_modbus_address(), producing the correct
    coil (2048 + M) and discrete (1024 + X) offsets for Delta hardware.

    Tested series:
        DVP-ES2, DVP-EH3, DVP-SX2, DVP-SS2, DVP-14SS2,
        AS200, AS300
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
            host:       Delta PLC IP address (must be non-empty).
            port:       Modbus TCP port (default 502).
            slave_id:   Modbus Unit ID (default 1).
            timeout_ms: Request timeout in milliseconds.

        Raises:
            ValueError: If host is empty.
        """
        super().__init__(host, port, slave_id, timeout_ms)
        # Override the brand set by MitsubishiDriver.__init__ via PLCDriver
        self.brand = _BRAND
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(
            "DeltaDriver created: host=%s port=%d slave=%d",
            host, port, slave_id,
        )

    # ------------------------------------------------------------------
    # Universal read — Delta address formula
    # ------------------------------------------------------------------

    def read_registers(
        self,
        plc_address: int,
        register_type: str,
        count: int = 1,
    ) -> PLCReadResult:
        """
        Reads registers using Delta DVP address mapping.

        Delegates to the same pymodbus calls as MitsubishiDriver but
        derives the Modbus address with brand='delta' so that:
            M coil 10  → coil address 2058  (2048 + 10)
            X input 5  → discrete addr 1029 (1024 + 5)
            D register 100 → holding addr 100 (unchanged)

        Args:
            plc_address:   PLC-native address (D-number, M-number, X-number).
            register_type: 'HOLDING', 'COIL', 'DISCRETE', or 'INPUT'.
            count:         Number of consecutive words/bits to read.

        Returns:
            PLCReadResult with raw 16-bit words. Never raises.
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
                    self.logger.error("Modbus read error: %s", str(resp))
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
    # Universal write — Delta address formula
    # ------------------------------------------------------------------

    def write_register(
        self,
        plc_address: int,
        register_type: str,
        value: int,
    ) -> PLCWriteResult:
        """
        Writes to a HOLDING register or COIL using Delta address mapping.

        For COIL writes, uses brand='delta' so M10 maps to coil 2059,
        not Mitsubishi's coil 11.

        Args:
            plc_address:   PLC-native D-number or M-number.
            register_type: 'HOLDING' or 'COIL'.
            value:         Integer value (COIL: 0=False, non-zero=True).

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

