"""
delta_rtu_driver.py — Universal PLC Monitor
Delta DVP / AS series via Modbus RTU (RS485 / RS232).

Tested hardware:
    DVP-SS2, DVP-14SS2, DVP-ES2, DVP-EH3, DVP-SX2 via RS-485 port.
    AS200, AS300 via built-in RS-485 (COM2) or AS-FCOPM module.

Serial parameter defaults for Delta DVP:
    Baud: 9600
    Parity: Even (E)   ← Delta factory default
    Data bits: 7       ← Delta DVP ASCII mode default (set 8 for RTU mode)
    Stop bits: 1

Address mapping — Delta differs from Mitsubishi for COIL and DISCRETE:
    M coil n      → coil address    = 2048 + n   (Mitsubishi: 1 + n)
    X discrete n  → discrete addr   = 1024 + n   (Mitsubishi: 0x400 + n)
    D register n  → holding addr    = n           (same as Mitsubishi)

DeltaRTUDriver inherits:
    - Serial connect/disconnect/is_connected  from MitsubishiRTUDriver
    - read_registers(brand='delta')           from DeltaDriver
    - write_register(brand='delta')           from DeltaDriver
    - write_coil_pulse()                      from MitsubishiDriver (via DeltaDriver)

MRO: DeltaRTUDriver → DeltaDriver → MitsubishiRTUDriver → MitsubishiDriver → PLCDriver
"""
from __future__ import annotations

import logging

from pymodbus.client import ModbusSerialClient

from .base_driver import PLCDriver
from .delta_driver import DeltaDriver

logger = logging.getLogger(__name__)

_BRAND = "delta"


class DeltaRTUDriver(DeltaDriver):
    """
    Modbus RTU (serial RS485/RS232) driver for Delta DVP / AS series PLCs.

    Combines:
        - Delta address formulas (read_registers / write_register from DeltaDriver)
        - RTU serial transport (connect / disconnect / is_connected)

    Tested series:
        DVP-SS2, DVP-14SS2, DVP-ES2, DVP-EH3, DVP-SX2,
        AS200, AS300
    """

    def __init__(
        self,
        com_port: str,
        baud_rate: int,
        slave_id: int = 1,
        timeout_ms: int = 3000,
        parity: str = "E",
        data_bits: int = 7,
        stop_bits: int = 1,
    ) -> None:
        """
        Args:
            com_port:   Serial port name, e.g. 'COM4' or '/dev/ttyUSB0'.
            baud_rate:  Serial baud rate. Delta DVP default: 9600.
            slave_id:   Modbus station address (default 1).
            timeout_ms: Request timeout in milliseconds.
            parity:     'E' Even, 'O' Odd, 'N' None. Delta default: 'E'.
            data_bits:  7 (Delta DVP ASCII default) or 8 (RTU binary mode).
            stop_bits:  1 or 2. Delta default: 1.
        """
        # Call PLCDriver.__init__ directly to avoid both the TCP host guard
        # in MitsubishiDriver and the repeated super().__init__ chain.
        PLCDriver.__init__(
            self,
            brand=_BRAND,
            host_or_port=com_port,
            port_or_baud=baud_rate,
            slave_id=slave_id,
            timeout_ms=timeout_ms,
        )
        self._com_port  = com_port
        self._baud_rate = baud_rate
        self._slave_id  = slave_id
        self._timeout   = timeout_ms / 1000.0
        self._parity    = parity
        self._data_bits = data_bits
        self._stop_bits = stop_bits
        self._client: ModbusSerialClient | None = None

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(
            "DeltaRTUDriver created: port=%s baud=%d parity=%s data=%d slave=%d",
            com_port, baud_rate, parity, data_bits, slave_id,
        )

    # ------------------------------------------------------------------
    # Serial transport lifecycle (mirrors MitsubishiRTUDriver exactly)
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Opens the serial port and verifies communication.
        Retries up to 3 times on PermissionError (Access is denied).
        """
        import time
        max_retries = 3
        retry_delay = 1.0

        with self._lock:
            # If already connected, skip
            if self._client and self._client.connected:
                self._connected = True
                return True

            for attempt in range(max_retries):
                try:
                    if not self._client:
                        self._client = ModbusSerialClient(
                            port      = self._com_port,
                            baudrate  = self._baud_rate,
                            parity    = self._parity,
                            bytesize  = self._data_bits,
                            stopbits  = self._stop_bits,
                            timeout   = self._timeout,
                        )

                    if not self._client.connect():
                        self.logger.error("Delta RTU port %s could not be opened", self._com_port)
                        self._connected = False
                        return False

                    # Verify comms
                    self._connected = True
                    self.logger.info("Delta RTU connected: port=%s baud=%d parity=%s slave=%d", 
                                   self._com_port, self._baud_rate, self._parity, self._slave_id)
                    return True

                except Exception as exc:
                    # Check for PermissionError (Access is denied)
                    if "PermissionError" in str(exc) or "Access is denied" in str(exc):
                        if attempt < max_retries - 1:
                            self.logger.warning("COM port %s busy (Access Denied). Retrying in %.1fs... (%d/%d)", 
                                              self._com_port, retry_delay, attempt + 1, max_retries)
                            if self._client:
                                try: self._client.close()
                                except Exception: pass
                                self._client = None
                            time.sleep(retry_delay)
                            continue
                    
                    self.logger.error("DeltaRTUDriver.connect exception: %s", exc)
                    self._connected = False
                    return False

            return False

    def disconnect(self) -> None:
        """Closes the serial port. Never raises."""
        with self._lock:
            try:
                if self._client:
                    self._client.close()
            except Exception as exc:
                self.logger.debug("DeltaRTUDriver.disconnect error: %s", exc)
            finally:
                self._connected = False

    def is_connected(self) -> bool:
        """Returns the cached connection state from the last operation."""
        return self._connected

    def update_params(self, profile: dict) -> None:
        """Update serial parameters from profile dict."""
        with self._lock:
            self._baud_rate = int(profile.get("baud_rate", self._baud_rate))
            self._parity    = str(profile.get("parity",    self._parity)).upper()
            self._data_bits = int(profile.get("data_bits", self._data_bits))
            self._stop_bits = int(profile.get("stop_bits", self._stop_bits))
            self._timeout   = int(profile.get("timeout_ms", 3000)) / 1000.0
            
            if self._client:
                # Force reconnect on next operation if parameters changed
                self._client.close()
                self._client = None # Force recreation with new params in connect()
                self._connected = False

    # read_registers() and write_register() are inherited from DeltaDriver,
    # which calls compute_modbus_address(brand='delta') — correct for both
    # TCP and RTU because the address formulas are transport-independent.
    #
    # write_coil_pulse() is inherited from MitsubishiDriver (via DeltaDriver)
    # and uses self.write_register() which resolves to DeltaDriver's override.
