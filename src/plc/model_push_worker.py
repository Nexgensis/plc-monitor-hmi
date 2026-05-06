"""
Background worker for pushing model configuration and parameters to the PLC.
"""
import logging
from typing import Dict, List, Any
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

class ModelPushWorker(QThread):
    """
    Short-lived background thread for writing model settings and parameter limits to PLC.
    """
    push_started = pyqtSignal(str)         # model_name
    push_progress = pyqtSignal(int, str)    # percent, message
    push_success = pyqtSignal(str)          # model_name
    push_failed = pyqtSignal(str, str)      # name, error

    def __init__(self, model: Dict[str, Any], parameters: List[Dict[str, Any]], 
                 write_manager: Any, operator_id: int):
        super().__init__()
        self._model = model
        self._parameters = parameters
        self._write_manager = write_manager
        self._operator_id = operator_id

    def run(self):
        try:
            name = self._model.get("name", "Unknown")
            self.push_started.emit(name)

            # Step 1: Write parameter limits (min/max/scale)
            self.push_progress.emit(20, "Writing limits...")
            limit_results = self._write_manager.write_model_limits(
                self._parameters,
                self._model["id"],
                self._operator_id
            )

            # Step 2: Write model metadata block (name, ID, etc.)
            self.push_progress.emit(60, "Writing model block...")
            block_result = self._write_manager.write_model_block(
                self._model, self._operator_id
            )

            # Step 3: Verification
            self.push_progress.emit(90, "Verifying...")
            
            # Check if any limit write failed
            any_failed = any(not r.success for r in limit_results.values())
            
            if any_failed or not block_result.success:
                self.push_failed.emit(name, "Register write/verify failed")
                return

            self.push_progress.emit(100, "Done")
            self.push_success.emit(name)

        except Exception as e:
            import traceback
            log.error(f"Error in ModelPushWorker: {traceback.format_exc()}")
            self.push_failed.emit(self._model.get("name", "?"), str(e))
