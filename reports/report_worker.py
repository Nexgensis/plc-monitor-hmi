"""
reports/report_worker.py
Threaded task dispatcher isolating huge synchronous IO dumps from Main Application visually.
"""

import logging
import traceback
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ReportWorker(QThread):
    """
    QThread mechanism executing specific abstract payloads mapping safely mechanically asynchronously.
    """
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)   
    error    = pyqtSignal(str)

    def __init__(self, report_type: str, exporter, output_path: str, **kwargs):
        super().__init__()
        self.report_type = report_type
        self.exporter = exporter
        self.output_path = output_path
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            self.progress.emit(10, "Fetching database constraints structurally explicitly...")
            result = None
            
            if self.report_type == "excel_shift":
                result = self.exporter.generate_shift_report(self.output_path, **self.kwargs)
                
            elif self.report_type == "excel_session":
                result = self.exporter.generate_session_report(self.output_path, **self.kwargs)
                
            elif self.report_type == "pdf_certificate":
                result = self.exporter.generate_test_certificate(self.output_path, **self.kwargs)
                
            elif self.report_type == "pdf_shift":
                result = self.exporter.generate_shift_summary_pdf(self.output_path, **self.kwargs)
                
            else:
                self.error.emit(f"Unknown report mapping identity explicitly inherently bounded natively: {self.report_type}")
                return
                
            self.progress.emit(90, "Saving bounded structural output metrics synchronously structurally natively...")
            
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("Unknown persistence fallback explicitly mapped negatively natively")
                
        except Exception as e:
            err_trace = traceback.format_exc()
            logger.error(f"ReportWorker threaded fault structurally dynamically inherently mapping natively constraints explicitly:\n{err_trace}")
            self.error.emit(str(e))
