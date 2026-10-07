"""
database.py — Universal PLC Monitor
Core database manager using SQLite.
Implements a thread-safe singleton with WAL mode and Foreign Key support.
"""
from __future__ import annotations

import sqlite3
import threading
import logging
import os
from typing import Optional
from contextlib import contextmanager

from src.utils.constants import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    """
    Singleton database manager.
    Provides thread-local connections to prevent concurrency issues.
    """
    _instance: Optional[Database] = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = DB_PATH) -> None:
        if Database._instance is not None:
            raise RuntimeError("Database is a singleton. Use get_instance().")
        
        self.db_path = db_path
        self._local  = threading.local()
        logger.info("Database initialized with path: %s", self.db_path)

    @classmethod
    def get_instance(cls, db_path: str = DB_PATH) -> Database:
        """Returns the singleton Database instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = Database(db_path)
        return cls._instance

    def get_connection(self) -> sqlite3.Connection:
        """
        Returns a thread-local sqlite3 connection.
        Configures WAL mode, Foreign Keys, and row_factory=sqlite3.Row.
        """
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0
            )
            # Performance and Integrity settings
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000") # 64MB cache
            
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            
        return self._local.conn

    def initialize(self, schema_path: str = "schema.sql") -> None:
        """Executes the schema script to create tables and indexes, then runs migrations."""
        if not os.path.exists(schema_path):
            logger.error("Schema file not found at %s", schema_path)
            return

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_script = f.read()

        conn = self.get_connection()
        try:
            conn.executescript(schema_script)
            conn.commit()
            logger.info("Database schema initialized successfully.")
        except sqlite3.Error as e:
            logger.error("Failed to initialize database schema: %s", e)
            conn.rollback()

        # Run migrations for existing databases
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Apply incremental schema migrations for existing databases."""
        conn = self.get_connection()
        migrations = [
            ("v4.1_limit_columns", [
                "ALTER TABLE test_results ADD COLUMN limit_min REAL DEFAULT 0.0",
                "ALTER TABLE test_results ADD COLUMN limit_max REAL DEFAULT 0.0",
            ]),
            ("v4.2_mapping_limit_columns", [
                "ALTER TABLE model_register_map ADD COLUMN limit_min REAL DEFAULT 0.0",
                "ALTER TABLE model_register_map ADD COLUMN limit_max REAL DEFAULT 0.0",
            ]),
            # Phase 1 — bulk data blocks (schema.sql creates register_blocks on
            # fresh installs; these statements cover existing databases where
            # CREATE TABLE ... IF NOT EXISTS in schema.sql already ran, plus the
            # plc_write_log additions that ALTER-only migration can provide).
            ("v4.3_register_blocks", [
                "CREATE TABLE IF NOT EXISTS register_blocks ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " name TEXT NOT NULL UNIQUE,"
                " description TEXT DEFAULT '',"
                " register_type TEXT NOT NULL"
                "  CHECK(register_type IN ('HOLDING','COIL','DISCRETE','INPUT')),"
                " start_address INTEGER NOT NULL"
                "  CHECK(start_address >= 0 AND start_address <= 65535),"
                " count INTEGER NOT NULL CHECK(count > 0 AND count <= 10000),"
                " data_type TEXT NOT NULL DEFAULT 'INT16'"
                "  CHECK(data_type IN ('BOOL','INT16','UINT16','INT32','UINT32','FLOAT32','BCD16','BCD32')),"
                " scale_factor REAL DEFAULT 1.0,"
                " decimal_places INTEGER DEFAULT 2,"
                " unit TEXT DEFAULT '',"
                " word_swap INTEGER DEFAULT 0,"
                " access TEXT NOT NULL DEFAULT 'READ_ONLY'"
                "  CHECK(access IN ('READ_ONLY','READ_WRITE')),"
                " group_name TEXT DEFAULT '',"
                " row_order INTEGER DEFAULT 0,"
                " show_value INTEGER DEFAULT 1,"
                " on_label TEXT DEFAULT 'ON',"
                " off_label TEXT DEFAULT 'OFF',"
                " on_color TEXT DEFAULT '#22c55e',"
                " off_color TEXT DEFAULT '#5a7a9a',"
                " is_active INTEGER DEFAULT 1,"
                " created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,"
                " created_at TEXT DEFAULT (datetime('now','utc')),"
                " updated_at TEXT DEFAULT (datetime('now','utc'))"
                ")",
                "CREATE INDEX IF NOT EXISTS idx_register_blocks_order"
                " ON register_blocks(group_name, row_order)",
            ]),
            ("v4.3_write_log_block_id", [
                "ALTER TABLE plc_write_log ADD COLUMN block_id INTEGER"
                " REFERENCES register_blocks(id) ON DELETE SET NULL",
            ]),
            ("v4.3_write_log_block_index", [
                "CREATE INDEX IF NOT EXISTS idx_write_log_block"
                " ON plc_write_log(block_id)",
            ]),
        ]
        for name, statements in migrations:
            try:
                already_applied = conn.execute(
                    "SELECT 1 FROM db_migrations WHERE name = ?", (name,)
                ).fetchone()
                if already_applied:
                    continue
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO db_migrations (name) VALUES (?)", (name,)
                )
                conn.commit()
                logger.info("Migration '%s' applied successfully.", name)
            except sqlite3.OperationalError as e:
                # Column already exists (ALTER TABLE fails silently on duplicate)
                if "duplicate column" in str(e):
                    conn.execute(
                        "INSERT OR IGNORE INTO db_migrations (name) VALUES (?)", (name,)
                    )
                    conn.commit()
                    logger.info("Migration '%s' already applied (column exists).", name)
                else:
                    logger.error("Migration '%s' failed: %s", name, e)
            except sqlite3.Error as e:
                logger.error("Migration '%s' failed: %s", name, e)

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Executes a non-returning query (INSERT, UPDATE, DELETE)."""
        conn = self.get_connection()
        in_tx = getattr(self._local, "in_tx", False)
        try:
            cursor = conn.execute(query, params)
            if not in_tx:
                conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error("Database execute error: %s\nQuery: %s", e, query)
            if not in_tx:
                conn.rollback()
            raise

    @contextmanager
    def transaction(self):
        """
        Context manager for atomic multi-statement transactions.
        
        Usage::
            with db.transaction():
                db.execute("INSERT ...", params)
                db.execute("UPDATE ...", params)
            # Auto-commits on normal exit, rolls back on exception

        While active, execute()/executemany() defer their per-call commit so
        every statement joins the same transaction (nested calls join too).
        """
        conn = self.get_connection()
        if getattr(self._local, "in_tx", False):
            yield conn  # nested — join the outer transaction
            return
        self._local.in_tx = True
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._local.in_tx = False

    def executemany(self, query: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Executes a batch of queries."""
        conn = self.get_connection()
        in_tx = getattr(self._local, "in_tx", False)
        try:
            cursor = conn.executemany(query, params_list)
            if not in_tx:
                conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error("Database executemany error: %s\nQuery: %s", e, query)
            if not in_tx:
                conn.rollback()
            raise

    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Fetches a single row and returns it as a plain dictionary."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("Database fetchone error: %s\nQuery: %s", e, query)
            raise

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetches all matching rows and returns them as a list of dictionaries."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Database fetchall error: %s\nQuery: %s", e, query)
            raise

    def close_all(self) -> None:
        """
        Note: sqlite3 connections are thread-local. This only closes
        the connection of the calling thread.
        """
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
            logger.debug("Database connection closed for thread: %s", threading.current_thread().name)
