"""
register_library_repo.py — Universal PLC Monitor
Manages the register_library table: the central source of truth for all
PLC registers known to the application.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .database import Database
from src.utils.constants import REG_TYPES, DATA_TYPES

logger = logging.getLogger(__name__)


class RegisterLibraryRepo:
    """
    Repository for CRUD operations on the register_library table.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_register(
        self,
        name: str,
        register_address: int,
        register_type: str,
        data_type: str,
        description: str = "",
        scale_factor: float = 1.0,
        decimal_places: int = 2,
        unit: str = "",
        access: str = "READ_ONLY",
        word_swap: bool = False,
        created_by: int = None,
    ) -> int:
        """
        Creates a new register definition in the library.

        Args:
            name:             Unique, user-friendly name.
            register_address: PLC-native address (0-65535).
            register_type:    HOLDING, COIL, DISCRETE, or INPUT.
            data_type:        INT16, FLOAT32, etc.
            description:      Optional long description.
            scale_factor:     Multiplier for raw -> engineering value.
            decimal_places:   Number of decimals for display.
            unit:             Unit string (e.g. 'mV').
            access:           READ_ONLY or READ_WRITE.
            word_swap:        Whether to swap 16-bit words in 32-bit types.
            created_by:       ID of the user who created it.

        Returns:
            The ID of the newly created register.

        Raises:
            ValueError: On validation failure.
        """
        # 1. Validation
        name = name.strip()
        if not name:
            raise ValueError("Register name cannot be empty.")

        if not (0 <= register_address <= 65535):
            raise ValueError(f"Invalid register address: {register_address}. Must be 0-65535.")

        if register_type not in REG_TYPES:
            raise ValueError(f"Invalid register type: {register_type}. Must be one of {REG_TYPES}.")

        if data_type not in DATA_TYPES:
            raise ValueError(f"Invalid data type: {data_type}. Must be one of {DATA_TYPES}.")

        if access not in ["READ_ONLY", "READ_WRITE"]:
            raise ValueError("Access must be 'READ_ONLY' or 'READ_WRITE'.")

        if scale_factor == 0:
            raise ValueError("Scale factor cannot be zero.")

        # Check name uniqueness
        if self.get_register_by_name(name):
            raise ValueError(f"A register with the name '{name}' already exists.")

        # 2. Persist
        query = """
            INSERT INTO register_library (
                name, register_address, register_type, data_type,
                description, scale_factor, decimal_places, unit,
                access, word_swap, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            name, register_address, register_type, data_type,
            description, scale_factor, decimal_places, unit,
            access, 1 if word_swap else 0, created_by
        )
        
        cursor = self.db.execute(query, params)
        return cursor.lastrowid

    def get_register(self, register_id: int) -> Optional[dict]:
        """Returns a register by ID or None."""
        return self.db.fetchone(
            "SELECT * FROM register_library WHERE id = ?", (register_id,)
        )

    def get_register_by_name(self, name: str) -> Optional[dict]:
        """Returns a register by name or None."""
        return self.db.fetchone(
            "SELECT * FROM register_library WHERE name = ?", (name.strip(),)
        )

    def get_all_registers(
        self,
        register_type: str = None,
        access: str = None,
    ) -> list[dict]:
        """
        Returns all registers, optionally filtered.
        ORDER BY register_type, register_address.
        """
        query = "SELECT * FROM register_library"
        clauses = []
        params = []

        if register_type:
            clauses.append("register_type = ?")
            params.append(register_type)
        if access:
            clauses.append("access = ?")
            params.append(access)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY register_type, register_address"
        return self.db.fetchall(query, tuple(params))

    def get_readable_registers(self) -> list[dict]:
        """Returns all registers (both READ_ONLY and READ_WRITE)."""
        return self.get_all_registers()

    def get_writable_registers(self) -> list[dict]:
        """Returns only READ_WRITE registers."""
        return self.get_all_registers(access="READ_WRITE")

    def update_register(self, register_id: int, **kwargs) -> bool:
        """
        Updates fields of an existing register.
        Validates all provided arguments.
        """
        if "id" in kwargs:
            raise ValueError("The ID of a register cannot be modified.")

        # 1. Fetch current to validate name changes
        current = self.get_register(register_id)
        if not current:
            return False

        if "name" in kwargs:
            new_name = kwargs["name"].strip()
            if not new_name:
                raise ValueError("Register name cannot be empty.")
            if new_name != current["name"] and self.get_register_by_name(new_name):
                raise ValueError(f"Register name '{new_name}' is already in use.")
            kwargs["name"] = new_name

        if "register_type" in kwargs and kwargs["register_type"] not in REG_TYPES:
             raise ValueError("Invalid register type.")

        if "data_type" in kwargs and kwargs["data_type"] not in DATA_TYPES:
             raise ValueError("Invalid data type.")

        # 2. Build dynamic update query
        fields = []
        params = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            if key == "word_swap":
                params.append(1 if value else 0)
            else:
                params.append(value)
        
        params.append(register_id)
        query = f"UPDATE register_library SET {', '.join(fields)} WHERE id = ?"
        
        self.db.execute(query, tuple(params))
        return True

    def delete_register(self, register_id: int) -> bool:
        """
        Deletes a register from the library.
        
        Note: Historical audit data (plc_write_log, test_results) and
        the message_register_id reference will cascade delete automatically.
        
        Fails if the register is currently in active use by models, 
        controls, I/O list, or message mappings.
        """
        usage = self.check_register_in_use(register_id)
        # Check only for active/configuration usage, not historical data
        active_usage = usage["model_maps"] + usage["control_registers"] + usage["io_list"] + usage["message_register"]
        
        if active_usage > 0:
            details = []
            if usage["model_maps"] > 0: details.append(f"{usage['model_maps']} model mappings")
            if usage["control_registers"] > 0: details.append(f"{usage['control_registers']} control buttons")
            if usage["io_list"] > 0: details.append(f"{usage['io_list']} I/O list entries")
            if usage["message_register"] > 0: details.append("Status Message Register")
            
            raise ValueError(
                f"Cannot delete register. It is currently referenced by: {', '.join(details)}."
            )

        self.db.execute("DELETE FROM register_library WHERE id = ?", (register_id,))
        return True

    def check_register_in_use(self, register_id: int) -> dict:
        """
        Checks active references to this register (config usage, not historical data).
        
        Note: Historical audit trails (plc_write_log, test_results) and 
        message_register_id references will cascade delete and are not checked here.
        We only check for active configuration usage that would prevent deletion.
        """
        row_maps = self.db.fetchone("SELECT COUNT(*) as cnt FROM model_register_map WHERE register_id = ?", (register_id,))
        maps = row_maps["cnt"] if row_maps else 0
        
        row_ctrls = self.db.fetchone("SELECT COUNT(*) as cnt FROM control_registers WHERE register_id = ?", (register_id,))
        ctrls = row_ctrls["cnt"] if row_ctrls else 0
        
        row_io = self.db.fetchone("SELECT COUNT(*) as cnt FROM io_list_config WHERE register_id = ?", (register_id,))
        io = row_io["cnt"] if row_io else 0
        
        row_msg = self.db.fetchone("SELECT COUNT(*) as cnt FROM message_register WHERE register_id = ?", (register_id,))
        msg = row_msg["cnt"] if row_msg else 0

        total = maps + ctrls + io + msg
        return {
            "model_maps": maps,
            "control_registers": ctrls,
            "io_list": io,
            "message_register": msg,
            "total": total,
            "can_delete": total == 0
        }

    def search_registers(self, query: str) -> list[dict]:
        """
        Searches by name substring or exact integer address.
        """
        query_str = query.strip()
        if not query_str:
            return self.get_all_registers()

        # Is it a number?
        if query_str.isdigit():
            return self.db.fetchall(
                "SELECT * FROM register_library WHERE register_address = ? OR name LIKE ? "
                "ORDER BY register_type, register_address",
                (int(query_str), f"%{query_str}%")
            )
        else:
            return self.db.fetchall(
                "SELECT * FROM register_library WHERE name LIKE ? "
                "ORDER BY register_type, register_address",
                (f"%{query_str}%",)
            )

    def get_poll_list(self, register_ids: list[int]) -> list[dict]:
        """
        Retrieves full details for a batch of register IDs.
        Used by ConnectionManager to build its internal polling structures.
        """
        if not register_ids:
            return []
            
        placeholders = ", ".join(["?"] * len(register_ids))
        query = f"""
            SELECT id as register_id, name, register_address, register_type, 
                   data_type, scale_factor, decimal_places, word_swap, unit
            FROM register_library 
            WHERE id IN ({placeholders})
        """
        return self.db.fetchall(query, tuple(register_ids))

    def export_library(self) -> list[dict]:
        """Returns all registers for JSON export."""
        return self.get_all_registers()

    def import_library(
        self,
        registers: list[dict],
        created_by: int,
        overwrite: bool = False,
    ) -> dict:
        """
        Imports a list of register definitions.
        """
        stats = {"imported": 0, "skipped": 0, "errors": 0}
        
        for reg in registers:
            try:
                existing = self.get_register_by_name(reg["name"])
                if existing:
                    if overwrite:
                        # Strip id and update existing
                        data = reg.copy()
                        if "id" in data: del data["id"]
                        self.update_register(existing["id"], **data)
                        stats["imported"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    # Create new
                    self.create_register(
                        name             = reg["name"],
                        register_address = reg["register_address"],
                        register_type    = reg["register_type"],
                        data_type        = reg["data_type"],
                        description      = reg.get("description", ""),
                        scale_factor     = reg.get("scale_factor", 1.0),
                        decimal_places   = reg.get("decimal_places", 2),
                        unit             = reg.get("unit", ""),
                        access           = reg.get("access", "READ_ONLY"),
                        word_swap        = bool(reg.get("word_swap", 0)),
                        created_by       = created_by
                    )
                    stats["imported"] += 1
            except Exception as e:
                logger.error("Import error for register %s: %s", reg.get("name"), e)
                stats["errors"] += 1
                
        return stats
