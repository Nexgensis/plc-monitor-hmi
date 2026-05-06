-- migrations/003_fix_register_fk_cascades.sql
-- Fix foreign key constraints on tables that reference register_library
-- These should cascade delete or set null instead of NO ACTION

-- For test_results: This is historical data, so we cascade delete
-- For plc_write_log: This is an audit trail, so we cascade delete

-- NOTE: SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT
-- We must recreate these tables to change their foreign key behavior.

BEGIN TRANSACTION;

-- Create a backup of test_results with CASCADE delete
CREATE TABLE test_results_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL
      REFERENCES test_sessions(id) ON DELETE CASCADE,
    register_id INTEGER NOT NULL
      REFERENCES register_library(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    group_name TEXT DEFAULT '',
    measured_value REAL DEFAULT 0.0,
    raw_value INTEGER DEFAULT 0,
    result TEXT NOT NULL DEFAULT 'PENDING'
      CHECK(result IN ('PASS','FAIL','BYPASS','PENDING')),
    timestamp TEXT DEFAULT (datetime('now','utc'))
);

-- Copy data from old table
INSERT INTO test_results_new
SELECT * FROM test_results;

-- Drop old table
DROP TABLE test_results;

-- Rename new table
ALTER TABLE test_results_new RENAME TO test_results;

-- Create a backup of plc_write_log with CASCADE delete
CREATE TABLE plc_write_log_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now','utc')),
    register_id INTEGER REFERENCES register_library(id) ON DELETE CASCADE,
    register_address INTEGER NOT NULL,
    register_name TEXT NOT NULL,
    value_written TEXT NOT NULL,
    value_readback TEXT DEFAULT NULL,
    write_success INTEGER DEFAULT 0,
    error_message TEXT DEFAULT NULL,
    operator_id INTEGER REFERENCES users(id),
    write_reason TEXT NOT NULL
);

-- Copy data from old table
INSERT INTO plc_write_log_new
SELECT * FROM plc_write_log;

-- Drop old table
DROP TABLE plc_write_log;

-- Rename new table
ALTER TABLE plc_write_log_new RENAME TO plc_write_log;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_test_results_session
  ON test_results(session_id);
CREATE INDEX IF NOT EXISTS idx_write_log_ts
  ON plc_write_log(timestamp);

COMMIT;
