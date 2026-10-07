"""
model_repo.py — Universal PLC Monitor
Manages the 'models' table: test definitions and their overall configuration.
"""
from __future__ import annotations

import logging
from typing import Optional

from .database import Database

logger = logging.getLogger(__name__)


class ModelRepository:
    """
    Repository for CRUD operations on the models table.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_all_models(self) -> list[dict]:
        """Returns all models ordered by sort_order then name."""
        return self.db.fetchall("SELECT * FROM models ORDER BY sort_order ASC, name ASC")

    def get_model(self, model_id: int) -> Optional[dict]:
        """Returns a single model by ID."""
        return self.db.fetchone("SELECT * FROM models WHERE id = ?", (model_id,))

    def get_model_by_name(self, name: str) -> Optional[dict]:
        """Returns a model by name."""
        return self.db.fetchone("SELECT * FROM models WHERE name = ?", (name.strip(),))

    def create_model(
        self,
        name: str,
        description: str = "",
        model_number: str = "",
        sort_order: int = 0,
    ) -> int:
        """
        Creates a new model definition.

        Args:
            name:         User-friendly name (e.g. 'Front LH Dipper').
            description:  Optional details.
            model_number: Part number or internal code.
            sort_order:   Manual ordering in UI lists.

        Returns:
            The ID of the newly created model.
        """
        name = name.strip()
        if not name:
            raise ValueError("Model name cannot be empty.")
            
        if self.get_model_by_name(name):
            raise ValueError(f"A model named '{name}' already exists.")

        query = """
            INSERT INTO models (name, description, model_number, sort_order)
            VALUES (?, ?, ?, ?)
        """
        cursor = self.db.execute(query, (name, description, model_number, sort_order))
        return cursor.lastrowid

    def update_model(self, model_id: int, **kwargs) -> bool:
        """
        Updates model fields. Validates name uniqueness if changed.
        """
        if "id" in kwargs:
            raise ValueError("Cannot update model ID.")

        current = self.get_model(model_id)
        if not current:
            return False

        if "name" in kwargs:
            new_name = kwargs["name"].strip()
            if not new_name:
                raise ValueError("Model name cannot be empty.")
            if new_name != current["name"] and self.get_model_by_name(new_name):
                raise ValueError(f"Model name '{new_name}' is already in use.")
            kwargs["name"] = new_name

        fields = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values())
        params.append(model_id)
        
        query = f"UPDATE models SET {', '.join(fields)} WHERE id = ?"
        self.db.execute(query, tuple(params))
        return True

    def get_full_model_config(self, model_id: int) -> Optional[dict]:
        """
        Returns a complete model configuration object including parameters
        and module groupings. Expected by TestPage and SessionController.
        """
        model = self.get_model(model_id)
        if not model:
            return None

        # Fetch all mappings with full register details
        query = """
            SELECT m.*, r.register_address, r.register_type, r.data_type, 
                   r.scale_factor, r.decimal_places, r.unit, r.word_swap
            FROM model_register_map m
            JOIN register_library r ON m.register_id = r.id
            WHERE m.model_id = ? AND m.enabled = 1
            ORDER BY m.card_position ASC, m.id ASC
        """
        mappings = self.db.fetchall(query, (model_id,))
        
        # Transform to UI structure
        parameters = []
        module_groups = {}
        
        for m in mappings:
            # Flatten into parameter dict
            p = {
                "id": m["id"],
                "register_id": m["register_id"],
                "param_name": m["display_name"],
                "group_name": m["group_name"] or "General",
                "role": m["role"],
                "address": m["register_address"],
                "type": m["register_type"],
                "data_type": m["data_type"],
                "scale": m["scale_factor"],
                "decimals": m["decimal_places"],
                "unit": m["unit"],
                "swap": bool(m["word_swap"]),
                "pass_value": m["pass_value"],
                "fail_value": m["fail_value"],
                "limit_min": m.get("limit_min", 0.0),
                "limit_max": m.get("limit_max", 0.0),
            }
            parameters.append(p)
            
            # Group for ModuleCard
            grp = p["group_name"]
            if grp not in module_groups:
                module_groups[grp] = []
            module_groups[grp].append(p)
            
        return {
            "model": model,
            "parameters": parameters,
            "module_groups": module_groups
        }

    def delete_model(self, model_id: int) -> bool:
        """
        Deletes a model.
        Note: Foreign Key ON DELETE CASCADE in schema v4.0 automatically
        removes entries in model_register_map.
        """
        self.db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        return True
