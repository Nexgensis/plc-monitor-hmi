"""
pass_fail_evaluator.py — Universal PLC Monitor
Business logic for determining PASS/FAIL status based on real-time PLC readings.
Pure Python, no Qt dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set, Any, Optional

from src.plc.data_model import RegisterReading
from src.utils.constants import (
    ROLE_RESULT,
    RESULT_PASS, RESULT_FAIL, RESULT_BYPASS, 
    RESULT_PENDING, RESULT_RUNNING
)

@dataclass
class EvalResult:
    """Standardized evaluation result for a single dashboard card."""
    register_id: int
    mapping_id: int
    display_name: str
    group_name: str
    measured_value: float
    display_str: str
    result: str           # PASS, FAIL, BYPASS, PENDING, or RUNNING
    pass_value: int
    fail_value: int
    timestamp: datetime


class PassFailEvaluator:
    """
    Evaluates real-time register readings against model-specific rules.
    Used by TestPage to drive the visual state of dashboard cards.
    """

    def __init__(self, dashboard_registers: List[Dict[str, Any]]) -> None:
        """
        Args:
            dashboard_registers: List of dicts from ModelMapRepo.get_dashboard_registers()
        """
        self._configs: Dict[int, Dict[str, Any]] = {}
        self._result_reg_ids: Set[int] = set()
        self.update_from_model(dashboard_registers)

    def update_from_model(self, dashboard_registers: List[Dict[str, Any]]) -> None:
        """Refresh configuration when model changes."""
        self._configs.clear()
        self._result_reg_ids.clear()
        for reg in dashboard_registers:
            self._configs[reg["register_id"]] = reg
            if reg.get("role") == ROLE_RESULT:
                self._result_reg_ids.add(reg["register_id"])

    def evaluate_all(
        self, 
        readings: Dict[int, RegisterReading],
        is_running: bool = False
    ) -> List[EvalResult]:
        """
        Performs evaluation of all dashboard registers.
        
        Args:
            readings:   {register_id: RegisterReading}
            is_running: True if a test cycle is currently active.
            
        Returns:
            Sorted list of EvalResult objects based on card_position.
        """
        results = []
        
        for reg_id, cfg in self._configs.items():
            reading = readings.get(reg_id)
            
            # 1. Base details
            display_name = cfg.get("display_name") or cfg.get("name", "Unknown")
            group_name   = cfg.get("group_name", "")
            pass_val     = cfg.get("pass_value", 1)
            fail_val     = cfg.get("fail_value", 2)
            
            if not reading:
                # No data yet
                results.append(EvalResult(
                    register_id    = reg_id,
                    mapping_id     = cfg.get("id", 0),
                    display_name   = display_name,
                    group_name     = group_name,
                    measured_value = 0.0,
                    display_str    = "---",
                    result         = RESULT_PENDING,
                    pass_value     = pass_val,
                    fail_value     = fail_val,
                    timestamp      = datetime.now(timezone.utc)
                ))
                continue

            # 2. Logic Determination
            if cfg.get("bypass", False):
                result_str = RESULT_BYPASS
            elif is_running:
                result_str = RESULT_RUNNING
            elif cfg.get("role") == ROLE_RESULT:
                # For RESULT roles, we look at the raw PLC value
                raw = reading.raw_words[0] if reading.raw_words else 0
                if raw == pass_val:
                    result_str = RESULT_PASS
                elif raw == fail_val:
                    result_str = RESULT_FAIL
                else:
                    result_str = RESULT_PENDING
            else:
                # MEASURED roles don't have autonomous PASS/FAIL usually
                # they follow the overall cycle or a linked RESULT register.
                # Here we default to PENDING (neutral) when not running.
                result_str = RESULT_PENDING

            results.append(EvalResult(
                register_id    = reg_id,
                mapping_id     = cfg.get("id", 0),
                display_name   = display_name,
                group_name     = group_name,
                measured_value = reading.display_value,
                display_str    = reading.display_str,
                result         = result_str,
                pass_value     = pass_val,
                fail_value     = fail_val,
                timestamp      = reading.timestamp
            ))
            
        # 3. Final sorting by user-defined position
        return sorted(
            results, 
            key=lambda r: self._configs[r.register_id].get("card_position", 0)
        )
