"""
Background worker thread for report generation.
"""
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class ReportWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, report_type, exporter, output_path, **kwargs):
        super().__init__()
        self._report_type = report_type
        self._exporter = exporter
        self._output_path = output_path
        self._kwargs = kwargs

    def run(self):
        try:
            self.progress.emit(10, "Fetching data...")
            methods = {
                "excel_session": self._exporter.generate_session_report,
                "excel_shift":   self._exporter.generate_shift_report,
                "pdf_cert":      self._exporter.generate_test_certificate,
                "pdf_shift":     self._exporter.generate_shift_summary_pdf,
            }
            fn = methods.get(self._report_type)
            if not fn:
                raise ValueError(f"Unknown report type: {self._report_type}")
                
            self.msleep(300)
            self.progress.emit(40, "Generating document...")
            
            # Extract specific args based on method signature
            if self._report_type in ["excel_session", "pdf_cert"]:
                result = fn(self._output_path, self._kwargs.get("session_id"))
            else:
                result = fn(self._output_path, 
                            model_id=self._kwargs.get("model_id"),
                            date_from=self._kwargs.get("date_from"),
                            date_to=self._kwargs.get("date_to"))
                            
            self.progress.emit(100, "Complete")
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Report generation failed")
            self.error.emit(str(e))
