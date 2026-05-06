"""
ui/dialogs/reports_dialog.py
Main reports interface for searching, previewing, and exporting test data.
"""

import os
import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QSplitter, QProgressBar, QAbstractItemView, QHeaderView,
    QFileDialog, QMessageBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt, QDate, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from src.ui.app_state import AppState
from src.reports.excel_exporter import ExcelExporter
from src.reports.pdf_exporter import PDFExporter
from src.reports.report_worker import ReportWorker

log = logging.getLogger(__name__)

class ReportsDialog(QDialog):
    """
    Dialog for reviewing historical test sessions and generating reports (Excel/PDF).
    """
    
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._state = app_state
        self._excel_exp = ExcelExporter(app_state.report_repo)
        self._pdf_exp = PDFExporter(app_state.report_repo)
        self._current_session_id = None
        self._worker: ReportWorker | None = None
        
        self.setWindowTitle("Historical Reports & Data Export")
        self.resize(1060, 700)
        
        self._setup_ui()
        self._populate_models()
        self._on_search()  # Initial search

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. FILTER BAR
        filter_bar = QFrame()
        filter_bar.setObjectName("card")
        filter_bar.setStyleSheet("QFrame#card { background-color: #f8f9fc; border: 1px solid #d0d8e8; border-radius: 4px; }")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        
        filter_layout.addWidget(QLabel("Model:"))
        self.model_filter = QComboBox()
        self.model_filter.setMinimumWidth(180)
        filter_layout.addWidget(self.model_filter)
        
        filter_layout.addWidget(QLabel("  From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        filter_layout.addWidget(self.date_from)
        
        filter_layout.addWidget(QLabel("  To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)
        
        self.btn_search = QPushButton("Search")
        self.btn_search.setStyleSheet("background: #1e2d4a; color: white; font-weight: bold; padding: 5px 15px;")
        self.btn_search.clicked.connect(self._on_search)
        filter_layout.addWidget(self.btn_search)
        
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet("padding: 5px 15px;")
        self.btn_clear.clicked.connect(self._on_clear_filters)
        filter_layout.addWidget(self.btn_clear)
        
        filter_layout.addStretch()
        
        self.result_count_lbl = QLabel("0 sessions")
        self.result_count_lbl.setStyleSheet("color: #6c757d; font-weight: bold;")
        filter_layout.addWidget(self.result_count_lbl)
        
        main_layout.addWidget(filter_bar)

        # 2. MAIN AREA (Splitter)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT: Sessions Table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(10)
        self.sessions_table.setHorizontalHeaderLabels([
            "#", "Date", "Time", "Model", "Operator", 
            "OK", "NG", "Batch", "Pass%", "Duration"
        ])
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sessions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sessions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sessions_table.verticalHeader().setVisible(False)
        self.sessions_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.sessions_table.itemDoubleClicked.connect(self._on_session_double_clicked)
        
        h_head = self.sessions_table.horizontalHeader()
        h_head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_head.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) # Model col
        
        self.splitter.addWidget(self.sessions_table)
        
        # RIGHT: Detail Panel
        self.detail_panel = QFrame()
        self.detail_panel.setStyleSheet("background-color: white; border: 1px solid #d0d8e8; border-radius: 4px;")
        self.detail_layout = QVBoxLayout(self.detail_panel)
        
        self.placeholder_lbl = QLabel("Select a session to view")
        self.placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_lbl.setStyleSheet("color: #6c757d; font-style: italic;")
        self.detail_layout.addWidget(self.placeholder_lbl)
        
        # Wrapped detail content
        self.detail_content = QWidget()
        self.dc_layout = QVBoxLayout(self.detail_content)
        self.dc_layout.setContentsMargins(10, 10, 10, 10)
        
        self.session_title = QLabel()
        self.session_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1e2d4a;")
        self.dc_layout.addWidget(self.session_title)
        
        self.overall_result_badge = QLabel()
        self.overall_result_badge.setMinimumHeight(40)
        self.overall_result_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_result_badge.setStyleSheet("font-size: 18px; font-weight: bold; color: white; border-radius: 4px;")
        self.dc_layout.addWidget(self.overall_result_badge)
        
        self.results_preview = QTableWidget()
        self.results_preview.setColumnCount(5)
        self.results_preview.setHorizontalHeaderLabels(["Param", "Result", "Measured", "Min", "Max"])
        self.results_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_preview.verticalHeader().setVisible(False)
        self.results_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.results_preview.setMaximumHeight(250)
        self.dc_layout.addWidget(self.results_preview)
        
        self.alarm_lbl = QLabel()
        self.alarm_lbl.setStyleSheet("color: #d4890a; font-weight: bold;")
        self.alarm_lbl.hide()
        self.dc_layout.addWidget(self.alarm_lbl)
        
        self.detail_layout.addWidget(self.detail_content)
        self.detail_content.hide()
        
        self.splitter.addWidget(self.detail_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.splitter, stretch=1)

        # 3. PROGRESS AREA
        self.progress_area = QWidget()
        pa_layout = QVBoxLayout(self.progress_area)
        pa_layout.setContentsMargins(0, 0, 0, 0)
        
        self.progress_lbl = QLabel("Generating...")
        self.progress_lbl.setStyleSheet("font-size: 11px;")
        pa_layout.addWidget(self.progress_lbl)
        
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        pa_layout.addWidget(self.export_progress)
        
        main_layout.addWidget(self.progress_area)
        self.progress_area.hide()

        # 4. EXPORT BAR
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #d0d8e8; max-height: 1px;")
        main_layout.addWidget(divider)
        
        export_bar = QHBoxLayout()
        self.selected_lbl = QLabel("No session selected")
        self.selected_lbl.setStyleSheet("color: #6c757d;")
        export_bar.addWidget(self.selected_lbl)
        
        export_bar.addStretch()
        
        self.btn_ex_sess = QPushButton("Excel — Session")
        self.btn_ex_sess.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_ex_sess.clicked.connect(self._on_export_excel_session)
        export_bar.addWidget(self.btn_ex_sess)
        
        self.btn_ex_shift = QPushButton("Excel — Shift")
        self.btn_ex_shift.setStyleSheet("background: #27ae60; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_ex_shift.clicked.connect(self._on_export_excel_shift)
        export_bar.addWidget(self.btn_ex_shift)
        
        self.btn_pdf = QPushButton("PDF Certificate")
        self.btn_pdf.setStyleSheet("background: #c0392b; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_pdf.clicked.connect(self._on_export_pdf)
        export_bar.addWidget(self.btn_pdf)
        
        self.btn_open_folder = QPushButton("Open Reports Folder")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        export_bar.addWidget(self.btn_open_folder)
        
        # Initial state
        self.btn_ex_sess.setEnabled(False)
        self.btn_pdf.setEnabled(False)
        
        main_layout.addLayout(export_bar)

    def _populate_models(self) -> None:
        self.model_filter.addItem("All Models", None)
        models = self._state.model_repo.get_all_models()
        for m in models:
            self.model_filter.addItem(m["name"], m["id"])

    def _on_clear_filters(self) -> None:
        self.model_filter.setCurrentIndex(0)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_to.setDate(QDate.currentDate())
        self._on_search()

    def _on_search(self) -> None:
        model_id = self.model_filter.currentData()
        df = self.date_from.date().toString("yyyy-MM-dd")
        dt = self.date_to.date().toString("yyyy-MM-dd")
        
        sessions = self._state.report_repo.get_sessions_summary(
            model_id=model_id,
            date_from=df,
            date_to=dt
        )
        
        self._populate_sessions_table(sessions)
        self.result_count_lbl.setText(f"{len(sessions)} session(s)")

    def _populate_sessions_table(self, sessions: list[dict]) -> None:
        self.sessions_table.setRowCount(0)
        for i, s in enumerate(sessions):
            self.sessions_table.insertRow(i)
            
            # # col
            it_id = QTableWidgetItem(str(s["session_id"]))
            it_id.setData(Qt.ItemDataRole.UserRole, s["session_id"])
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sessions_table.setItem(i, 0, it_id)
            
            # Date / Time
            dt = s["started_at"]
            self.sessions_table.setItem(i, 1, QTableWidgetItem(dt[:10]))
            self.sessions_table.setItem(i, 2, QTableWidgetItem(dt[11:19]))
            
            # Model / Operator
            self.sessions_table.setItem(i, 3, QTableWidgetItem(s["model_name"] or "-"))
            self.sessions_table.setItem(i, 4, QTableWidgetItem(s["operator_username"] or "-"))
            
            # Counts
            self.sessions_table.setItem(i, 5, QTableWidgetItem(str(s["ok_count"])))
            self.sessions_table.setItem(i, 6, QTableWidgetItem(str(s["ng_count"])))
            self.sessions_table.setItem(i, 7, QTableWidgetItem(str(s["batch_count"])))
            
            # Pass%
            rate = s["pass_rate_pct"]
            it_rate = QTableWidgetItem(f"{rate:.1f}%")
            it_rate.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rate >= 95: it_rate.setForeground(QColor("#1a6b3a"))
            elif rate >= 80: it_rate.setForeground(QColor("#d4890a"))
            else: it_rate.setForeground(QColor("#c0392b"))
            it_rate.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.sessions_table.setItem(i, 8, it_rate)
            
            # Duration
            dur = s["duration_sec"]
            self.sessions_table.setItem(i, 9, QTableWidgetItem(f"{dur:.1f}s"))
            
            # Row tinting for problematic sessions
            if s["ng_count"] > 0 and rate < 80:
                for c in range(10):
                    self.sessions_table.item(i, c).setBackground(QColor("#fff0f0"))

    def _on_selection_changed(self) -> None:
        sel = self.sessions_table.selectedItems()
        if not sel: return
        row = sel[0].row()
        self._on_session_selected(row)

    def _on_session_selected(self, row: int) -> None:
        session_id = self.sessions_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._current_session_id = session_id
        
        detail = self._state.report_repo.get_session_detail(session_id)
        if detail:
            self._show_session_detail(detail)
            self.selected_lbl.setText(f"Session #{session_id} selected")
            self.btn_ex_sess.setEnabled(True)
            self.btn_pdf.setEnabled(True)

    def _show_session_detail(self, detail: dict) -> None:
        self.placeholder_lbl.hide()
        self.detail_content.show()
        
        session = detail["session"]
        results = detail["results"]
        alarms  = detail["alarms"]
        
        model_name = session.get("model_name", "Unknown")
        dt_str = session["started_at"]
        self.session_title.setText(f"{model_name} — {dt_str[:16]}")
        
        # Overall result from counts
        has_ng = session["ng_count"] > 0
        if has_ng:
            self.overall_result_badge.setText("FAIL")
            self.overall_result_badge.setStyleSheet("background: #c0392b; font-size: 18px; font-weight: bold; color: white; border-radius: 4px;")
            self.overall_result_badge.setObjectName("lbl_fail")
        else:
            self.overall_result_badge.setText("PASS")
            self.overall_result_badge.setStyleSheet("background: #1a6b3a; font-size: 18px; font-weight: bold; color: white; border-radius: 4px;")
            self.overall_result_badge.setObjectName("lbl_pass")
            
        # Preview table
        self.results_preview.setRowCount(0)
        for i, r in enumerate(results[:20]): # Limit preview for speed
            self.results_preview.insertRow(i)
            self.results_preview.setItem(i, 0, QTableWidgetItem(r["param_name"]))
            
            it_res = QTableWidgetItem(r["result"])
            if r["result"] == "PASS": it_res.setForeground(QColor("#1a6b3a"))
            elif r["result"] == "FAIL": it_res.setForeground(QColor("#c0392b"))
            self.results_preview.setItem(i, 1, it_res)
            
            self.results_preview.setItem(i, 2, QTableWidgetItem(f"{r['measured_value']:.2f}"))
            self.results_preview.setItem(i, 3, QTableWidgetItem(f"{r['limit_min']:.2f}"))
            self.results_preview.setItem(i, 4, QTableWidgetItem(f"{r['limit_max']:.2f}"))
            
        # Alarms
        n_alarms = len(alarms)
        if n_alarms > 0:
            self.alarm_lbl.setText(f"⚠ {n_alarms} alarm(s) recorded")
            self.alarm_lbl.show()
        else:
            self.alarm_lbl.hide()

    def _on_session_double_clicked(self, item: QTableWidgetItem) -> None:
        # Auto trigger PDF export on double click
        self._on_export_pdf()

    def _on_export_excel_session(self) -> None:
        if not self._current_session_id: return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel Report",
            f"reports/session_{self._current_session_id}.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path: return
        
        self._start_export("excel_session", path, session_id=self._current_session_id)

    def _on_export_excel_shift(self) -> None:
        now_str = datetime.now().strftime("%Y%m%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Shift Report",
            f"reports/shift_{now_str}.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path: return
        
        model_id = self.model_filter.currentData()
        self._start_export(
            "excel_shift", path,
            model_id=model_id,
            date_from=self.date_from.date().toString("yyyy-MM-dd"),
            date_to=self.date_to.date().toString("yyyy-MM-dd")
        )

    def _on_export_pdf(self) -> None:
        if not self._current_session_id: return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Certificate",
            f"reports/cert_{self._current_session_id}.pdf",
            "PDF Files (*.pdf)"
        )
        if not path: return
        
        self._start_export("pdf_certificate", path, session_id=self._current_session_id)

    def _start_export(self, report_type: str, output_path: str, **kwargs) -> None:
        os.makedirs("reports", exist_ok=True)
        
        self._set_export_buttons_enabled(False)
        self.progress_area.show()
        self.export_progress.setValue(0)
        self.progress_lbl.setText("Initializing...")
        
        exporter = self._excel_exp if "excel" in report_type else self._pdf_exp
        
        self._worker = ReportWorker(report_type, exporter, output_path, **kwargs)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_export_done)
        self._worker.error.connect(self._on_export_error)
        self._worker.start()

    def _on_worker_progress(self, pct: int, msg: str) -> None:
        self.export_progress.setValue(pct)
        self.progress_lbl.setText(msg)

    def _on_export_done(self, path: str) -> None:
        self.progress_area.hide()
        self._set_export_buttons_enabled(True)
        
        reply = QMessageBox.information(
            self, "Export Complete",
            f"Report saved to:\n{path}",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok
        )
        if reply == QMessageBox.StandardButton.Open:
            os.startfile(path)

    def _on_export_error(self, error: str) -> None:
        self.progress_area.hide()
        self._set_export_buttons_enabled(True)
        QMessageBox.critical(self, "Export Failed", f"Report generation failed:\n{error}")

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self.btn_ex_sess.setEnabled(enabled and self._current_session_id is not None)
        self.btn_ex_shift.setEnabled(enabled)
        self.btn_pdf.setEnabled(enabled and self._current_session_id is not None)
        self.btn_open_folder.setEnabled(enabled)
        self.btn_search.setEnabled(enabled)

    def _on_open_folder(self) -> None:
        folder = os.path.abspath("reports")
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)
