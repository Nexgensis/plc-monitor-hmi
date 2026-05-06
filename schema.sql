-- Universal PLC Monitor — Zero Hardcoded Addresses or Names
-- Schema version 4.0
-- Inline comment on every column explaining its purpose

PRAGMA foreign_keys = ON;

--- TABLE 1: users ---
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for each user
    username TEXT NOT NULL UNIQUE,          -- Unique login name
    role TEXT NOT NULL                     -- Access level: ADMIN, OPERATOR, or SUPERVISOR
      CHECK(role IN ('ADMIN','OPERATOR','SUPERVISOR')),
    password_hash TEXT NOT NULL,           -- Argon2 or similar hashed password
    created_at TEXT DEFAULT (datetime('now','utc')), -- Timestamp of account creation
    last_login TEXT DEFAULT NULL           -- Timestamp of last successful login
);

--- TABLE 2: plc_profile ---
-- Single row (id=1). Global PLC connection config.
CREATE TABLE IF NOT EXISTS plc_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,      -- Static ID to ensure only one profile exists
    brand TEXT NOT NULL DEFAULT 'mitsubishi' -- PLC Brand (determines address offset logic)
      CHECK(brand IN ('mitsubishi','delta','generic')),
    protocol TEXT NOT NULL DEFAULT 'TCP'   -- Communication protocol (TCP or RTU)
      CHECK(protocol IN ('TCP','RTU')),

    -- TCP settings
    host TEXT NOT NULL DEFAULT '',         -- PLC IP address (e.g., 192.168.1.5)
    port INTEGER NOT NULL DEFAULT 502,     -- Modbus TCP port (default 502)
    slave_id INTEGER NOT NULL DEFAULT 1,   -- Modbus Unit ID / Slave Address

    -- RTU/Serial settings (used when protocol='RTU')
    com_port TEXT DEFAULT '',              -- Serial port name (e.g., COM3 or /dev/ttyUSB0)
    baud_rate INTEGER DEFAULT 9600,        -- Serial baud rate (e.g., 9600, 19200, 115200)
    parity TEXT DEFAULT 'E'                -- Serial parity: E=Even, O=Odd, N=None
      CHECK(parity IN ('E','O','N')),
    data_bits INTEGER DEFAULT 8            -- Serial data bits (7 or 8)
      CHECK(data_bits IN (7,8)),
    stop_bits INTEGER DEFAULT 1            -- Serial stop bits (1 or 2)
      CHECK(stop_bits IN (1,2)),

    -- Polling and timing
    poll_interval_ms INTEGER NOT NULL DEFAULT 500, -- Frequency of PLC register polling
    timeout_ms INTEGER NOT NULL DEFAULT 3000,      -- Wait time for Modbus response
    reconnect_delay_ms INTEGER NOT NULL DEFAULT 3000, -- Delay before retry after disconnect
    max_retries INTEGER NOT NULL DEFAULT 3,         -- Max retries before marking failure

    -- Connection quality tracking (updated at runtime)
    last_connected_at TEXT DEFAULT NULL,   -- Timestamp of last successful communication
    last_error TEXT DEFAULT NULL,          -- String describing the last error encountered
    consecutive_errors INTEGER DEFAULT 0,  -- Count of failed requests since last success

    -- Message register configuration
    message_register_id INTEGER            -- Register ID for status bar messages
      REFERENCES register_library(id) ON DELETE SET NULL,

    updated_at TEXT DEFAULT (datetime('now','utc')) -- Timestamp of last config update
);

--- TABLE 3: register_library ---
-- Single source of truth for ALL registers the app knows about.
CREATE TABLE IF NOT EXISTS register_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique identifier for the register
    name TEXT NOT NULL UNIQUE,             -- User-defined name (e.g., 'Dipper LOW Current')
    description TEXT DEFAULT '',           -- Detailed notes for engineering reference
    register_address INTEGER NOT NULL,     -- The address as written in the PLC program
    register_type TEXT NOT NULL DEFAULT 'HOLDING' -- Modbus table type (HOLDING, COIL, etc.)
      CHECK(register_type IN ('HOLDING','COIL','DISCRETE','INPUT')),
    data_type TEXT NOT NULL DEFAULT 'INT16' -- How to interpret the bits (INT16, FLOAT32, etc.)
      CHECK(data_type IN ('BOOL','INT16','UINT16','INT32','UINT32','FLOAT32','BCD16','BCD32')),
    scale_factor REAL DEFAULT 1.0,         -- Multiplier to convert raw integer to real value
    decimal_places INTEGER DEFAULT 2,      -- Precision for UI display
    unit TEXT DEFAULT '',                  -- Unit of measure (e.g., 'A', 'mV', 'rpm')
    access TEXT NOT NULL DEFAULT 'READ_ONLY' -- Access permission (READ_ONLY or READ_WRITE)
      CHECK(access IN ('READ_ONLY','READ_WRITE')),
    word_swap INTEGER DEFAULT 0,           -- 1 = swap words for 32-bit types (Endianness)
    created_by INTEGER REFERENCES users(id) ON DELETE CASCADE, -- User who added this register
    created_at TEXT DEFAULT (datetime('now','utc')), -- Entry creation timestamp
    updated_at TEXT DEFAULT (datetime('now','utc'))  -- Last modification timestamp
);

--- TABLE 4: models ---
-- User-created models. No hardcoded names.
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique model identifier
    name TEXT NOT NULL UNIQUE,             -- User-defined model name (e.g., 'SW-0256A')
    description TEXT DEFAULT '',           -- Notes about the model
    model_number TEXT DEFAULT '',          -- Manufacturer model/part number
    sort_order INTEGER DEFAULT 0,          -- Rank for display order in selection lists
    is_active INTEGER DEFAULT 1,           -- Soft-delete flag (1=Active, 0=Disabled)
    created_at TEXT DEFAULT (datetime('now','utc')) -- Creation timestamp
);

--- TABLE 5: model_register_map ---
-- Links registers from the library to a specific model.
CREATE TABLE IF NOT EXISTS model_register_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique mapping identifier
    model_id INTEGER NOT NULL              -- Reference to the model
      REFERENCES models(id) ON DELETE CASCADE,
    register_id INTEGER NOT NULL           -- Reference to the register in library
      REFERENCES register_library(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'MEASURED'  -- Functional role (MEASURED, RESULT, STATUS, etc.)
      CHECK(role IN ('MEASURED','RESULT','STATUS','LIMIT_MIN','LIMIT_MAX','COUNTER','TIMER','CUSTOM')),
    display_name TEXT NOT NULL DEFAULT '', -- Model-specific override for library name
    group_name TEXT DEFAULT '',            -- UI grouping (e.g., 'Dipper Module')
    enabled INTEGER DEFAULT 1,             -- 1 if active for this model
    bypass INTEGER DEFAULT 0,              -- 1 if excluded from PASS/FAIL evaluation
    show_in_dashboard INTEGER DEFAULT 1,   -- 1 to show as a card on dashboard
    card_position INTEGER DEFAULT 0,       -- Manual order for dashboard layout
    pass_value INTEGER DEFAULT 1,          -- Raw value indicating PASS for RESULT role
    fail_value INTEGER DEFAULT 2,          -- Raw value indicating FAIL for RESULT role
    UNIQUE(model_id, register_id)          -- Prevent duplicate register mapping per model
);

--- TABLE 6: control_registers ---
-- User-configurable write operations.
CREATE TABLE IF NOT EXISTS control_registers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique control identifier
    name TEXT NOT NULL UNIQUE,             -- Button label (e.g., 'Start Test')
    register_id INTEGER NOT NULL           -- Reference to a READ_WRITE register
      REFERENCES register_library(id) ON DELETE CASCADE,
    control_type TEXT NOT NULL             -- Functional type (START_TEST, RESET_BATCH, etc.)
      CHECK(control_type IN ('START_TEST','STOP_TEST','RESET_BATCH','RESET_COUNTER','ACK','BYPASS_FLAG','CUSTOM')),
    write_value INTEGER NOT NULL DEFAULT 1, -- Data written when button clicked
    reset_after_ms INTEGER DEFAULT 0,      -- Delay before writing 0 (pulse operation)
    confirm_required INTEGER DEFAULT 0,    -- 1 = Require confirmation dialog
    description TEXT DEFAULT '',           -- Explanation of what this control does
    sort_order INTEGER DEFAULT 0           -- Order in the Control Panel
);

--- TABLE 7: io_list_config ---
-- Live status monitoring list for I/O page.
CREATE TABLE IF NOT EXISTS io_list_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique I/O row identifier
    display_name TEXT NOT NULL,            -- Label (e.g., 'Proximity Sensor X1')
    register_id INTEGER NOT NULL           -- Register to monitor
      REFERENCES register_library(id) ON DELETE CASCADE,
    group_name TEXT DEFAULT '',            -- Grouping (e.g., 'Inputs', 'Outputs')
    row_order INTEGER DEFAULT 0,           -- Display order within group
    show_value INTEGER DEFAULT 1,          -- 1=Numeric, 0=ON/OFF labels only
    on_label TEXT DEFAULT 'ON',            -- Text when non-zero (e.g., 'ACTIVE')
    off_label TEXT DEFAULT 'OFF',          -- Text when zero
    on_color TEXT DEFAULT '#22c55e',       -- UI color hex for non-zero
    off_color TEXT DEFAULT '#5a7a9a',      -- UI color hex for zero
    is_active INTEGER DEFAULT 1            -- Soft-delete flag
);

--- TABLE 8: message_register ---
-- Maps register values to status bar messages.
CREATE TABLE IF NOT EXISTS message_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique message mapping identifier
    register_id INTEGER NOT NULL           -- Register used as the status index
      REFERENCES register_library(id) ON DELETE CASCADE,
    trigger_value INTEGER NOT NULL,        -- Value that triggers this message
    message_text TEXT NOT NULL,            -- The message displayed in the UI
    color TEXT NOT NULL DEFAULT 'white'    -- Indicator color (green, red, yellow, etc.)
      CHECK(color IN ('green','red','yellow','white','amber')),
    severity TEXT DEFAULT 'INFO'           -- Logic severity (INFO, WARNING, ERROR, CRITICAL)
      CHECK(severity IN ('INFO','WARNING','ERROR','CRITICAL')),
    UNIQUE(register_id, trigger_value)     -- Unique message per value per register
);

--- TABLE 9: test_sessions ---
-- Recording of a specific production test run.
CREATE TABLE IF NOT EXISTS test_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique session identifier
    model_id INTEGER NOT NULL              -- Model being tested
      REFERENCES models(id),
    operator_id INTEGER NOT NULL           -- User performing the test
      REFERENCES users(id),
    started_at TEXT DEFAULT (datetime('now','utc')), -- Start timestamp
    ended_at TEXT DEFAULT NULL,            -- Completion timestamp
    ok_count INTEGER DEFAULT 0,            -- Number of units passed
    ng_count INTEGER DEFAULT 0,            -- Number of units failed
    batch_count INTEGER DEFAULT 0,         -- Total units processed in session
    overall_result TEXT DEFAULT 'PENDING'  -- PASS, FAIL, or current PENDING status
      CHECK(overall_result IN ('PASS','FAIL','PENDING'))
);

--- TABLE 10: test_results ---
-- Snapshot of measurements for every register in a session.
CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique result record ID
    session_id INTEGER NOT NULL            -- Link to the test session
      REFERENCES test_sessions(id) ON DELETE CASCADE,
    register_id INTEGER NOT NULL           -- The library register measured
      REFERENCES register_library(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,            -- Name snapshot at time of test
    group_name TEXT DEFAULT '',            -- Group snapshot at time of test
    measured_value REAL DEFAULT 0.0,       -- Processed value (scaled)
    raw_value INTEGER DEFAULT 0,           -- Raw integer from PLC
    result TEXT NOT NULL DEFAULT 'PENDING' -- Outcome: PASS, FAIL, BYPASS
      CHECK(result IN ('PASS','FAIL','BYPASS','PENDING')),
    timestamp TEXT DEFAULT (datetime('now','utc')) -- Measurement timestamp
);

--- TABLE 11: plc_write_log ---
-- Audit trail of all write commands sent to the PLC.
CREATE TABLE IF NOT EXISTS plc_write_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique log entry ID
    timestamp TEXT DEFAULT (datetime('now','utc')), -- Time of write
    register_id INTEGER REFERENCES register_library(id) ON DELETE CASCADE, -- Target register (if from library)
    register_address INTEGER NOT NULL,     -- Modbus address targeted
    register_name TEXT NOT NULL,           -- Name of the register at time of write
    value_written TEXT NOT NULL,           -- The value sent to the PLC
    value_readback TEXT DEFAULT NULL,      -- Read-back verification value (optional)
    write_success INTEGER DEFAULT 0,       -- 1 if write was confirmed successful
    error_message TEXT DEFAULT NULL,       -- Description of failure if applicable
    operator_id INTEGER REFERENCES users(id), -- User who initiated the write
    write_reason TEXT NOT NULL             -- Manual click, Auto-logic, etc.
);

--- TABLE 12: session_comments ---
-- Operator notes for specific test sessions.
CREATE TABLE IF NOT EXISTS session_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique comment identifier
    session_id INTEGER NOT NULL            -- Target session
      REFERENCES test_sessions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id), -- Comment author
    comment TEXT NOT NULL,                 -- Note content
    created_at TEXT DEFAULT (datetime('now','utc')) -- Timestamp
);

--- TABLE 13: app_config ---
-- Global application settings (theme, intervals, etc.).
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,                  -- Unique setting key (e.g., 'theme')
    value TEXT NOT NULL,                   -- Setting value as string
    updated_at TEXT DEFAULT (datetime('now','utc')) -- Last update timestamp
);

--- TABLE 14: db_migrations ---
-- Tracking database schema versions and patches.
CREATE TABLE IF NOT EXISTS db_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Unique migration ID
    name TEXT NOT NULL UNIQUE,             -- Migration filename or version label
    applied_at TEXT DEFAULT (datetime('now','utc')) -- Execution timestamp
);

--- INDEXES ---
-- Optimization for common queries
CREATE INDEX IF NOT EXISTS idx_model_reg_map_model
  ON model_register_map(model_id);         -- Faster model register lookup
CREATE INDEX IF NOT EXISTS idx_model_reg_map_reg
  ON model_register_map(register_id);      -- Cross-reference indexing
CREATE INDEX IF NOT EXISTS idx_model_reg_map_pos
  ON model_register_map(model_id, card_position); -- Dashboard ordering
CREATE INDEX IF NOT EXISTS idx_test_results_session
  ON test_results(session_id);            -- Faster session report generation
CREATE INDEX IF NOT EXISTS idx_write_log_ts
  ON plc_write_log(timestamp);            -- Chronological audit searches
CREATE INDEX IF NOT EXISTS idx_io_list_order
  ON io_list_config(group_name, row_order); -- Sorted I/O display
CREATE INDEX IF NOT EXISTS idx_msg_reg_value
  ON message_register(register_id, trigger_value); -- Fast status message lookup
CREATE INDEX IF NOT EXISTS idx_sessions_model
  ON test_sessions(model_id);             -- Filtering reports by model
CREATE INDEX IF NOT EXISTS idx_sessions_started
  ON test_sessions(started_at);           -- Filtering reports by date

-- End of Schema version 4.0

--- INITIAL DATA ---
-- Default users (Username matches Role for easy login)
INSERT OR IGNORE INTO users (username, role, password_hash) VALUES ('ADMIN', 'ADMIN', 'ADMIN');
INSERT OR IGNORE INTO users (username, role, password_hash) VALUES ('OPERATOR', 'OPERATOR', 'OPERATOR');
INSERT OR IGNORE INTO users (username, role, password_hash) VALUES ('SUPERVISOR', 'SUPERVISOR', 'SUPERVISOR');

-- Default config
INSERT OR IGNORE INTO app_config (key, value) VALUES ('first_run', '1');
INSERT OR IGNORE INTO app_config (key, value) VALUES ('theme', 'dark');
INSERT OR IGNORE INTO app_config (key, value) VALUES ('language', 'en');
