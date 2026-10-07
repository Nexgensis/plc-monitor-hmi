"""
driver_factory.py — Universal PLC Monitor
Creates the correct PLCDriver subclass from a plc_profile dict read from
the database.

Design:
    - Single static method create(profile) does all dispatch.
    - Input is the raw dict from plc_profile table (fetchone result).
    - Raises ValueError with a user-friendly message for misconfigured
      profiles so the UI can surface it directly in a dialog.
    - Never catches the ValueError — caller (ConnectionManager) handles it.
    - Uses timeout_ms (milliseconds) from the new schema v4.0 profile,
      not the old timeout_sec field.
"""
from __future__ import annotations

import logging
import threading

from .base_driver import PLCDriver
from .mitsubishi_driver import MitsubishiDriver
from .mitsubishi_rtu_driver import MitsubishiRTUDriver
from .delta_driver import DeltaDriver
from .delta_rtu_driver import DeltaRTUDriver
from src.utils.constants import (
    PLC_BRAND_MITSUBISHI,
    PLC_BRAND_DELTA,
    PLC_BRAND_GENERIC,
    PLC_PROTOCOL_TCP,
    PLC_PROTOCOL_RTU,
)

logger = logging.getLogger(__name__)


class PLCDriverFactory:
    """
    Factory for PLCDriver instantiation with caching to prevent port conflicts.
    """
    _cache: dict[str, PLCDriver] = {}
    _lock = threading.Lock()

    @staticmethod
    def create(profile: dict, cached: bool = True) -> PLCDriver:
        """
        Instantiate or retrieve the correct PLCDriver subclass.
        Reuses instances for the same connection (host:port or COM port)
        to prevent 'Access is denied' serial port errors.

        Pass cached=False for throwaway drivers (e.g. the connection
        tester) that must never touch or tear down the live connection.
        """
        brand    = str(profile.get("brand",    PLC_BRAND_MITSUBISHI)).lower().strip()
        protocol = str(profile.get("protocol", PLC_PROTOCOL_TCP)).upper().strip()

        # Generate a unique key for this driver class and connection.
        # Brand/protocol are part of the identity because Delta and
        # Mitsubishi use different address conversion logic on the same
        # endpoint.
        if protocol == PLC_PROTOCOL_TCP:
            host = str(profile.get("host", "")).strip()
            port = int(profile.get("port", 502))
            cache_key = f"{brand}:{protocol}:{host}:{port}"
        else:
            com_port = str(profile.get("com_port", "")).strip()
            cache_key = f"{brand}:{protocol}:{com_port}"

        with PLCDriverFactory._lock:
            # If we have a driver for this port already, update it and return it
            if cached and cache_key in PLCDriverFactory._cache:
                driver = PLCDriverFactory._cache[cache_key]
                logger.info("Reusing existing driver for %s", cache_key)
                
                # Update parameters (slave_id, timeout, etc.)
                driver.slave_id = int(profile.get("slave_id", 1))
                driver.timeout_ms = int(profile.get("timeout_ms", 3000))
                # For RTU, we might need to update baud/parity too
                if hasattr(driver, "update_params"):
                    driver.update_params(profile)
                return driver

            # Otherwise, create new
            driver = PLCDriverFactory._create_new(profile)
            if cached:
                PLCDriverFactory._cache[cache_key] = driver
            return driver

    @staticmethod
    def _create_new(profile: dict) -> PLCDriver:
        brand    = str(profile.get("brand",    PLC_BRAND_MITSUBISHI)).lower().strip()
        protocol = str(profile.get("protocol", PLC_PROTOCOL_TCP)).upper().strip()

        if protocol == PLC_PROTOCOL_TCP:
            host = str(profile.get("host", "")).strip()
            if not host:
                raise ValueError("PLC IP address is not configured.")
            port      = int(profile.get("port",       502))
            slave_id  = int(profile.get("slave_id",   1))
            timeout   = int(profile.get("timeout_ms", 3000))

            if brand in (PLC_BRAND_MITSUBISHI, PLC_BRAND_GENERIC):
                return MitsubishiDriver(host, port, slave_id, timeout)
            elif brand == PLC_BRAND_DELTA:
                return DeltaDriver(host, port, slave_id, timeout)

        elif protocol == PLC_PROTOCOL_RTU:
            com_port = str(profile.get("com_port", "")).strip()
            if not com_port:
                raise ValueError("COM port is not configured.")
            baud_rate  = int(profile.get("baud_rate",  9600))
            slave_id   = int(profile.get("slave_id",   1))
            timeout    = int(profile.get("timeout_ms", 3000))
            parity     = str(profile.get("parity",     "E")).upper()
            data_bits  = int(profile.get("data_bits",  8))
            stop_bits  = int(profile.get("stop_bits",  1))

            if brand in (PLC_BRAND_MITSUBISHI, PLC_BRAND_GENERIC):
                return MitsubishiRTUDriver(
                    com_port, baud_rate, slave_id, timeout,
                    parity, data_bits, stop_bits,
                )
            elif brand == PLC_BRAND_DELTA:
                return DeltaRTUDriver(
                    com_port, baud_rate, slave_id, timeout,
                    parity, data_bits, stop_bits,
                )

        raise ValueError(f"Unsupported brand/protocol: {brand}/{protocol}")

    # Alias for backward compatibility
    create_from_profile = create

    @staticmethod
    def invalidate(profile: dict = None) -> None:
        """
        Remove cached driver(s) so the next create() builds fresh.
        If profile is given, only that specific cache entry is removed.
        If None, the entire cache is cleared.
        """
        with PLCDriverFactory._lock:
            if profile is None:
                PLCDriverFactory._cache.clear()
                logger.info("PLCDriverFactory: Cache cleared")
            else:
                brand = str(profile.get("brand", "")).lower().strip()
                protocol = str(profile.get("protocol", "")).upper().strip()
                if protocol == "TCP":
                    host = str(profile.get("host", "")).strip()
                    port = int(profile.get("port", 502))
                    key = f"{brand}:{protocol}:{host}:{port}"
                else:
                    com_port = str(profile.get("com_port", "")).strip()
                    key = f"{brand}:{protocol}:{com_port}"
                if key in PLCDriverFactory._cache:
                    del PLCDriverFactory._cache[key]
                    logger.info("PLCDriverFactory: Removed cached driver for %s", key)

