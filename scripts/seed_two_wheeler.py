"""
seed_two_wheeler.py — Seed database for Two-Wheeler Handle Test Fixture

One-time setup that populates:
  1. Register library (26 registers)
  2. Two models (Left Handle, Right Handle)
  3. Model-register mappings with pass/fail limits
  4. Control registers (Start Test, Stop Test, Reset Batch)
  5. Message register mappings (D21 status)
  6. I/O list configuration (digital outputs + system status)
  7. PLC profile (localhost:5020)

Usage:
  python scripts/seed_two_wheeler.py [--db plc_monitor.db] [--reset]
"""
import argparse
import os
import sys
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SeedTwoWheeler")

# ---------------------------------------------------------------------------
# Register definitions: (name, address, register_type, data_type,
#                       description, scale_factor, decimal_places, unit, access)
# ---------------------------------------------------------------------------
REGISTER_DEFS = [
    # System registers
    ("Heartbeat", 0, "HOLDING", "UINT16", "Auto-incrementing counter", 1.0, 0, "", "READ_ONLY"),
    ("Machine State", 21, "HOLDING", "UINT16", "0=IDLE, 99=RUNNING, 1=PASS, 2=FAIL", 1.0, 0, "", "READ_ONLY"),
    ("Overall Result", 22, "HOLDING", "UINT16", "1=PASS, 2=FAIL, 3=BYPASS", 1.0, 0, "", "READ_ONLY"),
    ("OK Count", 23, "HOLDING", "UINT16", "Cumulative pass count", 1.0, 0, "", "READ_ONLY"),
    ("NG Count", 24, "HOLDING", "UINT16", "Cumulative fail count", 1.0, 0, "", "READ_ONLY"),
    ("Batch Count", 25, "HOLDING", "UINT16", "Current batch count", 1.0, 0, "", "READ_ONLY"),

    # Left Handle analog parameters (D100-D106)
    ("Left Indicator Current", 100, "HOLDING", "UINT16", "Left turn indicator bulb current", 100.0, 2, "mA", "READ_ONLY"),
    ("Right Indicator Current", 101, "HOLDING", "UINT16", "Right turn indicator bulb current", 100.0, 2, "mA", "READ_ONLY"),
    ("Horn Button Resistance", 102, "HOLDING", "UINT16", "Horn button continuity resistance", 10.0, 1, "ohm", "READ_ONLY"),
    ("Clutch Lever Voltage", 103, "HOLDING", "UINT16", "Clutch lever position sensor", 1000.0, 3, "V", "READ_ONLY"),
    ("High Beam Current", 104, "HOLDING", "UINT16", "High beam headlight current", 100.0, 2, "mA", "READ_ONLY"),
    ("Low Beam Current", 105, "HOLDING", "UINT16", "Low beam headlight current", 100.0, 2, "mA", "READ_ONLY"),
    ("Pass Light Current", 106, "HOLDING", "UINT16", "Pass flash light current", 100.0, 2, "mA", "READ_ONLY"),

    # Right Handle analog parameters (D111-D118)
    ("Throttle Position Voltage", 111, "HOLDING", "UINT16", "Throttle position sensor voltage", 1000.0, 3, "V", "READ_ONLY"),
    ("Front Brake Lever Voltage", 112, "HOLDING", "UINT16", "Front brake lever switch voltage", 1000.0, 3, "V", "READ_ONLY"),
    ("Kill Switch Continuity", 113, "HOLDING", "UINT16", "Engine kill switch resistance", 10.0, 1, "ohm", "READ_ONLY"),
    ("Starter Button Current", 114, "HOLDING", "UINT16", "Starter button circuit current", 100.0, 2, "mA", "READ_ONLY"),
    ("Headlight Switch Current", 115, "HOLDING", "UINT16", "Headlight switch circuit current", 100.0, 2, "mA", "READ_ONLY"),
    ("Rear Brake Voltage", 116, "HOLDING", "UINT16", "Rear brake lever switch voltage", 1000.0, 3, "V", "READ_ONLY"),
    ("Panel Light Current", 117, "HOLDING", "UINT16", "Instrument panel light current", 100.0, 2, "mA", "READ_ONLY"),
    ("USB Charger Voltage", 118, "HOLDING", "UINT16", "USB charger output voltage", 1000.0, 3, "V", "READ_ONLY"),

    # Control coils (M100-M102)
    ("Start Test Trigger", 100, "COIL", "BOOL", "Pulse 1 to start a test cycle", 1.0, 0, "", "READ_WRITE"),
    ("Stop Test Trigger", 101, "COIL", "BOOL", "Pulse 1 to abort test", 1.0, 0, "", "READ_WRITE"),
    ("Reset Batch Trigger", 102, "COIL", "BOOL", "Pulse 1 to reset batch counters", 1.0, 0, "", "READ_WRITE"),

    # Digital outputs (M110-M118)
    ("Left Indicator Lamp", 110, "COIL", "BOOL", "Left indicator lamp state", 1.0, 0, "", "READ_ONLY"),
    ("Right Indicator Lamp", 111, "COIL", "BOOL", "Right indicator lamp state", 1.0, 0, "", "READ_ONLY"),
    ("Horn Active", 112, "COIL", "BOOL", "Horn circuit active state", 1.0, 0, "", "READ_ONLY"),
    ("High Beam ON", 113, "COIL", "BOOL", "High beam headlight state", 1.0, 0, "", "READ_ONLY"),
    ("Low Beam ON", 114, "COIL", "BOOL", "Low beam headlight state", 1.0, 0, "", "READ_ONLY"),
    ("Kill Switch ON", 115, "COIL", "BOOL", "Kill switch active state", 1.0, 0, "", "READ_ONLY"),
    ("Starter Active", 116, "COIL", "BOOL", "Starter circuit active state", 1.0, 0, "", "READ_ONLY"),
    ("Brake Lever Pressed", 117, "COIL", "BOOL", "Brake lever engaged state", 1.0, 0, "", "READ_ONLY"),
    ("Clutch Lever Engaged", 118, "COIL", "BOOL", "Clutch lever engaged state", 1.0, 0, "", "READ_ONLY"),
]

# ---------------------------------------------------------------------------
# Model definitions: (name, description, model_number, sort_order)
# ---------------------------------------------------------------------------
MODEL_DEFS = [
    ("Left Handle Assembly", "Left handle switches and indicators for two-wheeler", "LHA-001", 1),
    ("Right Handle Assembly", "Right handle controls and sensors for two-wheeler", "RHA-001", 2),
]

# ---------------------------------------------------------------------------
# Model-Register mappings: (model_name, register_name, role, display_name,
#   group_name, enabled, bypass, show_in_dashboard, card_position, pass_value, fail_value)
#
# Roles: MEASURED, RESULT, STATUS, LIMIT_MIN, LIMIT_MAX, COUNTER, TIMER, CUSTOM
# ---------------------------------------------------------------------------
LEFT_HANDLE_MAPPINGS = [
    # Measured parameters
    ("Left Handle Assembly", "Left Indicator Current", "MEASURED", "Left Indicator Current", "Electrical", 1, 0, 1, 1, 1, 2),
    ("Left Handle Assembly", "Right Indicator Current", "MEASURED", "Right Indicator Current", "Electrical", 1, 0, 1, 2, 1, 2),
    ("Left Handle Assembly", "Horn Button Resistance", "MEASURED", "Horn Button", "Electrical", 1, 0, 1, 3, 1, 2),
    ("Left Handle Assembly", "Clutch Lever Voltage", "MEASURED", "Clutch Lever", "Mechanical", 1, 0, 1, 4, 1, 2),
    ("Left Handle Assembly", "High Beam Current", "MEASURED", "High Beam Current", "Electrical", 1, 0, 1, 5, 1, 2),
    ("Left Handle Assembly", "Low Beam Current", "MEASURED", "Low Beam Current", "Electrical", 1, 0, 1, 6, 1, 2),
    ("Left Handle Assembly", "Pass Light Current", "MEASURED", "Pass Light", "Electrical", 1, 0, 1, 7, 1, 2),
    # Digital outputs
    ("Left Handle Assembly", "Left Indicator Lamp", "MEASURED", "Indicator Left", "Digital I/O", 1, 0, 1, 8, 1, 2),
    ("Left Handle Assembly", "Right Indicator Lamp", "MEASURED", "Indicator Right", "Digital I/O", 1, 0, 1, 9, 1, 2),
    ("Left Handle Assembly", "Horn Active", "MEASURED", "Horn State", "Digital I/O", 1, 0, 1, 10, 1, 2),
    ("Left Handle Assembly", "High Beam ON", "MEASURED", "High Beam State", "Digital I/O", 1, 0, 1, 11, 1, 2),
    ("Left Handle Assembly", "Low Beam ON", "MEASURED", "Low Beam State", "Digital I/O", 1, 0, 1, 12, 1, 2),
    ("Left Handle Assembly", "Clutch Lever Engaged", "MEASURED", "Clutch State", "Digital I/O", 1, 0, 1, 13, 1, 2),
    # System registers
    ("Left Handle Assembly", "Overall Result", "RESULT", "Test Result", "System", 1, 0, 1, 20, 1, 2),
    ("Left Handle Assembly", "Machine State", "STATUS", "Machine State", "System", 1, 0, 1, 21, 0, 2),
    ("Left Handle Assembly", "OK Count", "COUNTER", "OK Count", "Counters", 1, 0, 1, 22, 0, 0),
    ("Left Handle Assembly", "NG Count", "COUNTER", "NG Count", "Counters", 1, 0, 1, 23, 0, 0),
    ("Left Handle Assembly", "Batch Count", "COUNTER", "Batch Count", "Counters", 1, 0, 1, 24, 0, 0),
]

RIGHT_HANDLE_MAPPINGS = [
    # Measured parameters
    ("Right Handle Assembly", "Throttle Position Voltage", "MEASURED", "Throttle Position", "Sensors", 1, 0, 1, 1, 1, 2),
    ("Right Handle Assembly", "Front Brake Lever Voltage", "MEASURED", "Front Brake", "Sensors", 1, 0, 1, 2, 1, 2),
    ("Right Handle Assembly", "Kill Switch Continuity", "MEASURED", "Kill Switch", "Electrical", 1, 0, 1, 3, 1, 2),
    ("Right Handle Assembly", "Starter Button Current", "MEASURED", "Starter Button", "Electrical", 1, 0, 1, 4, 1, 2),
    ("Right Handle Assembly", "Headlight Switch Current", "MEASURED", "Headlight Switch", "Electrical", 1, 0, 1, 5, 1, 2),
    ("Right Handle Assembly", "Rear Brake Voltage", "MEASURED", "Rear Brake", "Sensors", 1, 0, 1, 6, 1, 2),
    ("Right Handle Assembly", "Panel Light Current", "MEASURED", "Panel Light", "Electrical", 1, 0, 1, 7, 1, 2),
    ("Right Handle Assembly", "USB Charger Voltage", "MEASURED", "USB Charger", "Power", 1, 0, 1, 8, 1, 2),
    # Digital outputs
    ("Right Handle Assembly", "Kill Switch ON", "MEASURED", "Kill State", "Digital I/O", 1, 0, 1, 9, 1, 2),
    ("Right Handle Assembly", "Starter Active", "MEASURED", "Starter State", "Digital I/O", 1, 0, 1, 10, 1, 2),
    ("Right Handle Assembly", "Brake Lever Pressed", "MEASURED", "Brake State", "Digital I/O", 1, 0, 1, 11, 1, 2),
    # System registers
    ("Right Handle Assembly", "Overall Result", "RESULT", "Test Result", "System", 1, 0, 1, 20, 1, 2),
    ("Right Handle Assembly", "Machine State", "STATUS", "Machine State", "System", 1, 0, 1, 21, 0, 2),
    ("Right Handle Assembly", "OK Count", "COUNTER", "OK Count", "Counters", 1, 0, 1, 22, 0, 0),
    ("Right Handle Assembly", "NG Count", "COUNTER", "NG Count", "Counters", 1, 0, 1, 23, 0, 0),
    ("Right Handle Assembly", "Batch Count", "COUNTER", "Batch Count", "Counters", 1, 0, 1, 24, 0, 0),
]

# ---------------------------------------------------------------------------
# Control register definitions: (name, register_name, control_type,
#   write_value, reset_after_ms, confirm_required, description, sort_order)
# ---------------------------------------------------------------------------
CONTROL_DEFS = [
    ("Start Test", "Start Test Trigger", "START_TEST", 1, 500, 0, "Start a new test cycle", 1),
    ("Stop Test", "Stop Test Trigger", "STOP_TEST", 1, 500, 1, "Abort the current test", 2),
    ("Reset Batch", "Reset Batch Trigger", "RESET_BATCH", 1, 500, 1, "Reset OK/NG/Batch counters", 3),
]

# ---------------------------------------------------------------------------
# Message register definitions: (register_name, trigger_value, message_text, color, severity)
# ---------------------------------------------------------------------------
MESSAGE_DEFS = [
    ("Machine State", 0, "IDLE - Ready", "green", "INFO"),
    ("Machine State", 99, "RUNNING - Test in progress", "yellow", "WARNING"),
    ("Machine State", 1, "PASS - All parameters OK", "green", "INFO"),
    ("Machine State", 2, "FAIL - Parameters out of range", "red", "ERROR"),
    ("Machine State", 3, "BYPASS - Test bypassed", "yellow", "WARNING"),
    ("Machine State", 4, "ERROR - System fault", "red", "CRITICAL"),
    ("Machine State", 5, "WAITING - Fixture not ready", "yellow", "WARNING"),
    ("Machine State", 6, "COMPLETE - Cycle finished", "green", "INFO"),
]


# ---------------------------------------------------------------------------
# I/O list definitions: (display_name, register_name, group_name, row_order,
#   show_value, on_label, off_label, on_color, off_color)
# ---------------------------------------------------------------------------
IO_LIST_DEFS = [
    # Control inputs
    ("Start Test Trigger", "Start Test Trigger", "Control", 1, 0, "ACTIVE", "OFF", "#22c55e", "#5a7a9a"),
    ("Stop Test Trigger", "Stop Test Trigger", "Control", 2, 0, "ACTIVE", "OFF", "#ef4444", "#5a7a9a"),
    ("Reset Batch Trigger", "Reset Batch Trigger", "Control", 3, 0, "ACTIVE", "OFF", "#f59e0b", "#5a7a9a"),

    # Left handle digital outputs
    ("Left Indicator Lamp", "Left Indicator Lamp", "Left Handle - Outputs", 10, 0, "ON", "OFF", "#22c55e", "#5a7a9a"),
    ("Right Indicator Lamp", "Right Indicator Lamp", "Left Handle - Outputs", 11, 0, "ON", "OFF", "#22c55e", "#5a7a9a"),
    ("Horn Active", "Horn Active", "Left Handle - Outputs", 12, 0, "ON", "OFF", "#22c55e", "#5a7a9a"),
    ("High Beam ON", "High Beam ON", "Left Handle - Outputs", 13, 0, "ON", "OFF", "#3b82f6", "#5a7a9a"),
    ("Low Beam ON", "Low Beam ON", "Left Handle - Outputs", 14, 0, "ON", "OFF", "#3b82f6", "#5a7a9a"),
    ("Clutch Lever Engaged", "Clutch Lever Engaged", "Left Handle - Outputs", 15, 0, "ENGAGED", "DISENGAGED", "#f59e0b", "#5a7a9a"),

    # Right handle digital outputs
    ("Kill Switch ON", "Kill Switch ON", "Right Handle - Outputs", 20, 0, "ON", "OFF", "#ef4444", "#5a7a9a"),
    ("Starter Active", "Starter Active", "Right Handle - Outputs", 21, 0, "ACTIVE", "OFF", "#22c55e", "#5a7a9a"),
    ("Brake Lever Pressed", "Brake Lever Pressed", "Right Handle - Outputs", 22, 0, "PRESSED", "RELEASED", "#f59e0b", "#5a7a9a"),

    # System status
    ("Machine State", "Machine State", "System", 30, 1, "RUN", "IDLE", "#22c55e", "#5a7a9a"),
    ("Overall Result", "Overall Result", "System", 31, 1, "PASS", "FAIL", "#22c55e", "#ef4444"),
    ("Heartbeat", "Heartbeat", "System", 32, 1, "ACTIVE", "STOPPED", "#22c55e", "#5a7a9a"),
]


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def clear_all(conn: sqlite3.Connection):
    """Delete all seeded data (in FK-safe order)."""
    logger.info("Clearing existing data...")
    conn.execute("DELETE FROM io_list_config")
    conn.execute("DELETE FROM message_register")
    conn.execute("DELETE FROM control_registers")
    conn.execute("DELETE FROM model_register_map")
    conn.execute("DELETE FROM models")
    conn.execute("DELETE FROM register_library")
    conn.execute("UPDATE plc_profile SET host = '', port = 502")
    conn.commit()
    logger.info("Cleared.")


def get_or_create_user_id(conn: sqlite3.Connection, username: str = "admin") -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        return row["id"]
    logger.warning(f"User '{username}' not found, using NULL for created_by")
    return None


def seed_register_library(conn: sqlite3.Connection) -> dict:
    """Insert registers and return {name: id} mapping."""
    admin_id = get_or_create_user_id(conn)
    reg_map = {}

    for name, addr, rtype, dtype, desc, scale, dec, unit, access in REGISTER_DEFS:
        cursor = conn.execute(
            """INSERT INTO register_library
               (name, description, register_address, register_type, data_type,
                scale_factor, decimal_places, unit, access, word_swap, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (name, desc, addr, rtype, dtype, scale, dec, unit, access, admin_id),
        )
        reg_map[name] = cursor.lastrowid

    conn.commit()
    logger.info(f"Registered {len(reg_map)} registers.")
    return reg_map


def seed_models(conn: sqlite3.Connection) -> dict:
    """Insert models and return {name: id} mapping."""
    model_map = {}

    for name, desc, model_num, sort in MODEL_DEFS:
        cursor = conn.execute(
            """INSERT INTO models (name, description, model_number, sort_order)
               VALUES (?, ?, ?, ?)""",
            (name, desc, model_num, sort),
        )
        model_map[name] = cursor.lastrowid

    conn.commit()
    logger.info(f"Created {len(model_map)} models.")
    return model_map


# ---------------------------------------------------------------------------
# Per-parameter spec limits (min, max) in engineering units, keyed by register
# name. Units match RegisterLibrary and the mock server (mA / V / ohm / state).
# Registers without limits (RESULT/STATUS/COUNTER or telemetry-only) remain
# unconfigured and are displayed as N/A.
# ---------------------------------------------------------------------------
MAPPING_LIMITS = {
    # Left handle analog (mock range shown) — mA / V / ohm
    "Left Indicator Current":   (180.0, 370.0),    # mock 180-370 mA
    "Right Indicator Current":  (180.0, 370.0),    # mock 180-370 mA
    "Horn Button Resistance":   (0.5, 5.0),        # mock 0-5 ohm
    "Clutch Lever Voltage":     (0.45, 1.05),      # mock 0.45-1.05 V
    "High Beam Current":        (280.0, 620.0),    # mock 280-620 mA
    "Low Beam Current":         (180.0, 420.0),    # mock 180-420 mA
    "Pass Light Current":       (280.0, 620.0),    # mock 280-620 mA
    # Right handle analog
    "Throttle Position Voltage": (0.45, 0.55),      # mock 0.45-0.55 V
    "Front Brake Lever Voltage":  (3.8, 4.2),       # mock 3.8-4.2 V
    "Kill Switch Continuity":     (0.0, 5.0),       # mock 0-5 ohm
    "Starter Button Current":     (80.0, 520.0),    # mock 80-520 mA
    "Headlight Switch Current":   (180.0, 420.0),   # mock 180-420 mA
    "Rear Brake Voltage":         (3.8, 4.2),       # mock 3.8-4.2 V
    "Panel Light Current":        (10.0, 50.0),     # mock 10-50 mA
    "USB Charger Voltage":        (4.8, 5.2),       # mock 4.8-5.2 V
    # Digital outputs (0/1 states)
    "Left Indicator Lamp":   (0.0, 1.0),
    "Right Indicator Lamp":  (0.0, 1.0),
    "Horn Active":           (0.0, 1.0),
    "High Beam ON":          (0.0, 1.0),
    "Low Beam ON":           (0.0, 1.0),
    "Clutch Lever Engaged":  (0.0, 1.0),
    "Kill Switch ON":        (0.0, 1.0),
    "Starter Active":        (0.0, 1.0),
    "Brake Lever Pressed":   (0.0, 1.0),
}


def seed_mappings(conn: sqlite3.Connection, model_map: dict, reg_map: dict, mappings: list):
    """Insert model-register mappings."""
    count = 0
    for model_name, reg_name, role, disp_name, group, enabled, bypass, show_dash, card_pos, pass_val, fail_val in mappings:
        model_id = model_map.get(model_name)
        reg_id = reg_map.get(reg_name)
        if model_id is None:
            logger.warning(f"Model '{model_name}' not found, skipping mapping.")
            continue
        if reg_id is None:
            logger.warning(f"Register '{reg_name}' not found, skipping mapping.")
            continue

        limit_min, limit_max = MAPPING_LIMITS.get(reg_name, (0.0, 0.0))

        conn.execute(
            """INSERT INTO model_register_map
               (model_id, register_id, role, display_name, group_name,
                enabled, bypass, show_in_dashboard, card_position,
                pass_value, fail_value, limit_min, limit_max)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (model_id, reg_id, role, disp_name, group,
             enabled, bypass, show_dash, card_pos, pass_val, fail_val,
             limit_min, limit_max),
        )
        count += 1

    conn.commit()
    logger.info(f"Created {count} model-register mappings.")


def seed_controls(conn: sqlite3.Connection, reg_map: dict):
    """Insert control register definitions."""
    count = 0
    for name, reg_name, ctrl_type, write_val, reset_ms, confirm, desc, sort_order in CONTROL_DEFS:
        reg_id = reg_map.get(reg_name)
        if reg_id is None:
            logger.warning(f"Register '{reg_name}' not found, skipping control.")
            continue

        conn.execute(
            """INSERT INTO control_registers
               (name, register_id, control_type, write_value,
                reset_after_ms, confirm_required, description, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, reg_id, ctrl_type, write_val, reset_ms, confirm, desc, sort_order),
        )
        count += 1

    conn.commit()
    logger.info(f"Created {count} control registers.")


def seed_messages(conn: sqlite3.Connection, reg_map: dict):
    """Insert message register mappings."""
    count = 0
    for reg_name, trigger_val, msg_text, color, severity in MESSAGE_DEFS:
        reg_id = reg_map.get(reg_name)
        if reg_id is None:
            logger.warning(f"Register '{reg_name}' not found, skipping messages.")
            continue

        conn.execute(
            """INSERT INTO message_register
               (register_id, trigger_value, message_text, color, severity)
               VALUES (?, ?, ?, ?, ?)""",
            (reg_id, trigger_val, msg_text, color, severity),
        )
        count += 1

    conn.commit()
    logger.info(f"Created {count} message register entries.")


def seed_io_list(conn: sqlite3.Connection, reg_map: dict):
    """Insert I/O list configuration entries."""
    count = 0
    for display_name, reg_name, group, row_order, show_val, on_lbl, off_lbl, on_clr, off_clr in IO_LIST_DEFS:
        reg_id = reg_map.get(reg_name)
        if reg_id is None:
            logger.warning(f"Register '{reg_name}' not found, skipping I/O entry.")
            continue

        conn.execute(
            """INSERT INTO io_list_config
               (display_name, register_id, group_name, row_order,
                show_value, on_label, off_label, on_color, off_color, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (display_name, reg_id, group, row_order, show_val, on_lbl, off_lbl, on_clr, off_clr),
        )
        count += 1

    conn.commit()
    logger.info(f"Created {count} I/O list entries.")


def seed_plc_profile(conn: sqlite3.Connection, reg_map: dict):
    """Update PLC profile to point to mock server."""
    msg_reg_id = reg_map.get("Machine State")

    conn.execute(
        """UPDATE plc_profile SET
           brand = 'mitsubishi',
           protocol = 'TCP',
           host = '127.0.0.1',
           port = 5020,
           slave_id = 1,
           poll_interval_ms = 500,
           timeout_ms = 3000,
           reconnect_delay_ms = 3000,
           max_retries = 3,
           message_register_id = ?
           WHERE id = 1""",
        (msg_reg_id,),
    )
    conn.commit()
    logger.info("PLC profile updated: 127.0.0.1:5020 (Mitsubishi TCP)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Seed database for Two-Wheeler Handle Test Fixture"
    )
    parser.add_argument(
        "--db", default="plc_monitor.db", help="Database file path (default: plc_monitor.db)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Clear existing data before seeding"
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        logger.error(f"Database file not found: {args.db}")
        logger.info("Run the application first to create the database, then re-run this script.")
        sys.exit(1)

    conn = get_db(args.db)

    try:
        if args.reset:
            clear_all(conn)

        # Check if already seeded
        existing = conn.execute("SELECT COUNT(*) as cnt FROM register_library").fetchone()
        if existing["cnt"] > 0:
            logger.warning(
                f"Database already has {existing['cnt']} registers. "
                "Use --reset to clear and re-seed, or data will be skipped."
            )
            # Still proceed — INSERT OR IGNORE will handle duplicates for models/messages
            # but register_library has UNIQUE constraint on name, so skip those

        reg_map = seed_register_library(conn)
        model_map = seed_models(conn)
        seed_mappings(conn, model_map, reg_map, LEFT_HANDLE_MAPPINGS)
        seed_mappings(conn, model_map, reg_map, RIGHT_HANDLE_MAPPINGS)
        seed_controls(conn, reg_map)
        seed_messages(conn, reg_map)
        seed_io_list(conn, reg_map)
        seed_plc_profile(conn, reg_map)

        print()
        print("=" * 55)
        print("  Two-Wheeler Handle Test Fixture — Seed Complete")
        print("=" * 55)
        print(f"  Registers:   {len(reg_map)}")
        print(f"  Models:      {len(model_map)}")
        print(f"  Mappings:    {len(LEFT_HANDLE_MAPPINGS) + len(RIGHT_HANDLE_MAPPINGS)}")
        print(f"  Controls:    {len(CONTROL_DEFS)}")
        print(f"  Messages:    {len(MESSAGE_DEFS)}")
        print(f"  I/O List:    {len(IO_LIST_DEFS)}")
        print(f"  PLC Profile: 127.0.0.1:5020 (Mitsubishi TCP)")
        print("=" * 55)
        print()
        print("Next steps:")
        print("  1. Start mock server:")
        print("     python tests/mock_plc_server.py --port 5020 --sim-mode interactive")
        print("  2. Start the application:")
        print("     python main.py")
        print("  3. Login as admin / Admin@1234")
        print("  4. Select a model and start testing!")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
