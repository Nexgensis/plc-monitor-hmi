"""
Repository for model test parameters and settings.
Handles CRUD and complex validations for test parameter configurations.
"""
import logging
from typing import List, Dict, Any, Optional
from src.db.database import Database
from src.utils.validators import validate_register_address

logger = logging.getLogger(__name__)

class ParameterRepository:
    """Repository for managing parameters and model settings."""
    def __init__(self, db: Database):
        self.db = db

    def add_parameter(self, model_id: int, param_name: str, display_name: str,
                      module_name: str, param_order: int,
                      unit: str = "mV", scale_factor: float = 1.0,
                      enabled: bool = True, bypass: bool = False,
                      measured_register: int = 0, result_register: int = 0,
                      limit_min_register: int = 0, limit_max_register: int = 0,
                      limit_min_value: float = 0.0,
                      limit_max_value: float = 9999.0) -> int:
        
        if scale_factor <= 0:
            raise ValueError("Scale factor must be positive.")
        if limit_min_value >= limit_max_value:
            raise ValueError("limit_min_value must be less than limit_max_value.")

        existing_name = self.db.fetchone(
            "SELECT id FROM model_parameters WHERE model_id = ? AND param_name = ?", (model_id, param_name)
        )
        if existing_name:
            raise ValueError(f"Parameter name '{param_name}' already exists for this model.")

        existing_order = self.db.fetchone(
            "SELECT id FROM model_parameters WHERE model_id = ? AND param_order = ?", (model_id, param_order)
        )
        if existing_order:
            raise ValueError(f"Parameter order '{param_order}' is already used.")

        query = """
            INSERT INTO model_parameters (
                model_id, param_name, display_name, module_name, param_order,
                unit, scale_factor, enabled, bypass,
                measured_register, result_register, limit_min_register, limit_max_register,
                limit_min_value, limit_max_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.db.execute(query, (
            model_id, param_name, display_name, module_name, param_order,
            unit, scale_factor, 1 if enabled else 0, 1 if bypass else 0,
            measured_register, result_register, limit_min_register, limit_max_register,
            limit_min_value, limit_max_value
        ))
        return cursor.lastrowid

    def get_model_parameters(self, model_id: int, enabled_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM model_parameters WHERE model_id = ?"
        params = [model_id]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY param_order ASC"
        return self.db.fetchall(query, tuple(params))

    def get_enabled_parameters(self, model_id: int) -> List[Dict[str, Any]]:
        """Shortcut for get_model_parameters(enabled_only=True)."""
        return self.get_model_parameters(model_id, enabled_only=True)

    def get_parameters_by_module(self, model_id: int) -> Dict[str, List[Dict[str, Any]]]:
        params = self.get_model_parameters(model_id)
        modules = {}
        for p in params:
            m = p["module_name"]
            if m not in modules:
                modules[m] = []
            modules[m].append(p)
        return modules

    def update_parameter_info(self, param_id: int, **kwargs) -> bool:
        allowed = {
            "param_name", "display_name", "module_name", "param_order", "unit", "scale_factor", "enabled", "bypass"
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        
        if "scale_factor" in updates and updates["scale_factor"] <= 0:
            raise ValueError("Scale factor must be positive.")

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE model_parameters SET {set_clause} WHERE id = ?"
        params = list(updates.values()) + [param_id]
        
        self.db.execute(query, tuple(params))
        return True

    def update_parameter_registers(self, param_id: int, measured_register: Optional[int] = None,
                                   result_register: Optional[int] = None, limit_min_register: Optional[int] = None,
                                   limit_max_register: Optional[int] = None) -> bool:
        updates = {}
        if measured_register is not None:
            if not validate_register_address(measured_register): raise ValueError("Invalid measured_register")
            updates["measured_register"] = measured_register
        if result_register is not None:
            if not validate_register_address(result_register): raise ValueError("Invalid result_register")
            updates["result_register"] = result_register
        if limit_min_register is not None:
            if not validate_register_address(limit_min_register): raise ValueError("Invalid limit_min_register")
            updates["limit_min_register"] = limit_min_register
        if limit_max_register is not None:
            if not validate_register_address(limit_max_register): raise ValueError("Invalid limit_max_register")
            updates["limit_max_register"] = limit_max_register

        if not updates:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE model_parameters SET {set_clause} WHERE id = ?"
        params = list(updates.values()) + [param_id]
        
        self.db.execute(query, tuple(params))
        return True

    def update_parameter_limits(self, param_id: int, limit_min_value: float, limit_max_value: float) -> bool:
        if limit_min_value >= limit_max_value:
            raise ValueError("limit_min_value must be less than limit_max_value")
        self.db.execute("UPDATE model_parameters SET limit_min_value = ?, limit_max_value = ? WHERE id = ?",
                        (limit_min_value, limit_max_value, param_id))
        return True

    def delete_parameter(self, param_id: int) -> bool:
        row = self.db.fetchone("SELECT model_id FROM model_parameters WHERE id = ?", (param_id,))
        if not row:
            return False
            
        model_id = row["model_id"]
        self.db.execute("DELETE FROM model_parameters WHERE id = ?", (param_id,))
        
        # Renormalize param_order
        params = self.db.fetchall(
            "SELECT id FROM model_parameters WHERE model_id = ? ORDER BY param_order ASC", (model_id,)
        )
        update_data = [(i, p["id"], model_id) for i, p in enumerate(params)]
        self.db.executemany("UPDATE model_parameters SET param_order = ? WHERE id = ? AND model_id = ?", update_data)
        return True

    def update_parameter_order(self, model_id: int, ordered_ids: List[int]) -> None:
        update_data = [(i, pid, model_id) for i, pid in enumerate(ordered_ids)]
        self.db.executemany("UPDATE model_parameters SET param_order = ? WHERE id = ? AND model_id = ?", update_data)

    def replace_all_parameters(self, model_id: int, parameters: List[Dict[str, Any]]) -> None:
        """Explicit transaction block to replace all parameters."""
        conn = self.db.get_connection()
        try:
            conn.execute("BEGIN TRANSACTION")
            conn.execute("DELETE FROM model_parameters WHERE model_id = ?", (model_id,))
            
            insert_query = """
                INSERT INTO model_parameters (
                    model_id, param_name, display_name, module_name, param_order,
                    unit, scale_factor, enabled, bypass,
                    measured_register, result_register, limit_min_register, limit_max_register,
                    limit_min_value, limit_max_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            insert_data = []
            for p in parameters:
                insert_data.append((
                    model_id, p["param_name"], p["display_name"], p["module_name"], p["param_order"],
                    p.get("unit", "mV"), p.get("scale_factor", 1.0),
                    1 if p.get("enabled", True) else 0, 1 if p.get("bypass", False) else 0,
                    p.get("measured_register", 0), p.get("result_register", 0),
                    p.get("limit_min_register", 0), p.get("limit_max_register", 0),
                    p.get("limit_min_value", 0.0), p.get("limit_max_value", 9999.0)
                ))
            
            conn.executemany(insert_query, insert_data)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to replace parameters: {e}")
            raise

    def duplicate_model_parameters(self, source_id: int, target_id: int) -> int:
        params = self.get_model_parameters(source_id)
        if not params:
            return 0
        
        insert_query = """
            INSERT INTO model_parameters (
                model_id, param_name, display_name, module_name, param_order,
                unit, scale_factor, enabled, bypass,
                measured_register, result_register, limit_min_register, limit_max_register,
                limit_min_value, limit_max_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        insert_data = []
        for p in params:
            insert_data.append((
                target_id, p["param_name"], p["display_name"], p["module_name"], p["param_order"],
                p["unit"], p["scale_factor"], p["enabled"], p["bypass"],
                p["measured_register"], p["result_register"],
                p["limit_min_register"], p["limit_max_register"],
                p["limit_min_value"], p["limit_max_value"]
            ))
        
        self.db.executemany(insert_query, insert_data)
        return len(insert_data)

    def get_parameters_for_plc_push(self, model_id: int) -> List[Dict[str, Any]]:
        query = (
            "SELECT * FROM model_parameters WHERE model_id = ? AND enabled = 1 AND limit_min_register > 0 "
            "ORDER BY param_order ASC"
        )
        return self.db.fetchall(query, (model_id,))

    def get_parameters_for_polling(self, model_id: int) -> List[Dict[str, Any]]:
        query = (
            "SELECT * FROM model_parameters WHERE model_id = ? AND enabled = 1 AND measured_register > 0 "
            "ORDER BY param_order ASC"
        )
        return self.db.fetchall(query, (model_id,))

    def validate_model_parameters(self, model_id: int) -> List[str]:
        warnings = []
        params = self.get_model_parameters(model_id)
        
        if not params:
            warnings.append("Model has no parameters.")
            return warnings
            
        used_registers = set()
        
        for p in params:
            name = p["param_name"]
            if p["enabled"] and p["measured_register"] <= 0:
                warnings.append(f"Parameter '{name}' is enabled but has no measured register.")
            
            if p["limit_min_value"] >= p["limit_max_value"]:
                warnings.append(f"Parameter '{name}' has invalid limit range.")
                
            regs = [r for r in [p["measured_register"], p["result_register"],
                                p["limit_min_register"], p["limit_max_register"]] if r > 0]
            for r in regs:
                if r in used_registers:
                    warnings.append(f"Register address conflict detected: {r} is used multiple times.")
                used_registers.add(r)
                
        return warnings

    # --- model_settings ---

    def get_model_settings(self, model_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetchone("SELECT * FROM model_settings WHERE model_id = ?", (model_id,))

    def create_model_settings(self, model_id: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO model_settings (model_id) VALUES (?)", (model_id,))

    def update_model_settings(self, model_id: int, **kwargs) -> bool:
        allowed = {"batch_set_value", "coupler_set_value"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
            
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE model_settings SET {set_clause} WHERE model_id = ?"
        params = list(updates.values()) + [model_id]
        
        self.db.execute(query, tuple(params))
        return True
