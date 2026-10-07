"""
session_repo.py — Universal PLC Monitor
Manages 'test_sessions' and 'test_results' tables for recording test history.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from .database import Database

logger = logging.getLogger(__name__)


class SessionRepository:
    """
    Repository for production test session recording.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def open_session(self, model_id: int, operator_id: int) -> int:
        """Alias for start_session to match UI/Logic expectations."""
        return self.start_session(model_id, operator_id)

    def start_session(self, model_id: int, operator_id: int) -> int:
        """
        Creates a new test session record.
        """
        query = """
            INSERT INTO test_sessions (model_id, operator_id, started_at, overall_result)
            VALUES (?, ?, datetime('now','utc'), 'PENDING')
        """
        cursor = self.db.execute(query, (model_id, operator_id))
        return cursor.lastrowid

    def close_session(self, session_id: int, ok_count: int, ng_count: int, batch_count: int,
                      notes: str = "", overall_result: str = None) -> bool:
        """Alias for end_session to match UI/Logic expectations."""
        # Note: Logic layer sends overall_result in its own way sometimes
        res = overall_result or "PENDING"
        return self.end_session(session_id, ok_count, ng_count, res)

    def end_session(self, session_id: int, ok_count: int, ng_count: int, overall_result: str) -> bool:
        """
        Closes a test session and records final counts.
        """
        query = """
            UPDATE test_sessions SET 
                ended_at = datetime('now','utc'),
                ok_count = ?,
                ng_count = ?,
                batch_count = ?,
                overall_result = ?
            WHERE id = ?
        """
        batch = ok_count + ng_count
        self.db.execute(query, (ok_count, ng_count, batch, overall_result, session_id))
        return True

    def record_result(
        self,
        session_id: int,
        parameter_id: int, # Mapping to register_id or mapping_id
        param_name: str,
        module_name: str,
        measured_value: float,
        limit_min: float = 0.0,
        limit_max: float = 0.0,
        result: str = "PENDING",
        deviation_pct: float = 0.0,
        raw_value: int = 0,
    ) -> int:
        """
        Records a specific register measurement snapshot for a session.
        Updated to match Logic layer signature.
        """
        query = """
            INSERT INTO test_results (
                session_id, register_id, display_name, group_name,
                measured_value, raw_value, result, timestamp,
                limit_min, limit_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','utc'), ?, ?)
        """
        params = (
            session_id, parameter_id, param_name, module_name,
            measured_value, raw_value, result, limit_min, limit_max
        )
        cursor = self.db.execute(query, params)
        return cursor.lastrowid

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Returns session details joined with model name."""
        query = """
            SELECT s.*, m.name as model_name, u.username as operator_name
            FROM test_sessions s
            JOIN models m ON s.model_id = m.id
            JOIN users u ON s.operator_id = u.id
            WHERE s.id = ?
        """
        return self.db.fetchone(query, (session_id,))

    def get_session_results(self, session_id: int) -> list[Dict[str, Any]]:
        """Returns all measurements for a specific session."""
        return self.db.fetchall(
            "SELECT * FROM test_results WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )

    def add_comment(self, session_id: int, user_id: int, comment: str) -> int:
        """Adds an operator note to a session."""
        query = "INSERT INTO session_comments (session_id, user_id, comment) VALUES (?, ?, ?)"
        cursor = self.db.execute(query, (session_id, user_id, comment))
        return cursor.lastrowid

    def increment_ok(self, session_id: int) -> bool:
        """Increments the ok_count for a session."""
        query = "UPDATE test_sessions SET ok_count = ok_count + 1 WHERE id = ?"
        self.db.execute(query, (session_id,))
        return True

    def increment_ng(self, session_id: int) -> bool:
        """Increments the ng_count for a session."""
        query = "UPDATE test_sessions SET ng_count = ng_count + 1 WHERE id = ?"
        self.db.execute(query, (session_id,))
        return True
