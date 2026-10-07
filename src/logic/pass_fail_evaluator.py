"""
pass_fail_evaluator.py — Universal PLC Monitor
Business logic for determining PASS/FAIL status based on real-time PLC readings.
Pure Python, no Qt dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set, Any

from src.plc.data_model import RegisterReading
from src.utils.constants import (
    ROLE_RESULT,
    ROLE_LIMIT_MIN, ROLE_LIMIT_MAX,
    RESULT_PASS, RESULT_FAIL, RESULT_BYPASS, 
    RESULT_PENDING, RESULT_RUNNING, RESULT_NA
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
    raw_value: int = 0
    limit_min: float = 0.0
    limit_max: float = 0.0


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

    def _extract_limits(self, readings) -> tuple[float, float]:
        """
        Reads the LIMIT_MIN and LIMIT_MAX register readings for the current model,
        if present in the active poll. Falls back to 0.0 otherwise.
        """
        limit_min = 0.0
        limit_max = 0.0
        for reg_id, cfg in self._configs.items():
            rd = readings.get(reg_id)
            if rd is None or not getattr(rd, "read_success", True):
                continue
            if cfg.get("role") == ROLE_LIMIT_MIN:
                limit_min = rd.display_value
            elif cfg.get("role") == ROLE_LIMIT_MAX:
                limit_max = rd.display_value
        return limit_min, limit_max

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
        limit_min, limit_max = self._extract_limits(readings)
        
        for reg_id, cfg in self._configs.items():
            reading = readings.get(reg_id)
            
            # 1. Base details
            display_name = cfg.get("display_name") or cfg.get("name", "Unknown")
            group_name   = cfg.get("group_name", "")
            pass_val     = cfg.get("pass_value", 1)
            fail_val     = cfg.get("fail_value", 2)

            # Per-parameter spec limits, falling back to model-wide limit
            # registers when no per-parameter thresholds are configured.
            p_min = cfg.get("limit_min", 0.0)
            p_max = cfg.get("limit_max", 0.0)
            if p_min == 0.0 and p_max == 0.0:
                p_min, p_max = limit_min, limit_max
            
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
                    timestamp      = datetime.now(timezone.utc),
                    raw_value      = 0,
                    limit_min      = p_min,
                    limit_max      = p_max
                ))
                continue

            # If the read failed, treat as pending (stale/garbage data)
            if not getattr(reading, 'read_success', True):
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
                    timestamp      = reading.timestamp,
                    raw_value      = 0,
                    limit_min      = p_min,
                    limit_max      = p_max
                ))
                continue

            # 2. Logic Determination
            raw_val = reading.raw_words[0] if reading.raw_words else 0
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
                # MEASURED / STATUS / COUNTER roles are judged against their
                # configured spec limits. No thresholds configured = informative
                # telemetry only (N/A).
                if p_min == 0.0 and p_max == 0.0:
                    result_str = RESULT_NA
                else:
                    val = reading.display_value
                    if p_min <= val <= p_max:
                        result_str = RESULT_PASS
                    else:
                        result_str = RESULT_FAIL

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
                timestamp      = reading.timestamp,
                raw_value      = raw_val,
                limit_min      = p_min,
                limit_max      = p_max
            ))
            
        # 3. Final sorting by user-defined position
        return sorted(
            results, 
            key=lambda r: self._configs[r.register_id].get("card_position", 0)
        )

    def get_overall_result(self, results: List[EvalResult]) -> str:
        """Determine overall PASS/FAIL from a list of EvalResults."""
        active = [r for r in results if r.result not in (RESULT_BYPASS, RESULT_PENDING, RESULT_RUNNING, RESULT_NA)]
        if not active:
            return RESULT_PENDING
        if any(r.result == RESULT_FAIL for r in active):
            return RESULT_FAIL
        if all(r.result == RESULT_PASS for r in active):
            return RESULT_PASS
        return RESULT_PENDING

    def get_module_results(self, results: List[EvalResult]) -> Dict[str, str]:
        """Group results by module and determine per-module PASS/FAIL."""
        modules: Dict[str, List[EvalResult]] = {}
        for r in results:
            grp = r.group_name or "General"
            modules.setdefault(grp, []).append(r)

        module_outcomes = {}
        for grp, res_list in modules.items():
            active = [r for r in res_list if r.result not in (RESULT_BYPASS, RESULT_PENDING, RESULT_RUNNING, RESULT_NA)]
            if not active:
                module_outcomes[grp] = RESULT_PENDING
            elif any(r.result == RESULT_FAIL for r in active):
                module_outcomes[grp] = RESULT_FAIL
            elif all(r.result == RESULT_PASS for r in active):
                module_outcomes[grp] = RESULT_PASS
            else:
                module_outcomes[grp] = RESULT_PENDING
        return module_outcomes
