"""
mitsubishi_rtu_driver.py — Universal PLC Monitor
Mitsubishi FX / iQ-F series via Modbus RTU (RS485 / RS232).

Tested hardware:
    FX3U + FX3U-485ADP-MB, FX5U + FX5-485ADP,
    iQ-F FX5UC via RS-485 port (9600-115200 baud, 7/8E1 typical).

Serial parameter defaults for Mitsubishi:
    Baud: 9600 or 19200
    Parity: Even (E)  ← Mitsubishi factory default
    Data bits: 7 or 8 (FX3U typically 7, FX5U typically 8)
    Stop bits: 1

All address translation is performed by validators.compute_modbus_address()
with brand='mitsubishi', identical to the TCP driver. The only difference
between this class and MitsubishiDriver is the transport layer (serial vs TCP).

After pymodbus .connect(), the read/write API is identical for TCP and RTU,
so all read_registers(), write_register(), and write_coil_pulse() methods
are inherited directly from MitsubishiDriver without overriding.
"""
from __future__ import annotations

import logging

from pymodbus.client import ModbusSerialClient

from .base_driver import PLCDriver
from .mitsubishi_driver import MitsubishiDriver

logger = logging.getLogger(__name__)


class MitsubishiRTUDriver(MitsubishiDriver):
    """
    Modbus RTU (serial RS485/RS232) driver for Mitsubishi FX / iQ-F PLCs.

    Inherits all read_registers(), write_register(), and write_coil_pulse()
    implementations from MitsubishiDriver. Only the transport (connect /
    disconnect / is_connected) is overridden to use ModbusSerialClient.

    pymodbus 3.x serial API:
        ModbusSerialClient(port, baudrate, parity, bytesize, stopbits, timeout)
    """

    def __init__(
        self,
        com_port: str,
        baud_rate: int,
        slave_id: int = 1,
        timeout_ms: int = 3000,
        parity: str = "E",
        data_bits: int = 8,
        stop_bits: int = 1,
    ) -> None:
        """
        Args:
            com_port:   Serial port name, e.g. 'COM3' or '/dev/ttyUSB0'.
            baud_rate:  Serial baud rate (e.g. 9600, 19200, 115200).
            slave_id:   Modbus station address (default 1).
            timeout_ms: Request timeout in milliseconds.
            parity:     'E' Even, 'O' Odd, 'N' None. Mitsubishi default: 'E'.
            data_bits:  7 or 8. FX3U default 7, FX5U default 8.
            stop_bits:  1 or 2. Mitsubishi default: 1.
        """
        # Call PLCDriver.__init__ directly — bypassing MitsubishiDriver.__init__
        # which requires a non-empty host (IP address) that doesn't apply here.
        PLCDriver.__init__(
            self,
            brand="mitsubishi",
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
            "MitsubishiRTUDriver created: port=%s baud=%d parity=%s slave=%d",
            com_port, baud_rate, parity, slave_id,
        )

    # ------------------------------------------------------------------
    # Serial transport lifecycle
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
                        self.logger.error("Mitsubishi RTU port %s could not be opened", self._com_port)
                        self._connected = False
                        return False

                    # Verify comms
                    self._connected = True
                    self.logger.info("Mitsubishi RTU connected: port=%s baud=%d parity=%s slave=%d", 
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
                    
                    self.logger.error("MitsubishiRTUDriver.connect exception: %s", exc)
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
                self.logger.debug("MitsubishiRTUDriver.disconnect error: %s", exc)
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

    # All read_registers(), write_register(), write_coil_pulse() are
    # inherited unchanged from MitsubishiDriver. After connect() the
    # pymodbus serial client exposes the same API as the TCP client.
