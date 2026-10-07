"""
test_pass_fail_evaluator.py — Tests for per-parameter min/max limit evaluation.
"""
import sys
import os
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.logic.pass_fail_evaluator import PassFailEvaluator, EvalResult
from src.plc.data_model import RegisterReading
from src.utils.constants import (
    RESULT_PASS, RESULT_FAIL, RESULT_NA, RESULT_PENDING, RESULT_RUNNING, RESULT_BYPASS,
)


def _reading(reg_id, value, raw=0, ok=True):
    return RegisterReading(
        register_id=reg_id,
        name=f"reg{reg_id}",
        plc_address=reg_id,
        register_type="HOLDING",
        raw_words=[raw],
        display_value=value,
        display_str=f"{value:.2f}",
        unit="A",
        data_type="UINT16",
        timestamp=datetime.now(timezone.utc),
        read_success=ok,
    )


def _cfg(reg_id, role="MEASURED", limit_min=0.0, limit_max=0.0, card_position=0,
         pass_value=1, fail_value=2, bypass=False):
    return {
        "id": reg_id,
        "register_id": reg_id,
        "role": role,
        "display_name": f"Param {reg_id}",
        "group_name": "G1",
        "limit_min": limit_min,
        "limit_max": limit_max,
        "card_position": card_position,
        "pass_value": pass_value,
        "fail_value": fail_value,
        "bypass": bypass,
    }


class TestMeasuredBounds:
    def test_pass_within_limits(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 3.0)})
        assert results[0].result == RESULT_PASS
        assert results[0].limit_min == 1.0
        assert results[0].limit_max == 5.0

    def test_fail_below_min(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 0.5)})
        assert results[0].result == RESULT_FAIL

    def test_fail_above_max(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 6.0)})
        assert results[0].result == RESULT_FAIL

    def test_na_when_no_limits(self):
        ev = PassFailEvaluator([_cfg(1)])
        results = ev.evaluate_all({1: _reading(1, 3.0)})
        assert results[0].result == RESULT_NA
        assert results[0].limit_min == 0.0
        assert results[0].limit_max == 0.0

    def test_running_supersedes_limits(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 3.0)}, is_running=True)
        assert results[0].result == RESULT_RUNNING

    def test_bypass_overrides_limits(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0, bypass=True)])
        results = ev.evaluate_all({1: _reading(1, 6.0)})
        assert results[0].result == RESULT_BYPASS

    def test_result_role_uses_raw_values(self):
        ev = PassFailEvaluator([_cfg(2, role="RESULT", pass_value=1, fail_value=2)])
        results = ev.evaluate_all({2: _reading(2, 1.0, raw=1)})
        assert results[0].result == RESULT_PASS

    def test_no_reading_is_pending(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({})
        assert results[0].result == RESULT_PENDING


class TestOverallResult:
    def test_overall_pass_when_all_pass(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0),
                                _cfg(2, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 2.0), 2: _reading(2, 4.0)})
        assert ev.get_overall_result(results) == RESULT_PASS

    def test_overall_fail_when_any_fail(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0),
                                _cfg(2, limit_min=1.0, limit_max=5.0)])
        results = ev.evaluate_all({1: _reading(1, 2.0), 2: _reading(2, 9.0)})
        assert ev.get_overall_result(results) == RESULT_FAIL

    def test_na_ignored_in_overall(self):
        # Two params: one real PASS, one N/A telemetry -> overall PASS
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0),
                                _cfg(2)])
        results = ev.evaluate_all({1: _reading(1, 2.0), 2: _reading(2, 3.0)})
        assert any(r.result == RESULT_NA for r in results)
        assert ev.get_overall_result(results) == RESULT_PASS

    def test_all_na_is_pending(self):
        ev = PassFailEvaluator([_cfg(1), _cfg(2)])
        results = ev.evaluate_all({1: _reading(1, 2.0), 2: _reading(2, 3.0)})
        assert ev.get_overall_result(results) == RESULT_PENDING

    def test_module_results_excludes_na(self):
        ev = PassFailEvaluator([_cfg(1, limit_min=1.0, limit_max=5.0),
                                _cfg(2)])
        results = ev.evaluate_all({1: _reading(1, 2.0), 2: _reading(2, 3.0)})
        mod = ev.get_module_results(results)
        assert mod["G1"] == RESULT_PASS
