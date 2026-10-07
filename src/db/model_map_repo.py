"""
model_map_repo.py — Universal PLC Monitor
Manages the relationship between models and register library entries.
Configures how each register is displayed and evaluated for a specific model.
"""
from __future__ import annotations

import logging
from typing import Optional

from .database import Database
from src.utils.constants import ROLES, MAX_DASHBOARD_CARDS

logger = logging.getLogger(__name__)


class ModelMapRepo:
    """
    Repository for the model_register_map table.
    Links a model to the specific PLC registers it needs to monitor.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add_mapping(
        self,
        model_id: int,
        register_id: int,
        role: str = "MEASURED",
        display_name: str = "",
        group_name: str = "",
        enabled: bool = True,
        bypass: bool = False,
        show_in_dashboard: bool = True,
        card_position: int = 0,
        pass_value: int = 1,
        fail_value: int = 2,
        limit_min: float = 0.0,
        limit_max: float = 0.0,
    ) -> int:
        """
        Maps a register to a model.

        Args:
            model_id:          Target model.
            register_id:       Register from library.
            role:              MEASURED, RESULT, STATUS, etc.
            display_name:      Override name for UI (defaults to library name).
            group_name:        UI grouping label (e.g. 'Pressure Settings').
            enabled:           Whether to poll this register for this model.
            bypass:            Whether to ignore evaluation for this register.
            show_in_dashboard: Whether to show a card for this register.
            card_position:     Sorting order on the dashboard.
            pass_value:        Modbus value interpreted as PASS (for RESULT role).
            fail_value:        Modbus value interpreted as FAIL (for RESULT role).
            limit_min:         Lower spec threshold for MEASURED role (0.0 = unconfigured).
            limit_max:         Upper spec threshold for MEASURED role (0.0 = unconfigured).
        """
        # 1. Validation
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}")

        # Check for duplicate mapping
        existing = self.db.fetchone(
            "SELECT id FROM model_register_map WHERE model_id = ? AND register_id = ?",
            (model_id, register_id)
        )
        if existing:
            raise ValueError("This register is already mapped to this model.")

        # Default display name to library name if not provided
        if not display_name.strip():
            lib_reg = self.db.fetchone("SELECT name FROM register_library WHERE id = ?", (register_id,))
            if lib_reg:
                display_name = lib_reg["name"]

        query = """
            INSERT INTO model_register_map (
                model_id, register_id, role, display_name, group_name,
                enabled, bypass, show_in_dashboard, card_position,
                pass_value, fail_value, limit_min, limit_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            model_id, register_id, role, display_name, group_name,
            1 if enabled else 0, 1 if bypass else 0, 
            1 if show_in_dashboard else 0, card_position,
            pass_value, fail_value, limit_min, limit_max
        )
        
        cursor = self.db.execute(query, params)
        return cursor.lastrowid

    def get_model_mappings(
        self,
        model_id: int,
        enabled_only: bool = False,
        role: str = None,
    ) -> list[dict]:
        """
        Returns all mappings for a model, joined with register library details.
        """
        query = """
            SELECT m.*, r.register_address, r.register_type, r.data_type, 
                   r.scale_factor, r.decimal_places, r.unit, r.word_swap,
                   r.name as library_name
            FROM model_register_map m
            JOIN register_library r ON m.register_id = r.id
            WHERE m.model_id = ?
        """
        params = [model_id]
        if enabled_only:
            query += " AND m.enabled = 1"
        if role:
            query += " AND m.role = ?"
            params.append(role)

        query += " ORDER BY m.card_position ASC, m.id ASC"
        return self.db.fetchall(query, tuple(params))

    def get_dashboard_registers(self, model_id: int, max_cards: int = MAX_DASHBOARD_CARDS) -> list[dict]:
        """
        Returns up to *max_cards* registers configured for dashboard display.
        """
        query = """
            SELECT m.*, r.register_address, r.register_type, r.data_type, 
                   r.scale_factor, r.decimal_places, r.unit, r.word_swap
            FROM model_register_map m
            JOIN register_library r ON m.register_id = r.id
            WHERE m.model_id = ? AND m.enabled = 1 AND m.show_in_dashboard = 1
            ORDER BY m.card_position ASC
            LIMIT ?
        """
        return self.db.fetchall(query, (model_id, max_cards))

    def get_poll_registers(self, model_id: int) -> list[dict]:
        """
        Returns all registers that ConnectionManager should poll for this model.
        """
        return self.get_model_mappings(model_id, enabled_only=True)

    def update_mapping(self, mapping_id: int, **kwargs) -> bool:
        """Updates specific mapping configuration fields."""
        if not kwargs: return False
        
        fields = []
        params = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            if isinstance(v, bool):
                params.append(1 if v else 0)
            else:
                params.append(v)
        
        params.append(mapping_id)
        query = f"UPDATE model_register_map SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def get_mapping_id(self, model_id: int, register_id: int) -> Optional[int]:
        """Returns the primary key for a specific model-register link."""
        row = self.db.fetchone(
            "SELECT id FROM model_register_map WHERE model_id = ? AND register_id = ?",
            (model_id, register_id)
        )
        return row["id"] if row else None

    def update_card_positions(self, model_id: int, positions: list[tuple[int, int]]) -> None:
        """
        Bulk update card positions (from drag-and-drop events).
        positions: list of (mapping_id, new_index)
        """
        query = "UPDATE model_register_map SET card_position = ? WHERE id = ? AND model_id = ?"
        data = [(pos, mid, model_id) for mid, pos in positions]
        self.db.executemany(query, data)

    def remove_mapping(self, mapping_id: int) -> bool:
        """Removes a single register from a model."""
        self.db.execute("DELETE FROM model_register_map WHERE id = ?", (mapping_id,))
        return True

    def remove_all_mappings(self, model_id: int) -> None:
        """Clears all registers from a model."""
        self.db.execute("DELETE FROM model_register_map WHERE model_id = ?", (model_id,))

    def copy_mappings(self, source_model_id: int, target_model_id: int) -> int:
        """
        Clones all register mappings from one model to another.
        """
        source_mappings = self.db.fetchall(
            "SELECT * FROM model_register_map WHERE model_id = ?", (source_model_id,)
        )
        count = 0
        # Only copy the columns that add_mapping() accepts
        _allowed_keys = {
            "register_id", "role", "display_name", "group_name",
            "enabled", "bypass", "show_in_dashboard", "card_position",
            "pass_value", "fail_value", "limit_min", "limit_max"
        }
        for m in source_mappings:
            try:
                # Filter to only allowed keys
                data = {k: v for k, v in dict(m).items() if k in _allowed_keys}
                data["model_id"] = target_model_id
                
                # Check if register already exists in target to avoid duplicates
                exists = self.db.fetchone(
                    "SELECT id FROM model_register_map WHERE model_id = ? AND register_id = ?",
                    (target_model_id, data["register_id"])
                )
                if not exists:
                    self.add_mapping(**data)
                    count += 1
            except Exception as e:
                logger.error("Failed to copy mapping %s: %s", m.get("id"), e)
        
        return count

    def get_result_registers(self, model_id: int) -> list[dict]:
        """Returns registers used for PASS/FAIL evaluation (RESULT role)."""
        return self.get_model_mappings(model_id, enabled_only=True, role="RESULT")

    def validate_model_mappings(self, model_id: int) -> list[str]:
        """
        Runs diagnostic checks on a model's configuration.
        Returns a list of human-readable warnings.
        """
        warnings = []
        mappings = self.get_model_mappings(model_id, enabled_only=True)
        
        if not mappings:
            warnings.append("Model has no enabled register mappings.")
            return warnings

        # Check for dashboard overflow
        db_count = sum(1 for m in mappings if m["show_in_dashboard"])
        if db_count > MAX_DASHBOARD_CARDS:
            warnings.append(
                f"Model has {db_count} dashboard cards, but UI only supports {MAX_DASHBOARD_CARDS}. "
                "Some will be hidden."
            )

        # Check for duplicate positions
        positions = [m["card_position"] for m in mappings if m["show_in_dashboard"]]
        if len(positions) != len(set(positions)):
            warnings.append("Some dashboard cards have duplicate sequence numbers.")

        return warnings
