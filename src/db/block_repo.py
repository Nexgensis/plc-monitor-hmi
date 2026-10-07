"""
block_repo.py — Universal PLC Monitor
Manages the 'register_blocks' table: contiguous address ranges polled and
written in bulk (batched reads, FC0F/FC16 multi-writes).

Block semantics:
  - COIL/DISCRETE blocks: `count` = number of bits, data_type is always BOOL.
  - HOLDING/INPUT blocks: `count` = number of 16-bit words; `data_type`
    defines how elements are decoded (count must be a multiple of the
    data type's word stride).
  - DISCRETE and INPUT blocks are always READ_ONLY (protocol read-only tables).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .database import Database
from src.utils.constants import (
    REG_TYPES,
    REG_TYPE_COIL,
    REG_TYPE_DISCRETE,
    REG_TYPE_INPUT,
    DATA_TYPES,
    DATA_TYPE_BOOL,
    DATA_TYPE_REGISTER_COUNT,
    ACCESS_READ_ONLY,
    ACCESS_READ_WRITE,
    MAX_BLOCK_COUNT_REGS,
    MAX_BLOCK_COUNT_BITS,
)

logger = logging.getLogger(__name__)

# Columns a caller may set via create/update (guard against SQL column injection).
_WRITABLE_COLUMNS = frozenset({
    "name", "description", "register_type", "start_address", "count",
    "data_type", "scale_factor", "decimal_places", "unit", "word_swap",
    "access", "group_name", "row_order", "show_value",
    "on_label", "off_label", "on_color", "off_color",
    "is_active", "created_by",
})

_BIT_TYPES = (REG_TYPE_COIL, REG_TYPE_DISCRETE)
_READ_ONLY_TYPES = (REG_TYPE_DISCRETE, REG_TYPE_INPUT)


class BlockRepo:
    """
    Repository for CRUD operations on the register_blocks table.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @staticmethod
    def max_count_for(register_type: str) -> int:
        """Max allowed count for a block of the given register type."""
        if register_type in _BIT_TYPES:
            return MAX_BLOCK_COUNT_BITS
        return MAX_BLOCK_COUNT_REGS

    @staticmethod
    def stride_for(register_type: str, data_type: str) -> int:
        """Words consumed per element (1 for bit blocks)."""
        if register_type in _BIT_TYPES:
            return 1
        return DATA_TYPE_REGISTER_COUNT.get(data_type, 1)

    def _validate(self, fields: Dict[str, Any], exclude_id: int = None) -> Dict[str, Any]:
        """
        Validates and normalizes block fields.

        Returns the normalized field dict (bit blocks force data_type=BOOL;
        read-only tables force access=READ_ONLY).

        Raises:
            ValueError: On any validation failure.
        """
        f = dict(fields)

        name = str(f.get("name", "")).strip()
        if not name:
            raise ValueError("Block name cannot be empty.")
        f["name"] = name

        register_type = f.get("register_type")
        if register_type not in REG_TYPES:
            raise ValueError(
                f"Invalid register type: {register_type!r}. Must be one of {REG_TYPES}."
            )
        f["register_type"] = register_type

        try:
            start = int(f.get("start_address"))
            count = int(f.get("count"))
        except (TypeError, ValueError):
            raise ValueError("Start address and count must be integers.")
        if not (0 <= start <= 65535):
            raise ValueError(f"Invalid start address: {start}. Must be 0-65535.")
        if count <= 0:
            raise ValueError(f"Count must be greater than zero (got {count}).")

        max_count = self.max_count_for(register_type)
        if count > max_count:
            raise ValueError(
                f"Count {count} exceeds the maximum of {max_count} "
                f"for {register_type} blocks."
            )
        if start + count - 1 > 65535:
            raise ValueError(
                f"Range {start}..{start + count - 1} exceeds address 65535."
            )
        f["start_address"] = start
        f["count"] = count

        # Data type rules: bit blocks are always BOOL; register blocks decode
        # with the selected data type and count must fit whole elements.
        if register_type in _BIT_TYPES:
            f["data_type"] = DATA_TYPE_BOOL
        else:
            data_type = f.get("data_type") or "INT16"
            if data_type not in DATA_TYPES:
                raise ValueError(
                    f"Invalid data type: {data_type!r}. Must be one of {DATA_TYPES}."
                )
            if data_type == DATA_TYPE_BOOL:
                raise ValueError(
                    "Data type BOOL is only valid for COIL/DISCRETE blocks."
                )
            stride = DATA_TYPE_REGISTER_COUNT.get(data_type, 1)
            if count % stride != 0:
                raise ValueError(
                    f"Count {count} must be a multiple of {stride} for {data_type} "
                    f"(whole elements only)."
                )
            f["data_type"] = data_type

        # Access rules: protocol read-only tables can never be written.
        access = f.get("access") or ACCESS_READ_ONLY
        if access not in (ACCESS_READ_ONLY, ACCESS_READ_WRITE):
            raise ValueError("Access must be 'READ_ONLY' or 'READ_WRITE'.")
        if register_type in _READ_ONLY_TYPES and access == ACCESS_READ_WRITE:
            raise ValueError(
                f"{register_type} blocks are read-only; access must be READ_ONLY."
            )
        f["access"] = access

        scale = f.get("scale_factor", 1.0)
        try:
            scale = float(scale)
        except (TypeError, ValueError):
            raise ValueError("Scale factor must be a number.")
        if scale == 0:
            raise ValueError("Scale factor cannot be zero.")
        f["scale_factor"] = scale

        try:
            dp = int(f.get("decimal_places", 2))
        except (TypeError, ValueError):
            raise ValueError("Decimal places must be an integer.")
        if not (0 <= dp <= 6):
            raise ValueError(f"Decimal places must be 0-6 (got {dp}).")
        f["decimal_places"] = dp

        # Name uniqueness (unless updating the same row).
        existing = self.get_block_by_name(name)
        if existing and existing["id"] != exclude_id:
            raise ValueError(f"A block with the name '{name}' already exists.")

        return f

    # ------------------------------------------------------------------
    # Create / Update / Delete
    # ------------------------------------------------------------------
    def create_block(
        self,
        name: str,
        register_type: str,
        start_address: int,
        count: int,
        data_type: str = "INT16",
        description: str = "",
        scale_factor: float = 1.0,
        decimal_places: int = 2,
        unit: str = "",
        word_swap: bool = False,
        access: str = ACCESS_READ_ONLY,
        group_name: str = "",
        row_order: int = 0,
        show_value: bool = True,
        on_label: str = "ON",
        off_label: str = "OFF",
        on_color: str = "#22c55e",
        off_color: str = "#5a7a9a",
        is_active: bool = True,
        created_by: int = None,
    ) -> int:
        """
        Creates a new block definition.

        Returns:
            The ID of the newly created block.

        Raises:
            ValueError: On validation failure (including duplicate name).
        """
        fields = self._validate({
            "name": name,
            "description": description,
            "register_type": register_type,
            "start_address": start_address,
            "count": count,
            "data_type": data_type,
            "scale_factor": scale_factor,
            "decimal_places": decimal_places,
            "unit": unit,
            "word_swap": word_swap,
            "access": access,
            "group_name": group_name,
            "row_order": row_order,
            "show_value": show_value,
            "on_label": on_label,
            "off_label": off_label,
            "on_color": on_color,
            "off_color": off_color,
            "is_active": is_active,
            "created_by": created_by,
        })

        cols = [c for c in _WRITABLE_COLUMNS if c in fields]
        query = (
            f"INSERT INTO register_blocks ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})"
        )
        params = tuple(
            (1 if fields[c] else 0) if isinstance(fields[c], bool) else fields[c]
            for c in cols
        )
        cursor = self.db.execute(query, params)
        logger.info(
            "Created block '%s' (%s %d..%d)",
            fields["name"], fields["register_type"],
            fields["start_address"],
            fields["start_address"] + fields["count"] - 1,
        )
        return cursor.lastrowid

    def update_block(self, block_id: int, **kwargs) -> bool:
        """
        Updates a block. Provided fields are merged over the existing row
        and the combined result is re-validated (so changing register_type,
        count, data_type, or start_address cannot produce an invalid block).

        Raises:
            ValueError: On validation failure or unknown column.
        """
        unknown = set(kwargs) - _WRITABLE_COLUMNS
        if unknown:
            raise ValueError(f"Unknown block field(s): {sorted(unknown)}")
        if not kwargs:
            return True

        existing = self.get_block(block_id)
        if not existing:
            raise ValueError(f"Block {block_id} not found.")

        merged = {**existing, **kwargs}
        merged.pop("id", None)
        merged.pop("block_id", None)
        merged.pop("created_at", None)
        merged.pop("updated_at", None)
        fields = self._validate(merged, exclude_id=block_id)

        dup = self.get_block_by_name(fields["name"])
        if dup and dup["id"] != block_id:
            raise ValueError(f"A block with the name '{fields['name']}' already exists.")

        cols = [c for c in _WRITABLE_COLUMNS if c in fields]
        assigns = ", ".join(f"{c} = ?" for c in cols)
        params = [
            (1 if fields[c] else 0) if isinstance(fields[c], bool) else fields[c]
            for c in cols
        ]
        params.append(block_id)
        self.db.execute(
            f"UPDATE register_blocks SET {assigns},"
            f" updated_at = datetime('now','utc') WHERE id = ?",
            tuple(params),
        )
        return True

    def delete_block(self, block_id: int) -> bool:
        """
        Deletes a block. Audit rows referencing it keep their history
        (block_id is ON DELETE SET NULL).
        """
        self.db.execute("DELETE FROM register_blocks WHERE id = ?", (block_id,))
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_block(self, block_id: int) -> Optional[Dict[str, Any]]:
        """Returns a block by ID or None."""
        return self.db.fetchone(
            "SELECT * FROM register_blocks WHERE id = ?", (block_id,)
        )

    def get_block_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Returns a block by name or None."""
        return self.db.fetchone(
            "SELECT * FROM register_blocks WHERE name = ?", (name.strip(),)
        )

    def get_all_blocks(
        self,
        active_only: bool = False,
        group_name: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns blocks ordered by group_name, row_order.
        Optionally filtered by active flag and/or group.
        """
        clauses = []
        params = []
        if active_only:
            clauses.append("is_active = 1")
        if group_name is not None:
            clauses.append("group_name = ?")
            params.append(group_name)
        query = "SELECT * FROM register_blocks"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY group_name ASC, row_order ASC, id ASC"
        return self.db.fetchall(query, tuple(params))

    def get_poll_blocks(self) -> List[Dict[str, Any]]:
        """
        Returns all active blocks for the polling loop.
        Each row carries `block_id` (alias of id) for signal/data-model use.
        """
        return self.db.fetchall(
            "SELECT *, id AS block_id FROM register_blocks"
            " WHERE is_active = 1"
            " ORDER BY group_name ASC, row_order ASC, id ASC"
        )

    def get_groups(self) -> List[str]:
        """Returns unique non-empty group names, ordered."""
        rows = self.db.fetchall(
            "SELECT DISTINCT group_name FROM register_blocks ORDER BY group_name"
        )
        return [r["group_name"] for r in rows if r["group_name"]]
