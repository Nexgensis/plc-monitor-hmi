"""
Controller managing test session lifecycle, DB recording, and stats tracking.
"""
import logging
from PyQt6.QtCore import QObject, pyqtSignal

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
            results = self._evaluator.evaluate_all(readings)
            self._last_results = results
            self.results_ready.emit(results)
            self.module_results.emit(self._evaluator.get_module_results(results))
        except Exception as e:
            logger.error(f"Error evaluating readings: {e}")

    def on_test_completed(self, plc_status) -> None:
        if not self._session_id:
            return
            
        try:
            # Determine overall result
            overall = self._evaluator.get_overall_result(self._last_results)
            
            # Write results to DB
            for r in self._last_results:
                self._app_state.session_repo.record_result(
                    session_id=self._session_id,
                    parameter_id=r.parameter_id,
                    param_name=r.param_name,
                    module_name=r.module_name,
                    measured_value=r.measured_value,
                    limit_min=r.limit_min,
                    limit_max=r.limit_max,
                    result=r.result,
                    deviation_pct=r.deviation_pct
                )
            
            # Close session
            # We need ok_count and ng_count from evaluator or current logic
            # For simplicity in this controller, we track them
            if overall == "PASS":
                self._ok_count += 1
                curr_ok = 1
                curr_ng = 0
            else:
                self._ng_count += 1
                curr_ok = 0
                curr_ng = 1
                
            self._batch_count += 1
            
            self._app_state.session_repo.close_session(
                session_id=self._session_id,
                ok_count=curr_ok, # This is per session? Or total? 
                # SessionRepo.close_session sets ok_count/ng_count for THIS session row.
                ng_count=curr_ng,
                batch_count=1,
                notes=""
            )
            
            # Update counts
            self._batch_count += 1
            if overall == "PASS":
                self._ok_count += 1
            elif overall == "FAIL":
                self._ng_count += 1
                
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
            self._session_id = None

    def on_reset_requested(self) -> None:
        self._ok_count = 0
        self._ng_count = 0
        self._batch_count = 0
        self.counts_updated.emit(0, 0, 0)
        logger.info("Test counters reset.")

    def update_evaluator(self, model_config: dict) -> None:
        self._evaluator.update_config(model_config)
