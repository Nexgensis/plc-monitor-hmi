"""
plc_profile_repo.py — Universal PLC Monitor
Manages the single-row plc_profile table for global connection settings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from .database import Database

logger = logging.getLogger(__name__)


class PLCProfileRepository:
    """
    Repository for global PLC configuration.
    Handles ID=1 profile row.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_profile(self) -> Dict[str, Any]:
        """
        Retrieves the global PLC profile.
        If missing (rare), it re-seeds the default profile.
        """
        row = self.db.fetchone("SELECT * FROM plc_profile WHERE id = 1")
        if not row:
            # Should be seeded by seed.py, but fallback for safety
            self.db.execute("INSERT OR IGNORE INTO plc_profile (id) VALUES (1)")
            row = self.db.fetchone("SELECT * FROM plc_profile WHERE id = 1")
        return row

    def update_profile(self, **kwargs) -> bool:
        """
        Updates connection settings.
        Validates keys against table schema.
        """
        allowed_keys = {
            "brand", "protocol", "host", "port", "slave_id",
            "com_port", "baud_rate", "parity", "data_bits", "stop_bits",
            "poll_interval_ms", "timeout_ms", "reconnect_delay_ms", "max_retries",
            "message_register_id"
        }

        updates = {k: v for k, v in kwargs.items() if k in allowed_keys}
        if not updates:
            return False

        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        fields = [f"{k} = ?" for k in updates.keys()]
        params = list(updates.values())
        params.append(1) # WHERE id = 1

        query = f"UPDATE plc_profile SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        logger.info("PLC profile updated: %s", list(updates.keys()))
        return True

    def update_diagnostics(self, last_error: str = None, success: bool = True) -> None:
        """
        Updates runtime quality metrics.
        """
        if success:
            query = """
                UPDATE plc_profile SET 
                    last_connected_at = datetime('now','utc'),
                    consecutive_errors = 0,
                    last_error = NULL
                WHERE id = 1
            """
            self.db.execute(query)
        else:
            query = """
                UPDATE plc_profile SET 
                    consecutive_errors = consecutive_errors + 1,
                    last_error = ?
                WHERE id = 1
            """
            self.db.execute(query, (last_error,))

    def is_configured(self) -> bool:
        """
        Returns True if the PLC profile has been minimally configured.
        We check for a non-empty host (TCP) or com_port (RTU).
        """
        profile = self.get_profile()
        if not profile:
            return False
        if profile.get("protocol") == "TCP":
            return bool(profile.get("host", "").strip())
        else:
            return bool(profile.get("com_port", "").strip())

    def get_message_config(self) -> Dict[int, Dict[str, Any]]:

        """
        Retrieves all messages from message_register for the current 
        message_register_id.
        Returns mapping of value -> message_dict.
        """
        # This repository only handles plc_profile. 
        # Message lookups are in MessageRegisterRepo.
        return {}
