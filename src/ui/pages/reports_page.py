"""
reports_page.py — Universal PLC Monitor
Production history, session details, and report export center.
Supports Excel and PDF export for quality certification.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QFrame, QComboBox, QDateEdit,
                             QGroupBox, QListWidget, QTextEdit, QFileDialog,
                             QProgressBar)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from src.ui.app_state import AppState
from src.utils.exporters import ExcelExporter, PDFExporter

logger = logging.getLogger(__name__)


class ExportWorker(QThread):
    """Background worker for report generation."""
    finished = pyqtSignal(str)

    def __init__(self, exporter_type: str, file_path: str, data: dict) -> None:
        super().__init__()
        self.exporter_type = exporter_type
        self.file_path = file_path
        self.data = data

    def run(self) -> None:
        if self.exporter_type == "excel":
            res = ExcelExporter.export_session(self.file_path, self.data)
        else:
            res = PDFExporter.export_session(self.file_path, self.data)
        self.finished.emit(res)


class ReportsPage(QWidget):
    """
    Unified reporting interface for viewing and exporting test history.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self._current_session_id: Optional[int] = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # --- LEFT: Search & History ---
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        
        # Filter Bar
        filter_card = QFrame()
        filter_card.setObjectName("card")
        filter_card.setStyleSheet("background: #0f172a; border-radius: 8px; padding: 10px;")
        f_layout = QHBoxLayout(filter_card)
        
        self.model_filter = QComboBox()
        self.model_filter.addItem("All Models", None)
        f_layout.addWidget(self.model_filter)
        
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        f_layout.addWidget(self.date_from)
        
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        f_layout.addWidget(self.date_to)
        
        btn_search = QPushButton("🔍 Search")
        btn_search.setObjectName("btn_primary")
        btn_search.clicked.connect(self._on_search)
        f_layout.addWidget(btn_search)
        
        left_col.addWidget(filter_card)

        # Sessions Table
        self.session_table = QTableWidget(0, 7)
        self.session_table.setHorizontalHeaderLabels(["#", "Date", "Time", "Model", "OK", "NG", "Pass%"])
        self.session_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.session_table.setAlternatingRowColors(True)
        self.session_table.itemDoubleClicked.connect(self._on_session_selected)
        left_col.addWidget(self.session_table, 1)

        # Comments Area
        comm_box = QGroupBox("Session Comments")
        comm_layout = QVBoxLayout(comm_box)
        self.comm_list = QListWidget()
        self.comm_list.setFixedHeight(100)
        comm_layout.addWidget(self.comm_list)
        
        input_layout = QHBoxLayout()
        self.comm_input = QTextEdit()
        self.comm_input.setFixedHeight(40)
        self.comm_input.setPlaceholderText("Add a comment...")
        input_layout.addWidget(self.comm_input)
        
        btn_add_comm = QPushButton("Add")
        btn_add_comm.setObjectName("btn_secondary")
        btn_add_comm.clicked.connect(self._on_add_comment)
        input_layout.addWidget(btn_add_comm)
        comm_layout.addLayout(input_layout)
        
        left_col.addWidget(comm_box)
        layout.addLayout(left_col, stretch=2)

        # --- RIGHT: Details & Export ---
        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        
        # Detail Panel
        self.detail_card = QFrame()
        self.detail_card.setObjectName("card")
        self.detail_card.setStyleSheet("background: #0f172a; border-radius: 8px; padding: 15px;")
        self.detail_layout = QVBoxLayout(self.detail_card)
        
        self.detail_placeholder = QLabel("Select a session to view details")
        self.detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_placeholder.setStyleSheet("color: #5a7a9a;")
        self.detail_layout.addWidget(self.detail_placeholder)
        
        # Hidden detail components
        self.detail_title = QLabel("")
        self.detail_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e8f0fa;")
        self.detail_title.setVisible(False)
        self.detail_layout.addWidget(self.detail_title)
        
        self.res_table = QTableWidget(0, 3)
        self.res_table.setHorizontalHeaderLabels(["Parameter", "Value", "Result"])
        self.res_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.res_table.setVisible(False)
        self.detail_layout.addWidget(self.res_table)
        
        right_col.addWidget(self.detail_card, 1)

        # Export Panel
        export_card = QFrame()
        export_card.setStyleSheet("background: #1e293b; border-radius: 8px; padding: 15px;")
        export_layout = QVBoxLayout(export_card)
        
        export_layout.addWidget(QLabel("<b>EXPORT OPTIONS</b>"))
        
        btn_xl = QPushButton("📊 Excel — Session Report")
        btn_xl.setObjectName("btn_primary")
        btn_xl.clicked.connect(lambda: self._start_export("excel"))
        export_layout.addWidget(btn_xl)
        
        btn_pdf = QPushButton("📄 PDF — Test Certificate")
        btn_pdf.setObjectName("btn_primary")
        btn_pdf.clicked.connect(lambda: self._start_export("pdf"))
        export_layout.addWidget(btn_pdf)
        
        self.export_bar = QProgressBar()
        self.export_bar.setRange(0, 0) # Indeterminate
        self.export_bar.setVisible(False)
        export_layout.addWidget(self.export_bar)
        
        self.export_status = QLabel("")
        self.export_status.setStyleSheet("font-size: 10px; color: #5a7a9a;")
        export_layout.addWidget(self.export_status)
        
        right_col.addWidget(export_card)
        layout.addLayout(right_col, stretch=1)

    def on_page_shown(self) -> None:
        self._refresh_filters()
        self._on_search()

    def _refresh_filters(self) -> None:
        self.model_filter.clear()
        self.model_filter.addItem("All Models", None)
        models = self.app_state.model_repo.get_all_models()
        for m in models:
            self.model_filter.addItem(m["name"], m["id"])

    def _on_search(self) -> None:
        mid = self.model_filter.currentData()
        df = self.date_from.date().toString("yyyy-MM-dd")
        dt = self.date_to.date().toString("yyyy-MM-dd")
        
        sessions = self.app_state.report_repo.get_sessions_summary(mid, df, dt)
        self.session_table.setRowCount(len(sessions))
        
        for i, s in enumerate(sessions):
            self.session_table.setItem(i, 0, QTableWidgetItem(str(s["session_id"])))
            dt_obj = datetime.strptime(s["started_at"], "%Y-%m-%d %H:%M:%S")
            self.session_table.setItem(i, 1, QTableWidgetItem(dt_obj.strftime("%Y-%m-%d")))
            self.session_table.setItem(i, 2, QTableWidgetItem(dt_obj.strftime("%H:%M:%S")))
            self.session_table.setItem(i, 3, QTableWidgetItem(s["model_name"]))
            self.session_table.setItem(i, 4, QTableWidgetItem(str(s["ok_count"])))
            self.session_table.setItem(i, 5, QTableWidgetItem(str(s["ng_count"])))
            
            rate = s["pass_rate_pct"]
            rate_item = QTableWidgetItem(f"{rate:.1f}%")
            if rate >= 95: rate_item.setForeground(QColor("#22c55e"))
            elif rate >= 80: rate_item.setForeground(QColor("#f59e0b"))
            else: rate_item.setForeground(QColor("#ef4444"))
            self.session_table.setItem(i, 6, rate_item)

    def _on_session_selected(self, item: QTableWidgetItem) -> None:
        row = item.row()
        self._current_session_id = int(self.session_table.item(row, 0).text())
        
        detail = self.app_state.report_repo.get_session_detail(self._current_session_id)
        if not detail: return
        
        self.detail_placeholder.setVisible(False)
        self.detail_title.setVisible(True)
        self.res_table.setVisible(True)
        
        session = detail["session"]
        self.detail_title.setText(f"Session #{session['id']} — {session['overall_result']}")
        
        # Flat list for result table
        all_res = []
        for grp, results in detail["results"].items():
            for r in results:
                all_res.append(r)
        
        self.res_table.setRowCount(len(all_res))
        for i, r in enumerate(all_res):
            self.res_table.setItem(i, 0, QTableWidgetItem(r["display_name"]))
            self.res_table.setItem(i, 1, QTableWidgetItem(str(r["measured_value"])))
            res_item = QTableWidgetItem(r["result"])
            if r["result"] == "PASS": res_item.setForeground(QColor("#22c55e"))
            elif r["result"] == "FAIL": res_item.setForeground(QColor("#ef4444"))
            self.res_table.setItem(i, 2, res_item)
            
        # Comments
        self.comm_list.clear()
        for c in detail["comments"]:
            self.comm_list.addItem(f"[{c['username']}]: {c['comment']}")

    def _on_add_comment(self) -> None:
        if not self._current_session_id: return
        txt = self.comm_input.toPlainText().strip()
        if not txt: return
        
        try:
            self.app_state.session_repo.add_comment(
                self._current_session_id, 
                self.app_state.current_user["id"], 
                txt
            )
            self.comm_input.clear()
            # Refresh details
            self._on_session_selected(self.session_table.currentItem())
        except Exception as e:
            logger.error(f"Failed to add comment: {e}")

    def _start_export(self, fmt: str) -> None:
        if not self._current_session_id: return
        
        detail = self.app_state.report_repo.get_session_detail(self._current_session_id)
        ext = "xlsx" if fmt == "excel" else "pdf"
        default_name = f"Session_{self._current_session_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Export", default_name, f"{fmt.upper()} Files (*.{ext})")
        if not file_path: return
        
        self.export_bar.setVisible(True)
        self.export_status.setText("Exporting...")
        
        self.worker = ExportWorker(fmt, file_path, detail)
        self.worker.finished.connect(self._on_export_finished)
        self.worker.start()

    def _on_export_finished(self, result: str) -> None:
        self.export_bar.setVisible(False)
        self.export_status.setText(result)
        if result.startswith("Success"):
            self.export_status.setStyleSheet("color: #22c55e;")
        else:
            self.export_status.setStyleSheet("color: #ef4444;")
