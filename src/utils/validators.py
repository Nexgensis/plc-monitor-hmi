"""
validators.py — Universal PLC Monitor
All pure functions. No Qt imports. No side effects.
Handles input validation and Modbus address conversion.
Schema v4.0 — all addresses computed from user-supplied integers.
"""
import struct
import socket
import logging
from typing import Union

from src.utils.constants import (
    PLC_BRAND_DELTA, MITSUBISHI_COIL_BASE,
    MITSUBISHI_X_BASE, MITSUBISHI_Y_BASE,
    DELTA_HOLDING_BASE, DELTA_COIL_BASE,
    DELTA_X_BASE, REG_TYPE_HOLDING,
    REG_TYPE_COIL, REG_TYPE_DISCRETE,
    REG_TYPE_INPUT, DATA_TYPE_REGISTER_COUNT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Basic field validators
# ---------------------------------------------------------------------------

def validate_ip(ip: str) -> bool:
    """
    Returns True if *ip* is a valid IPv4 address string or 'localhost'.
    Does NOT perform DNS resolution.
    """
    if not isinstance(ip, str):
        return False
    if ip.strip().lower() == "localhost":
        return True
    try:
        socket.inet_aton(ip.strip())
        return True
    except socket.error:
        return False


def validate_port(port: Union[int, str]) -> bool:
    """
    Returns True if *port* is an integer in the valid TCP/UDP range [1, 65535].
    Accepts int or numeric string.
    """
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def validate_register_address(addr: Union[int, str]) -> bool:
    """
    Returns True if *addr* is in the valid Modbus address range [0, 65535].
    Value 0 is permitted (D0 / M0 are legitimate PLC addresses).
    """
    try:
        a = int(addr)
        return 0 <= a <= 65535
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Modbus address conversion
# ---------------------------------------------------------------------------

def compute_modbus_address(plc_address: int,
                            register_type: str,
                            brand: str) -> int:
    """
    Converts a user-entered PLC programmer address to the pymodbus protocol
    address (0-based index passed to read_holding_registers etc.).

    Args:
        plc_address:   The number as written in the PLC program.
                       e.g. 100 for D100, 10 for M10.
        register_type: One of REG_TYPE_HOLDING / COIL / DISCRETE / INPUT.
        brand:         One of 'mitsubishi' / 'delta' / 'generic'.

    Returns:
        Integer Modbus address suitable for pymodbus function calls.

    Address formulas:
        HOLDING  → plc_address            (D-registers, same for all brands)
        COIL     → base + plc_address     (M-relays, brand-specific base)
        DISCRETE → base + plc_address     (X-inputs, brand-specific base)
        INPUT    → plc_address            (analog input, pass-through)
    """
    if register_type == REG_TYPE_HOLDING:
        # D100 → Modbus address 100 for both Mitsubishi and Delta
        return DELTA_HOLDING_BASE + plc_address  # base is 0 for all brands

    elif register_type == REG_TYPE_COIL:
        if brand == PLC_BRAND_DELTA:
            return DELTA_COIL_BASE + plc_address
        else:
            # Mitsubishi and generic
            return MITSUBISHI_COIL_BASE + plc_address

    elif register_type == REG_TYPE_DISCRETE:
        if brand == PLC_BRAND_DELTA:
            return DELTA_X_BASE + plc_address
        else:
            return MITSUBISHI_X_BASE + plc_address

    elif register_type == REG_TYPE_INPUT:
        # Analog input registers — direct pass-through
        return plc_address

    logger.warning(
        "compute_modbus_address: unknown register_type=%r, returning raw address",
        register_type,
    )
    return plc_address


def y_to_modbus(y_octal_str: str) -> int:
    """
    Converts a Y-output string (e.g. 'Y20') to a Modbus coil address.
    Both Mitsubishi and Delta use base 1280 for Y outputs.
    Y20 (octal 20 = decimal 16) → 1280 + 16 = 1296.

    Returns 0 on parse failure.
    """
    try:
        octal_digits = "".join(filter(str.isdigit, y_octal_str))
        decimal_val = int(octal_digits, 8)
        return MITSUBISHI_Y_BASE + decimal_val  # same constant for both brands
    except Exception:
        logger.warning("y_to_modbus: failed to parse '%s'", y_octal_str)
        return 0


# ---------------------------------------------------------------------------
# Raw register → engineering value conversion
# ---------------------------------------------------------------------------

def convert_raw_to_value(raw_words: list[int],
                          data_type: str,
                          scale_factor: float,
                          word_swap: bool = False) -> float:
    """
    Converts a list of raw 16-bit Modbus register words into a scaled
    engineering value.

    Args:
        raw_words:    List of unsigned 16-bit integers from pymodbus.
                      Must contain at least get_register_count(data_type) words.
        data_type:    One of the DATA_TYPE_* constants.
        scale_factor: Multiplier applied after type conversion.
        word_swap:    If True, swap the two words for 32-bit types.
                      Use when PLC sends low-word first (non-standard).

    Returns:
        Scaled float value. Returns 0.0 on any error.

    Supported types:
        BOOL    — returns 1.0 if raw_words[0] != 0, else 0.0
        INT16   — signed 16-bit, two's complement
        UINT16  — unsigned 16-bit
        INT32   — signed 32-bit (2 registers)
        UINT32  — unsigned 32-bit (2 registers)
        FLOAT32 — IEEE 754 single-precision (2 registers)
        BCD16   — 4-digit BCD in one register
        BCD32   — 8-digit BCD in two registers
    """
    if not raw_words:
        return 0.0

    try:
        if data_type == "BOOL":
            return 1.0 if raw_words[0] else 0.0

        elif data_type == "INT16":
            v = raw_words[0] & 0xFFFF
            if v > 32767:
                v -= 65536
            return v * scale_factor

        elif data_type == "UINT16":
            return (raw_words[0] & 0xFFFF) * scale_factor

        elif data_type in ("INT32", "UINT32"):
            if len(raw_words) < 2:
                return 0.0
            if word_swap:
                combined = ((raw_words[1] & 0xFFFF) << 16) | (raw_words[0] & 0xFFFF)
            else:
                combined = ((raw_words[0] & 0xFFFF) << 16) | (raw_words[1] & 0xFFFF)
            if data_type == "INT32" and combined > 2_147_483_647:
                combined -= 4_294_967_296
            return combined * scale_factor

        elif data_type == "FLOAT32":
            if len(raw_words) < 2:
                return 0.0
            if word_swap:
                words = [raw_words[1] & 0xFFFF, raw_words[0] & 0xFFFF]
            else:
                words = [raw_words[0] & 0xFFFF, raw_words[1] & 0xFFFF]
            packed = struct.pack(">HH", words[0], words[1])
            return struct.unpack(">f", packed)[0] * scale_factor

        elif data_type == "BCD16":
            raw = raw_words[0] & 0xFFFF
            val = (
                ((raw >> 12) & 0xF) * 1000
                + ((raw >> 8) & 0xF) * 100
                + ((raw >> 4) & 0xF) * 10
                + (raw & 0xF)
            )
            return val * scale_factor

        elif data_type == "BCD32":
            if len(raw_words) < 2:
                return 0.0
            if word_swap:
                w0, w1 = raw_words[1] & 0xFFFF, raw_words[0] & 0xFFFF
            else:
                w0, w1 = raw_words[0] & 0xFFFF, raw_words[1] & 0xFFFF
            val = (
                ((w0 >> 12) & 0xF) * 10_000_000
                + ((w0 >> 8) & 0xF) * 1_000_000
                + ((w0 >> 4) & 0xF) * 100_000
                + (w0 & 0xF) * 10_000
                + ((w1 >> 12) & 0xF) * 1_000
                + ((w1 >> 8) & 0xF) * 100
                + ((w1 >> 4) & 0xF) * 10
                + (w1 & 0xF)
            )
            return val * scale_factor

    except Exception as exc:
        logger.error("convert_raw_to_value: data_type=%s error: %s", data_type, exc)

    return 0.0


def get_register_count(data_type: str) -> int:
    """
    Returns the number of Modbus registers (16-bit words) consumed by
    *data_type*. Returns 1 for unknown types (safe default).
    """
    return DATA_TYPE_REGISTER_COUNT.get(data_type, 1)


# ---------------------------------------------------------------------------
# Export / display utilities
# ---------------------------------------------------------------------------

def format_value(value: float, decimal_places: int, unit: str = "") -> str:
    """
    Formats a float value for UI display using the register's decimal_places
    setting and optional unit suffix.

    Args:
        value:          Scaled engineering value.
        decimal_places: Number of decimal digits (0-6).
        unit:           Unit string appended after a space (e.g., 'mV').

    Returns:
        Formatted string, e.g. "34.56 mV".
    """
    formatted = f"{value:.{max(0, min(6, decimal_places))}f}"
    if unit:
        return f"{formatted} {unit}"
    return formatted
