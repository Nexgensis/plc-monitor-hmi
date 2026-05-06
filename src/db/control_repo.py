"""
control_repo.py — Universal PLC Monitor
Manages the 'control_registers' table for user-definable write operations.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List

from .database import Database

logger = logging.getLogger(__name__)


class ControlRegisterRepo:
    """
    Repository for UI control buttons (Start, Stop, Reset, etc.).
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_all_controls(self) -> List[Dict[str, Any]]:
        """
        Returns all control definitions joined with their register library 
        details. ORDER BY sort_order.
        """
        query = """
            SELECT c.*, r.name as register_name, r.register_address, 
                   r.register_type, r.data_type, r.word_swap
            FROM control_registers c
            JOIN register_library r ON c.register_id = r.id
            ORDER BY c.sort_order ASC, c.name ASC
        """
        return self.db.fetchall(query)

    def get_control_by_type(self, control_type: str) -> Dict[str, Any] | None:
        """Finds a control button by its functional type (e.g. 'START_TEST')."""
        query = """
            SELECT c.*, r.register_address, r.register_type, r.data_type, r.word_swap
            FROM control_registers c
            JOIN register_library r ON c.register_id = r.id
            WHERE c.control_type = ?
            LIMIT 1
        """
        return self.db.fetchone(query, (control_type,))

    def create_control(
        self,
        name: str,
        register_id: int,
        control_type: str,
        write_value: int = 1,
        reset_after_ms: int = 0,
        confirm_required: bool = False,
        description: str = "",
        sort_order: int = 0,
    ) -> int:
        """Defines a new control button."""
        query = """
            INSERT INTO control_registers (
                name, register_id, control_type, write_value, 
                reset_after_ms, confirm_required, description, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            name.strip(), register_id, control_type, write_value,
            reset_after_ms, 1 if confirm_required else 0, description, sort_order
        )
        cursor = self.db.execute(query, params)
        return cursor.lastrowid

    def update_control(self, control_id: int, **kwargs) -> bool:
        """Updates control fields."""
        fields = []
        params = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            if isinstance(v, bool):
                params.append(1 if v else 0)
            else:
                params.append(v)
        
        params.append(control_id)
        query = f"UPDATE control_registers SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def delete_control(self, control_id: int) -> bool:
        """Removes a control button."""
        self.db.execute("DELETE FROM control_registers WHERE id = ?", (control_id,))
        return True
