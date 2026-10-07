"""
Controller managing test session lifecycle, DB recording, and stats tracking.
"""
import logging
from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.constants import (
    RESULT_PASS, RESULT_FAIL, RESULT_BYPASS, RESULT_PENDING,
    MACHINE_STATE_PASS, MACHINE_STATE_FAIL, MACHINE_STATE_BYPASS,
)

logger = logging.getLogger(__name__)

class SessionController(QObject):
    test_started = pyqtSignal(int)          # session_id
    test_completed = pyqtSignal(dict)       # summary dict
    results_ready = pyqtSignal(list)        # list[EvaluationResult]
    overall_result = pyqtSignal(str)        # PASS|FAIL
    module_results = pyqtSignal(dict)       # {module: result}
    counts_updated = pyqtSignal(int, int, int) # ok, ng, batch
    error_occurred = pyqtSignal(str)

    def __init__(self, app_state, evaluator):
        super().__init__()
        self._app_state = app_state
        self._evaluator = evaluator
        self._session_id = None
        self._ok_count = 0
        self._ng_count = 0
        self._batch_count = 0
        self._last_results = []
        self._last_readings: dict = {}

    @property
    def active_session_id(self):
        return self._session_id

    def on_test_started(self) -> None:
        try:
            model_id = self._app_state.current_model_id
            user_id = self._app_state.current_user["id"] if self._app_state.current_user else None
            
            if not model_id or not user_id:
                self.error_occurred.emit("Cannot start test: Model or User not set.")
                return

            self._session_id = self._app_state.session_repo.open_session(model_id, user_id)
            self._last_results = []
            logger.info(f"Test session started: ID {self._session_id}")
            self.test_started.emit(self._session_id)
        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            self.error_occurred.emit(f"Failed to start session: {e}")

    def on_readings_update(self, readings: dict) -> None:
        if not self._session_id:
            return
            
        try:
            self._last_readings = readings
            results = self._evaluator.evaluate_all(readings, is_running=True)
            self._last_results = results
            self.results_ready.emit(results)
            self.module_results.emit(self._evaluator.get_module_results(results))
        except Exception as e:
            logger.error(f"Error evaluating readings: {e}")

    def on_test_completed(self, plc_status) -> None:
        if not self._session_id:
            return
            
        try:
            # Re-evaluate the final readings WITHOUT the running flag so the
            # RESULT registers produce real PASS/FAIL instead of RUNNING.
            final_readings = getattr(self, "_last_readings", {}) or {}
            results = self._evaluator.evaluate_all(final_readings, is_running=False)
            self._last_results = results

            # Determine overall result
            overall = self._evaluator.get_overall_result(results)

            # Fall back to the PLC machine state register if the evaluation
            # was inconclusive (e.g. no RESULT-role registers configured).
            if overall in (None, "PENDING"):
                state = plc_status if isinstance(plc_status, int) else None
                if state == MACHINE_STATE_PASS:
                    overall = RESULT_PASS
                elif state == MACHINE_STATE_FAIL:
                    overall = RESULT_FAIL
                elif state == MACHINE_STATE_BYPASS:
                    overall = RESULT_BYPASS

            # Write results to DB (map invalid UI states to a DB-valid value)
            for r in results:
                db_result = r.result
                if db_result not in ("PASS", "FAIL", "BYPASS", "PENDING"):
                    db_result = "PENDING"
                self._app_state.session_repo.record_result(
                    session_id=self._session_id,
                    parameter_id=r.register_id,
                    param_name=r.display_name,
                    module_name=r.group_name,
                    measured_value=r.measured_value,
                    limit_min=getattr(r, "limit_min", 0.0),
                    limit_max=getattr(r, "limit_max", 0.0),
                    result=db_result,
                    raw_value=r.raw_value
                )
            
            # Close session and update cumulative counters
            if overall == RESULT_PASS:
                self._ok_count += 1
                curr_ok, curr_ng = 1, 0
                db_overall = "PASS"
            elif overall == RESULT_FAIL:
                self._ng_count += 1
                curr_ok, curr_ng = 0, 1
                db_overall = "FAIL"
            else:
                # BYPASS/PENDING are not stored as PASS/FAIL (schema constraint)
                curr_ok, curr_ng = 0, 0
                db_overall = "PENDING"
                overall = RESULT_PENDING
                
            self._batch_count += 1
            
            self._app_state.session_repo.close_session(
                session_id=self._session_id,
                ok_count=curr_ok,
                ng_count=curr_ng,
                batch_count=1,
                overall_result=db_overall
            )
            
            logger.info(f"Test session {self._session_id} completed: {overall}")
            
            # Reset active session
            closed_session_id = self._session_id
            self._session_id = None
            
            # Fetch summary
            summary = self._app_state.report_repo.get_sessions_summary(session_id=closed_session_id)
            summary_dict = summary[0] if summary else {}
            
            # Emit signals
            self.overall_result.emit(overall)
            self.counts_updated.emit(self._ok_count, self._ng_count, self._batch_count)
            self.test_completed.emit(summary_dict)
            
        except Exception as e:
            logger.error(f"Error completing test session: {e}")
            self.error_occurred.emit(f"Failed to complete session: {e}")
            # Attempt to close the session in DB to avoid orphaned PENDING sessions
            if self._session_id:
                try:
                    self._app_state.session_repo.close_session(
                        session_id=self._session_id,
                        ok_count=0, ng_count=1, batch_count=1,
                        overall_result="FAIL"
                    )
                except Exception as close_err:
                    logger.error(f"Failed to close orphaned session {self._session_id}: {close_err}")
            self._session_id = None

    def on_reset_requested(self) -> None:
        self._ok_count = 0
        self._ng_count = 0
        self._batch_count = 0
        self.counts_updated.emit(0, 0, 0)
        logger.info("Test counters reset.")

    def update_evaluator(self, model_config: dict) -> None:
        self._evaluator.update_from_model(model_config)
