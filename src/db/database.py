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
from typing import Any, Optional

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
        """Executes the schema script to create tables and indexes."""
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

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Executes a non-returning query (INSERT, UPDATE, DELETE)."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error("Database execute error: %s\nQuery: %s", e, query)
            conn.rollback()
            raise

    def executemany(self, query: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Executes a batch of queries."""
        conn = self.get_connection()
        try:
            cursor = conn.executemany(query, params_list)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error("Database executemany error: %s\nQuery: %s", e, query)
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
            return None

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetches all matching rows and returns them as a list of dictionaries."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Database fetchall error: %s\nQuery: %s", e, query)
            return []

    def close_all(self) -> None:
        """
        Note: sqlite3 connections are thread-local. This only closes
        the connection of the calling thread.
        """
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
            logger.debug("Database connection closed for thread: %s", threading.current_thread().name)
