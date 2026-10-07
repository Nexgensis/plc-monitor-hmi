"""
constants.py — Universal PLC Monitor
Single source of truth for all app-level constants.
Schema v4.0 — zero hardcoded register addresses or model names.
All register/model data lives exclusively in the database.
"""

# ---------------------------------------------------------------------------
# Application identity
# ---------------------------------------------------------------------------
APP_NAME          = "PLC Monitor"
APP_VERSION       = "1.0.0"
APP_ORG           = "Switch Test Station"
DB_PATH           = "plc_monitor.db"
LOG_DIR           = "logs"
REPORTS_DIR       = "reports"
CONFIG_EXPORT_DIR = "config_exports"

# ---------------------------------------------------------------------------
# PLC Brands
# Determines which address-offset formula is applied at runtime.
# ---------------------------------------------------------------------------
PLC_BRAND_MITSUBISHI = "mitsubishi"
PLC_BRAND_DELTA      = "delta"
PLC_BRAND_GENERIC    = "generic"

PLC_BRANDS = [PLC_BRAND_MITSUBISHI, PLC_BRAND_DELTA, PLC_BRAND_GENERIC]

PLC_BRAND_LABELS: dict[str, str] = {
    PLC_BRAND_MITSUBISHI: "Mitsubishi FX / iQ-F Series",
    PLC_BRAND_DELTA:      "Delta DVP / AS Series",
    PLC_BRAND_GENERIC:    "Generic Modbus TCP/RTU",
}

# Communication protocols
PLC_PROTOCOL_TCP = "TCP"
PLC_PROTOCOL_RTU = "RTU"

# ---------------------------------------------------------------------------
# Modbus Address Conversion Bases
#
# These are the ONLY address formulas in the codebase.
# All register addresses are stored as PLC programmer numbers (D-number,
# M-number, etc.) in register_library.register_address. The functions in
# validators.py use these bases to produce the Modbus protocol address.
#
# Mitsubishi FX5U / iQ-F:
#   D register n → Modbus holding address n     (MITSUBISHI_HOLDING_BASE + n)
#   M coil n     → Modbus coil address          (MITSUBISHI_COIL_BASE + n)
#   Y output     → Modbus coil address          (MITSUBISHI_Y_BASE + decimal_of_octal)
#   X input      → Modbus discrete address      (MITSUBISHI_X_BASE + decimal_of_octal)
#
# Delta DVP:
#   D register n → Modbus holding address n     (DELTA_HOLDING_BASE + n)
#   M coil n     → Modbus coil address          (DELTA_COIL_BASE + n)
#   Y output     → Modbus coil address          (DELTA_Y_BASE + decimal_of_octal)
#   X input      → Modbus discrete address      (DELTA_X_BASE + n)
#
# Generic: pass-through, no offset applied.
# ---------------------------------------------------------------------------
MITSUBISHI_HOLDING_BASE = 0       # D0 → holding address 0
MITSUBISHI_COIL_BASE    = 1       # M0 → coil address 1
MITSUBISHI_Y_BASE       = 1280    # Y output coil base (decimal offset of octal Y)
MITSUBISHI_X_BASE       = 0x400   # X input discrete base (1024)

DELTA_HOLDING_BASE      = 0       # D0 → holding address 0 (same as Mitsubishi)
DELTA_COIL_BASE         = 2048    # M0 → coil protocol address 0x0800
DELTA_Y_BASE            = 1280    # Y output coil base (same as Mitsubishi)
DELTA_X_BASE            = 1024    # X input discrete base

# ---------------------------------------------------------------------------
# Register Types (Modbus function table identifiers)
# ---------------------------------------------------------------------------
REG_TYPE_HOLDING  = "HOLDING"   # 4x table — D registers, data values (read/write)
REG_TYPE_COIL     = "COIL"      # 0x table — M/Y relays, bit read/write
REG_TYPE_DISCRETE = "DISCRETE"  # 1x table — X inputs, bit read-only
REG_TYPE_INPUT    = "INPUT"     # 3x table — analog input registers

REG_TYPES = [REG_TYPE_HOLDING, REG_TYPE_COIL, REG_TYPE_DISCRETE, REG_TYPE_INPUT]

REG_TYPE_LABELS: dict[str, str] = {
    REG_TYPE_HOLDING:  "Holding Register (4x) — D registers",
    REG_TYPE_COIL:     "Coil (0x) — M/Y relays, R/W bits",
    REG_TYPE_DISCRETE: "Discrete Input (1x) — X inputs, read-only",
    REG_TYPE_INPUT:    "Input Register (3x) — analog inputs",
}

# ---------------------------------------------------------------------------
# Data Types — how raw register words are interpreted
# ---------------------------------------------------------------------------
DATA_TYPE_BOOL    = "BOOL"     # Single bit from coil/discrete register
DATA_TYPE_INT16   = "INT16"    # Signed 16-bit integer (-32768 to 32767)
DATA_TYPE_UINT16  = "UINT16"   # Unsigned 16-bit integer (0 to 65535)
DATA_TYPE_INT32   = "INT32"    # Signed 32-bit integer (2 consecutive registers)
DATA_TYPE_UINT32  = "UINT32"   # Unsigned 32-bit integer (2 consecutive registers)
DATA_TYPE_FLOAT32 = "FLOAT32"  # IEEE 754 32-bit float (2 consecutive registers)
DATA_TYPE_BCD16   = "BCD16"    # Binary Coded Decimal 16-bit (1 register)
DATA_TYPE_BCD32   = "BCD32"    # Binary Coded Decimal 32-bit (2 registers)

DATA_TYPES = [
    DATA_TYPE_BOOL,
    DATA_TYPE_INT16,
    DATA_TYPE_UINT16,
    DATA_TYPE_INT32,
    DATA_TYPE_UINT32,
    DATA_TYPE_FLOAT32,
    DATA_TYPE_BCD16,
    DATA_TYPE_BCD32,
]

DATA_TYPE_LABELS: dict[str, str] = {
    DATA_TYPE_BOOL:    "Boolean (single bit)",
    DATA_TYPE_INT16:   "INT16 — signed 16-bit (-32768..32767)",
    DATA_TYPE_UINT16:  "UINT16 — unsigned 16-bit (0..65535)",
    DATA_TYPE_INT32:   "INT32 — signed 32-bit (2 registers)",
    DATA_TYPE_UINT32:  "UINT32 — unsigned 32-bit (2 registers)",
    DATA_TYPE_FLOAT32: "FLOAT32 — IEEE 754 float (2 registers)",
    DATA_TYPE_BCD16:   "BCD16 — Binary Coded Decimal 16-bit",
    DATA_TYPE_BCD32:   "BCD32 — Binary Coded Decimal 32-bit",
}

# Number of Modbus registers (words) consumed by each data type
DATA_TYPE_REGISTER_COUNT: dict[str, int] = {
    DATA_TYPE_BOOL:    1,
    DATA_TYPE_INT16:   1,
    DATA_TYPE_UINT16:  1,
    DATA_TYPE_BCD16:   1,
    DATA_TYPE_INT32:   2,
    DATA_TYPE_UINT32:  2,
    DATA_TYPE_FLOAT32: 2,
    DATA_TYPE_BCD32:   2,
}

# ---------------------------------------------------------------------------
# Access Modes
# ---------------------------------------------------------------------------
ACCESS_READ_ONLY  = "READ_ONLY"   # App only reads this register
ACCESS_READ_WRITE = "READ_WRITE"  # App may write to this register

# ---------------------------------------------------------------------------
# Data Blocks — bulk contiguous address ranges (register_blocks table)
# ---------------------------------------------------------------------------
# UI/config limits for a single block definition.
MAX_BLOCK_COUNT_REGS = 1000   # max words in one HOLDING/INPUT block
MAX_BLOCK_COUNT_BITS = 2000   # max bits in one COIL/DISCRETE block

# Modbus protocol maxima per request — block reads/writes are chunked to
# these sizes (class-overridable per driver/brand if a device is stricter).
MODBUS_MAX_READ_REGS  = 125   # FC03/FC04 max holding/input registers
MODBUS_MAX_READ_BITS  = 2000  # FC01/FC02 max coils/discrete inputs
MODBUS_MAX_WRITE_REGS = 123   # FC16 max holding registers
MODBUS_MAX_WRITE_BITS = 1968  # FC0F max coils

# ---------------------------------------------------------------------------
# Register Roles in model_register_map
# Defines the functional role of each register for a specific model.
# ---------------------------------------------------------------------------
ROLE_MEASURED  = "MEASURED"    # Live process measurement shown in dashboard card
ROLE_RESULT    = "RESULT"      # PASS/FAIL flag register for this parameter
ROLE_STATUS    = "STATUS"      # General machine status indicator
ROLE_LIMIT_MIN = "LIMIT_MIN"   # Minimum acceptable value register
ROLE_LIMIT_MAX = "LIMIT_MAX"   # Maximum acceptable value register
ROLE_COUNTER   = "COUNTER"     # Counter register (batch, part, etc.)
ROLE_TIMER     = "TIMER"       # Timer register
ROLE_CUSTOM    = "CUSTOM"      # Engineer-defined custom role

ROLES = [
    ROLE_MEASURED, ROLE_RESULT, ROLE_STATUS,
    ROLE_LIMIT_MIN, ROLE_LIMIT_MAX,
    ROLE_COUNTER, ROLE_TIMER, ROLE_CUSTOM,
]

# ---------------------------------------------------------------------------
# Control Register Types (for control_registers table)
# ---------------------------------------------------------------------------
CTRL_START_TEST    = "START_TEST"     # Triggers start of test cycle
CTRL_STOP_TEST     = "STOP_TEST"      # Stops an active test cycle
CTRL_RESET_BATCH   = "RESET_BATCH"    # Resets batch counter to 0
CTRL_RESET_COUNTER = "RESET_COUNTER"  # Resets part/unit counter
CTRL_ACK           = "ACK"            # Acknowledges alarm condition
CTRL_BYPASS_FLAG   = "BYPASS_FLAG"    # Sets/clears bypass state
CTRL_CUSTOM        = "CUSTOM"         # Engineer-defined custom write

CTRL_TYPES = [
    CTRL_START_TEST, CTRL_STOP_TEST, CTRL_RESET_BATCH,
    CTRL_RESET_COUNTER, CTRL_ACK, CTRL_BYPASS_FLAG, CTRL_CUSTOM,
]

CTRL_TYPE_LABELS: dict[str, str] = {
    CTRL_START_TEST:    "Start Test Cycle",
    CTRL_STOP_TEST:     "Stop Test Cycle",
    CTRL_RESET_BATCH:   "Reset Batch Counter",
    CTRL_RESET_COUNTER: "Reset Part Counter",
    CTRL_ACK:           "Alarm Acknowledge",
    CTRL_BYPASS_FLAG:   "Bypass Flag Toggle",
    CTRL_CUSTOM:        "Custom Write",
}

# plc_write_log.write_reason for bulk register-block writes (FC16/FC0F).
# Not a control_registers type — audit-trail reason only.
REASON_BLOCK_WRITE = "BLOCK_WRITE"

# ---------------------------------------------------------------------------
# Test Result Values
# ---------------------------------------------------------------------------
RESULT_PASS    = "PASS"
RESULT_FAIL    = "FAIL"
RESULT_BYPASS  = "BYPASS"
RESULT_PENDING = "PENDING"
RESULT_RUNNING = "RUNNING"
RESULT_NA      = "N/A"       # Informative/telemetry parameter with no thresholds

# ---------------------------------------------------------------------------
# Machine State (D21 message register values)
# ---------------------------------------------------------------------------
MACHINE_STATE_IDLE      = 0
MACHINE_STATE_RUNNING   = 99
MACHINE_STATE_PASS      = 1
MACHINE_STATE_FAIL      = 2
MACHINE_STATE_BYPASS    = 3
MACHINE_STATE_ERROR     = 4
MACHINE_STATE_WAITING   = 5
MACHINE_STATE_COMPLETE  = 6

# ---------------------------------------------------------------------------
# Dashboard Card Layout
# ---------------------------------------------------------------------------
MAX_DASHBOARD_CARDS = 20  # Maximum simultaneous cards on test dashboard

# Thresholds: (min_cards, max_cards) → grid layout config
CARD_GRID_THRESHOLDS: dict[tuple[int, int], dict] = {
    (1, 4):   {"cols": 2, "size": "large"},
    (5, 8):   {"cols": 3, "size": "medium"},
    (9, 16):  {"cols": 4, "size": "small"},
    (17, 30): {"cols": 5, "size": "small"},
}

# ---------------------------------------------------------------------------
# User Roles and Access Control
# ---------------------------------------------------------------------------
ROLE_ADMIN      = "ADMIN"       # Full access: CONFIG, all screens, all writes
ROLE_SUPERVISOR = "SUPERVISOR"  # Reports + read access, no CONFIG
ROLE_OPERATOR   = "OPERATOR"    # Model selection, test execution, manual writes

CONFIG_ACCESS_ROLES  = [ROLE_ADMIN]
REPORTS_ACCESS_ROLES = [ROLE_ADMIN, ROLE_SUPERVISOR]

# ---------------------------------------------------------------------------
# Write Reasons — audit trail labels for plc_write_log
# ---------------------------------------------------------------------------
WRITE_START_TEST    = "START_TEST"    # User pressed Start
WRITE_STOP_TEST     = "STOP_TEST"     # User pressed Stop
WRITE_RESET_BATCH   = "RESET_BATCH"   # Batch counter reset
WRITE_RESET_COUNTER = "RESET_COUNTER" # Part counter reset
WRITE_ACK           = "ACK"           # Alarm acknowledge
WRITE_BYPASS        = "BYPASS_FLAG"   # Bypass flag toggle
WRITE_CUSTOM        = "CUSTOM"        # Custom control write
WRITE_MANUAL        = "MANUAL"        # Manual control panel write

# ---------------------------------------------------------------------------
# Theme Constants
# ---------------------------------------------------------------------------
THEME_DARK  = "dark"
THEME_LIGHT = "light"

# ---------------------------------------------------------------------------
# Design Tokens — single source of truth for Python-side colors.
# MUST stay in sync with assets/themes/dark.qss and assets/themes/light.qss.
# Palette: deep-teal sidebar (#1a3c40 family) + cyan accent, teal-tinted
# neutrals, semantic green/red/amber for pass/fail/warn.
# ---------------------------------------------------------------------------

# Dark theme palette (industrial dark UI)
DARK_BG_PRIMARY     = "#0a171a"   # window / content background
DARK_BG_SECONDARY   = "#0f2024"   # cards, top bar, inputs
DARK_BG_CARD        = "#0f2024"
DARK_BORDER         = "#1a3c40"   # teal border / selection / primary button
DARK_TEXT_PRIMARY   = "#e8f7fa"
DARK_TEXT_MUTED     = "#5a8f9a"
DARK_ACCENT         = "#22d3ee"   # cyan accent (active states, focus)
DARK_PASS           = "#22c55e"
DARK_FAIL           = "#ef4444"
DARK_RUNNING        = "#f59e0b"
DARK_WARN           = "#f59e0b"
DARK_SIDEBAR_BG     = "#11292c"   # deep teal sidebar
DARK_SIDEBAR_ACTIVE = "#1a3c40"

# Light theme palette
LIGHT_BG_PRIMARY    = "#f4f7f6"   # window / content background
LIGHT_BG_SECONDARY  = "#ffffff"
LIGHT_BG_CARD       = "#ffffff"
LIGHT_BORDER        = "#e2eef0"
LIGHT_TEXT_PRIMARY  = "#1e363b"
LIGHT_TEXT_MUTED    = "#64848b"
LIGHT_ACCENT        = "#0e7490"   # cyan-700 accent (contrast-safe on white)
LIGHT_PASS          = "#16a34a"
LIGHT_FAIL          = "#dc2626"
LIGHT_RUNNING       = "#d97706"
LIGHT_WARN          = "#d97706"
LIGHT_SIDEBAR_BG    = "#1a3c40"   # deep teal sidebar (same as plan)
LIGHT_SIDEBAR_ACTIVE = "rgba(255,255,255,0.15)"

# ---------------------------------------------------------------------------
# Navigation Pages and Sidebar Items
# ---------------------------------------------------------------------------
PAGE_MODEL    = "model"
PAGE_TEST     = "test"
PAGE_MANUAL   = "manual"
PAGE_CONFIG   = "config"
PAGE_IO_LIST  = "io_list"
PAGE_REPORTS  = "reports"
PAGE_SETTINGS = "settings"

# Each entry: (page_id, icon_name, label, allowed_roles)
# icon_name is a key into src.utils.icons.get_icon()
NAV_ITEMS: list[tuple[str, str, str, list[str]]] = [
    (PAGE_MODEL,    "model",    "Model Selection",  [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_OPERATOR]),
    (PAGE_TEST,     "test",     "Live Testing",     [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_OPERATOR]),
    (PAGE_MANUAL,   "manual",   "Manual Control",   [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_OPERATOR]),
    (PAGE_CONFIG,   "config",   "PLC Mapping",      [ROLE_ADMIN]),
    (PAGE_IO_LIST,  "io",       "I/O Diagnostics",  [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_OPERATOR]),
    (PAGE_REPORTS,  "reports",  "Reports & Analytics", [ROLE_ADMIN, ROLE_SUPERVISOR]),
    (PAGE_SETTINGS, "settings", "System Settings",   [ROLE_ADMIN]),
]

# Sidebar section grouping: (section_title, [page_ids in order])
NAV_SECTIONS: list[tuple[str, list[str]]] = [
    ("MONITORING",        [PAGE_MODEL, PAGE_TEST, PAGE_IO_LIST]),
    ("CONTROL & CONFIG",  [PAGE_MANUAL, PAGE_CONFIG, PAGE_REPORTS]),
    ("SYSTEM",            [PAGE_SETTINGS]),
]

# ---------------------------------------------------------------------------
# Timing Defaults (milliseconds unless noted)
# ---------------------------------------------------------------------------
DEFAULT_POLL_MS       = 500   # Default PLC polling interval
DEFAULT_TIMEOUT_MS    = 3000  # Default Modbus request timeout
DEFAULT_RECONNECT_MS  = 3000  # Default delay between reconnect attempts
WRITE_VERIFY_DELAY_MS = 150   # Delay before reading back a written value
IO_LIST_REFRESH_MS    = 250  # I/O list page refresh rate
MAX_WRITE_RETRIES     = 3     # Maximum write retry attempts

# ---------------------------------------------------------------------------
# Serial Port Defaults
# ---------------------------------------------------------------------------
BAUD_RATES: list[int] = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
PARITY_OPTIONS: dict[str, str] = {"E": "Even", "O": "Odd", "N": "None"}
STOP_BITS: list[int] = [1, 2]
DATA_BITS: list[int] = [7, 8]

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def is_plc_configured(host: str) -> bool:
    """Returns True if the PLC host has been set by admin (non-empty)."""
    return bool(host and host.strip())


# ---------------------------------------------------------------------------
# LEGACY CONSTANTS (Backward compatibility for UI components)
# TODO: Migrate UI to use database-driven config and remove these.
# ---------------------------------------------------------------------------

# Y output coil map (Mitsubishi)
Y_COIL_MAP_MITSUBISHI = {
    "Y20": 1296,  # MVD LOW BEAM  (octal 20 = dec 16 → 1280 + 16)
    "Y21": 1297,  # MVD HIGH BEAM (octal 21 = dec 17)
    "Y22": 1298,  # MVD HORN      (octal 22 = dec 18)
    "Y23": 1299,  # MVD LH BLINKER(octal 23 = dec 19)
    "Y24": 1300,  # MVD RH BLINKER(octal 24 = dec 20)
    "Y31": 1305,  # LH CONTACT LOAD CHANGE (octal 31 = dec 25)
    "Y32": 1306,  # RH CONTACT LOAD CHANGE (octal 32 = dec 26)
}

# Test states (D21 value)
STATE_IDLE     = 0   
STATE_RUNNING  = 99  
STATE_COMPLETE = 6   

STATE_LABELS = {
    STATE_IDLE: "IDLE",
    STATE_RUNNING: "RUNNING",
    1: "PASS",
    2: "FAIL",
    3: "BYPASS",
    4: "ERROR",
    5: "WAITING",
    6: "COMPLETE",
}

# D21 message severity mapping
D21_SEVERITY = {
    1:  "green",   2:  "red",     3:  "red",     4:  "red",
    5:  "red",     6:  "red",     7:  "red",     8:  "red",
    9:  "red",     10: "red",     15: "red",     16: "red",
    20: "red",     21: "red",     22: "red",     26: "yellow",
    27: "red",     28: "red",     29: "yellow",  30: "yellow",
}

PLC_RESULT_PASS   = 1
PLC_RESULT_FAIL   = 2
PLC_RESULT_BYPASS = 3

# ---------------------------------------------------------------------------
# Default PLC Register Addresses (used by PLCProfileDialog)
# These are sensible defaults; actual values are stored in the database.
# ---------------------------------------------------------------------------
DEFAULT_STATE_REGISTER           = 21   # D21 — machine state register
DEFAULT_START_COIL               = 100  # M100 — test start trigger coil
DEFAULT_OVERALL_RESULT_REGISTER  = 22   # D22 — overall PASS/FAIL result
DEFAULT_OK_COUNT_REGISTER        = 23   # D23 — OK (pass) counter
DEFAULT_NG_COUNT_REGISTER        = 24   # D24 — NG (fail) counter
