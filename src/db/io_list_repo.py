"""
io_list_repo.py — Universal PLC Monitor
Manages the 'io_list_config' table for the dedicated I/O status page.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List

from .database import Database

logger = logging.getLogger(__name__)


class IOListRepo:
    """
    Repository for the live I/O monitoring list.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_io_config(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Returns all I/O row definitions joined with register library details.
        ORDER BY group_name, row_order.
        """
        query = """
            SELECT io.*, r.register_address, r.register_type, r.data_type,
                   r.name as library_name, r.scale_factor, r.word_swap,
                   r.decimal_places, r.unit
            FROM io_list_config io
            JOIN register_library r ON io.register_id = r.id
        """
        if active_only:
            query += " WHERE io.is_active = 1"
            
        query += " ORDER BY io.group_name ASC, io.row_order ASC"
        return self.db.fetchall(query)

    def create_io_row(
        self,
        display_name: str,
        register_id: int,
        group_name: str = "",
        row_order: int = 0,
        show_value: bool = True,
        on_label: str = "ON",
        off_label: str = "OFF",
        on_color: str = "#22c55e",
        off_color: str = "#5a7a9a",
    ) -> int:
        """Adds a new row to the I/O monitoring list."""
        query = """
            INSERT INTO io_list_config (
                display_name, register_id, group_name, row_order,
                show_value, on_label, off_label, on_color, off_color
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            display_name.strip(), register_id, group_name, row_order,
            1 if show_value else 0, on_label, off_label, on_color, off_color
        )
        cursor = self.db.execute(query, params)
        return cursor.lastrowid

    def update_io_row(self, io_id: int, **kwargs) -> bool:
        """Updates I/O row configuration."""
        fields = []
        params = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            if isinstance(v, bool):
                params.append(1 if v else 0)
            else:
                params.append(v)
        
        params.append(io_id)
        query = f"UPDATE io_list_config SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def delete_io_row(self, io_id: int) -> bool:
        """Removes an I/O row."""
        self.db.execute("DELETE FROM io_list_config WHERE id = ?", (io_id,))
        return True

    def get_poll_registers(self) -> List[Dict[str, Any]]:
        """Returns all registers required for the I/O list polling."""
        return self.get_io_config(active_only=True)

    def get_groups(self) -> List[str]:
        """Returns list of unique group names."""
        rows = self.db.fetchall("SELECT DISTINCT group_name FROM io_list_config ORDER BY group_name")
        return [r["group_name"] for r in rows if r["group_name"]]

    def get_all_entries(self, group_name: str = None) -> List[Dict[str, Any]]:
        """Returns all entries, optionally filtered by group."""
        query = """
            SELECT io.*, r.register_address, r.register_type, r.data_type,
                   r.name, r.scale_factor, r.decimal_places, r.unit
            FROM io_list_config io
            JOIN register_library r ON io.register_id = r.id
        """
        params = []
        if group_name:
            query += " WHERE io.group_name = ?"
            params.append(group_name)
        
        query += " ORDER BY io.row_order ASC"
        return self.db.fetchall(query, tuple(params))
