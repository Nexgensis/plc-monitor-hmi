"""
message_repo.py — Universal PLC Monitor
Manages the 'message_register' table for mapping register values to status bar text.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Tuple

from .database import Database

logger = logging.getLogger(__name__)


class MessageRegisterRepo:
    """
    Repository for the status bar message lookup system.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_messages_for_register(self, register_id: int) -> Dict[int, Tuple[str, str]]:
        """
        Retrieves all value-to-message mappings for a specific register ID.
        Returns: { value: (text, color) }
        """
        query = "SELECT trigger_value, message_text, color FROM message_register WHERE register_id = ?"
        rows = self.db.fetchall(query, (register_id,))
        return {int(r["trigger_value"]): (str(r["message_text"]), str(r["color"])) for r in rows}

    def add_message_mapping(
        self,
        register_id: int,
        trigger_value: int,
        message_text: str,
        color: str = "white",
        severity: str = "INFO",
    ) -> int:
        """Adds a new message trigger for a register."""
        query = """
            INSERT INTO message_register (
                register_id, trigger_value, message_text, color, severity
            ) VALUES (?, ?, ?, ?, ?)
        """
        cursor = self.db.execute(query, (register_id, trigger_value, message_text, color, severity))
        return cursor.lastrowid

    def update_message_mapping(self, mapping_id: int, **kwargs) -> bool:
        """Updates a single message mapping."""
        fields = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values())
        params.append(mapping_id)
        query = f"UPDATE message_register SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def delete_message_mapping(self, mapping_id: int) -> bool:
        """Deletes a single message mapping."""
        self.db.execute("DELETE FROM message_register WHERE id = ?", (mapping_id,))
        return True

    def delete_messages_for_register(self, register_id: int) -> None:
        """Clears all mappings for a register."""
        self.db.execute("DELETE FROM message_register WHERE register_id = ?", (register_id,))

    def get_all_mappings(self, register_id: int = None) -> List[Dict[str, Any]]:
        """Returns message mappings, optionally filtered by register."""
        if register_id:
            query = "SELECT * FROM message_register WHERE register_id = ? ORDER BY trigger_value"
            return self.db.fetchall(query, (register_id,))
        else:
            query = """
                SELECT m.*, r.name as register_name
                FROM message_register m
                JOIN register_library r ON m.register_id = r.id
                ORDER BY r.name, m.trigger_value
            """
            return self.db.fetchall(query)
