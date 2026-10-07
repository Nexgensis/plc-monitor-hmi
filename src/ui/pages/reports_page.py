"""
reports_page.py — Universal PLC Monitor
Production history, session details, and report export center.
Supports Excel and PDF export for quality certification.
Bulk results table shows ALL results from ALL sessions in the date range.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFrame, QComboBox, QDateEdit,
                             QGroupBox, QListWidget, QTextEdit, QFileDialog,
                             QGridLayout, QMenu)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QAction

from src.ui.app_state import AppState
from src.ui.components.charts import PieChart, BarChart
from src.ui.components.toast import ToastManager
from src.ui.theme_manager import ThemeManager
from src.utils.exporters import ExcelExporter, PDFExporter

logger = logging.getLogger(__name__)

# Results table column definitions
RESULTS_COLUMNS = ["Session#", "Date", "Time", "Module", "Parameter",
                   "Measured", "Min", "Max", "User", "Result"]
RESULTS_COL_COUNT = len(RESULTS_COLUMNS)


def _fg(token: str) -> QColor:
    """Theme-aware design token as QColor (resolved at paint/populate time)."""
    return QColor(ThemeManager.get_color(token))


class ExportWorker(QThread):
    """Background worker for single-session report generation."""
    finished = pyqtSignal(str)

    def __init__(self, exporter_type: str, file_path: str, data: dict) -> None:
        super().__init__()
        self.exporter_type = exporter_type
        self.file_path = file_path
        self.data = data

    def run(self) -> None:
        try:
            logger.info(f"ExportWorker running: type={self.exporter_type}, path={self.file_path}")
            if self.exporter_type == "excel":
                res = ExcelExporter.export_session(self.file_path, self.data)
            else:
                res = PDFExporter.export_session(self.file_path, self.data)
            logger.info(f"ExportWorker result: {res}")
            self.finished.emit(res)
        except Exception as e:
            logger.error(f"ExportWorker exception: {e}")
            self.finished.emit(f"Error: {e}")


class BulkExportWorker(QThread):
    """Background worker for bulk (all-sessions) report generation."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, exporter_type: str, file_path: str,
                 sessions_data: list, all_results: list) -> None:
        super().__init__()
        self.exporter_type = exporter_type
        self.file_path = file_path
        self.sessions_data = sessions_data
        self.all_results = all_results

    def run(self) -> None:
        try:
            self.progress.emit("Preparing data...")
            data = {
                "sessions": self.sessions_data,
                "results": self.all_results,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            logger.info(f"BulkExportWorker running: type={self.exporter_type}, "
                        f"sessions={len(self.sessions_data)}, results={len(self.all_results)}")
            if self.exporter_type == "excel":
                res = ExcelExporter.export_bulk(self.file_path, data)
            else:
                res = PDFExporter.export_bulk(self.file_path, data)
            logger.info(f"BulkExportWorker result: {res}")
            self.finished.emit(res)
        except Exception as e:
            logger.error(f"BulkExportWorker exception: {e}")
            self.finished.emit(f"Error: {e}")


class ReportsPage(QWidget):
    """
    Unified reporting interface for viewing and exporting test history.
    The results table shows ALL results from ALL sessions in the selected date range.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self._current_session_id: Optional[int] = None
        self._highlighted_session_id: Optional[int] = None
        self._bulk_results: List[Dict[str, Any]] = []
        self._sessions_for_export: List[Dict[str, Any]] = []
        self.setAccessibleName("Reports page")
        self._init_ui()
        ThemeManager.bus().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme: str) -> None:
        """Re-populate tables so token-based row colors match the new theme."""
        if not self._sessions_for_export:
            return
        highlighted = self._highlighted_session_id
        self._on_search()
        if highlighted is not None:
            self._highlight_session(highlighted)

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- LEFT: Search & History ---
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # Filter Bar
        filter_card = QFrame()
        filter_card.setObjectName("reports_filter_card")
        f_layout = QVBoxLayout(filter_card)

        # Date range presets row
        f_layout.setSpacing(10)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.model_filter = QComboBox()
        self.model_filter.addItem("All Models", None)
        filter_row.addWidget(self.model_filter)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setAccessibleName("Start date")
        filter_row.addWidget(self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setAccessibleName("End date")
        filter_row.addWidget(self.date_to)

        btn_search = QPushButton("🔍")
        btn_search.setObjectName("btn_primary")
        btn_search.setFixedSize(32, 32)
        btn_search.setAccessibleName("Search sessions")
        btn_search.setToolTip("Search for test sessions within date range")
        btn_search.clicked.connect(self._on_search)
        filter_row.addWidget(btn_search)

        btn_export_menu = QPushButton("⬇")
        btn_export_menu.setObjectName("btn_accent")
        btn_export_menu.setFixedSize(32, 32)
        btn_export_menu.setAccessibleName("Export options")
        btn_export_menu.setToolTip("Export options")
        export_menu = QMenu()
        act_xl_session = QAction("Session → Excel", self)
        act_xl_session.triggered.connect(lambda: self._start_export("excel"))
        export_menu.addAction(act_xl_session)
        act_pdf_session = QAction("Session → PDF Certificate", self)
        act_pdf_session.triggered.connect(lambda: self._start_export("pdf"))
        export_menu.addAction(act_pdf_session)
        export_menu.addSeparator()
        act_xl_bulk = QAction("All Sessions → Excel", self)
        act_xl_bulk.triggered.connect(lambda: self._start_bulk_export("excel"))
        export_menu.addAction(act_xl_bulk)
        act_pdf_bulk = QAction("All Sessions → PDF", self)
        act_pdf_bulk.triggered.connect(lambda: self._start_bulk_export("pdf"))
        export_menu.addAction(act_pdf_bulk)
        btn_export_menu.setMenu(export_menu)
        filter_row.addWidget(btn_export_menu)

        f_layout.addLayout(filter_row)

        left_col.addWidget(filter_card)

        # Export progress / status card (styled by QSS: reports_export_card)
        self.export_bar = QFrame()
        self.export_bar.setObjectName("reports_export_card")
        export_bar_layout = QHBoxLayout(self.export_bar)
        export_bar_layout.setContentsMargins(10, 6, 10, 6)
        self.export_status = QLabel("")
        self.export_status.setObjectName("reports_export_status")
        self.export_status.setWordWrap(True)
        self.export_status.setAccessibleName("Export status")
        export_bar_layout.addWidget(self.export_status)
        self.export_bar.setVisible(False)
        left_col.addWidget(self.export_bar)

        # Summary Stats
        stats_frame = QFrame()
        stats_frame.setObjectName("reports_stats_frame")
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setSpacing(10)

        self.stat_total = self._make_stat_card(stats_layout, 0, 0, "TOTAL SESSIONS", "0")
        self.stat_ok = self._make_stat_card(stats_layout, 0, 1, "TOTAL OK", "0")
        self.stat_ng = self._make_stat_card(stats_layout, 0, 2, "TOTAL NG", "0")
        self.stat_pass_rate = self._make_stat_card(stats_layout, 0, 3, "AVG PASS RATE", "0%")

        left_col.addWidget(stats_frame)

        # Sessions Table (left panel — summary)
        self.session_table = QTableWidget(0, 7)
        self.session_table.setHorizontalHeaderLabels(["#", "Date", "Time", "Model", "OK", "NG", "Pass%"])
        self.session_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.session_table.setAlternatingRowColors(True)
        self.session_table.setAccessibleName("Test session history")
        self.session_table.setToolTip("Click a session to highlight its results on the right")
        self.session_table.itemClicked.connect(self._on_session_selected)
        left_col.addWidget(self.session_table, 1)

        layout.addLayout(left_col, stretch=2)

        # --- RIGHT: Bulk Results & Export ---
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # Charts Row
        charts_frame = QFrame()
        charts_frame.setObjectName("reports_charts_frame")
        charts_layout = QHBoxLayout(charts_frame)
        charts_layout.setSpacing(10)

        pie_card = QFrame()
        pie_card_layout = QVBoxLayout(pie_card)
        pie_card_layout.setSpacing(4)
        pie_title = QLabel("PASS/FAIL DISTRIBUTION")
        pie_title.setObjectName("chart_title")
        pie_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pie_card_layout.addWidget(pie_title)
        self.pie_chart = PieChart()
        pie_card_layout.addWidget(self.pie_chart, alignment=Qt.AlignmentFlag.AlignCenter)
        charts_layout.addWidget(pie_card)

        bar_card = QFrame()
        bar_card_layout = QVBoxLayout(bar_card)
        bar_card_layout.setSpacing(4)
        bar_title = QLabel("TOP FAILURES")
        bar_title.setObjectName("chart_title")
        bar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_card_layout.addWidget(bar_title)
        self.bar_chart = BarChart()
        bar_card_layout.addWidget(self.bar_chart)
        charts_layout.addWidget(bar_card)

        right_col.addWidget(charts_frame)

        # Detail Panel — 10-column bulk results table
        self.detail_card = QFrame()
        self.detail_card.setObjectName("reports_detail_card")
        self.detail_layout = QVBoxLayout(self.detail_card)

        self.detail_placeholder = QLabel("Search to load all results across sessions")
        self.detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_placeholder.setObjectName("reports_detail_placeholder")
        self.detail_layout.addWidget(self.detail_placeholder)

        # Title shown when results are loaded
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("reports_detail_title")
        self.detail_title.setVisible(False)
        self.detail_layout.addWidget(self.detail_title)

        self.res_table = QTableWidget(0, RESULTS_COL_COUNT)
        self.res_table.setHorizontalHeaderLabels(RESULTS_COLUMNS)
        self.res_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.res_table.setAlternatingRowColors(True)
        self.res_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.res_table.setSortingEnabled(True)
        self.res_table.setVisible(False)
        self.detail_layout.addWidget(self.res_table)

        right_col.addWidget(self.detail_card, 1)

        # Comments Area
        self.comm_box = QGroupBox("Session Comments")
        comm_layout = QVBoxLayout(self.comm_box)
        self.comm_list = QListWidget()
        self.comm_list.setFixedHeight(80)
        comm_layout.addWidget(self.comm_list)

        input_layout = QHBoxLayout()
        self.comm_input = QTextEdit()
        self.comm_input.setFixedHeight(32)
        self.comm_input.setPlaceholderText("Add a comment...")
        input_layout.addWidget(self.comm_input)

        btn_add_comm = QPushButton("+")
        btn_add_comm.setObjectName("btn_secondary")
        btn_add_comm.setFixedSize(28, 28)
        btn_add_comm.clicked.connect(self._on_add_comment)
        input_layout.addWidget(btn_add_comm)
        comm_layout.addLayout(input_layout)

        right_col.addWidget(self.comm_box)
        self.comm_box.setVisible(False)

        layout.addLayout(right_col, stretch=1)

    # ─── Page lifecycle ────────────────────────────────────────────────

    def on_page_shown(self) -> None:
        self._refresh_filters()
        self._on_search()

    # ─── Filter helpers ────────────────────────────────────────────────

    def _make_stat_card(self, layout: QGridLayout, row: int, col: int,
                        title: str, value: str) -> QLabel:
        card = QFrame()
        card.setObjectName("stat_card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(10, 8, 10, 8)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("stat_title")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        value_lbl = QLabel(value)
        value_lbl.setObjectName("stat_value")
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_lbl)

        layout.addWidget(card, row, col)
        return value_lbl

    def _update_summary_stats(self, sessions: list) -> None:
        total = len(sessions)
        total_ok = sum(s.get("ok_count", 0) for s in sessions)
        total_ng = sum(s.get("ng_count", 0) for s in sessions)
        avg_rate = sum(s.get("pass_rate_pct", 0) for s in sessions) / total if total > 0 else 0

        self.stat_total.setText(str(total))
        self.stat_ok.setText(str(total_ok))
        self.stat_ng.setText(str(total_ng))
        self.stat_pass_rate.setText(f"{avg_rate:.1f}%")

        if avg_rate >= 95:
            self.stat_pass_rate.setProperty("rate_level", "high")
        elif avg_rate >= 80:
            self.stat_pass_rate.setProperty("rate_level", "medium")
        else:
            self.stat_pass_rate.setProperty("rate_level", "low")
        self.stat_pass_rate.style().unpolish(self.stat_pass_rate)
        self.stat_pass_rate.style().polish(self.stat_pass_rate)

    def _refresh_filters(self) -> None:
        self.model_filter.clear()
        self.model_filter.addItem("All Models", None)
        models = self.app_state.model_repo.get_all_models()
        for m in models:
            self.model_filter.addItem(m["name"], m["id"])

    # ─── Search ────────────────────────────────────────────────────────

    def _on_search(self) -> None:
        mid = self.model_filter.currentData()
        df = self.date_from.date().toString("yyyy-MM-dd")
        dt = self.date_to.date().toString("yyyy-MM-dd")

        # Populate session summary table (left panel)
        sessions = self.app_state.report_repo.get_sessions_summary(mid, df, dt)
        self._sessions_for_export = sessions
        self.session_table.setRowCount(len(sessions))

        if len(sessions) == 0:
            self.session_table.setRowCount(1)
            item = QTableWidgetItem("No sessions found for the selected date range.")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.session_table.setSpan(0, 0, 1, 7)
            self.session_table.setItem(0, 0, item)
            self.pie_chart.set_data(0, 0)
            self.bar_chart.set_data([])
        else:
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
                if rate >= 95:
                    rate_item.setForeground(_fg("pass"))
                elif rate >= 80:
                    rate_item.setForeground(_fg("warn"))
                else:
                    rate_item.setForeground(_fg("fail"))
                self.session_table.setItem(i, 6, rate_item)

            self._update_summary_stats(sessions)

        # Load bulk results into the right panel
        self._load_bulk_results(mid, df, dt)

        # Reset selection state
        self._current_session_id = None
        self._highlighted_session_id = None
        self.comm_box.setVisible(False)

    def _load_bulk_results(self, model_id, date_from, date_to) -> None:
        """Load ALL results from ALL sessions into the right-panel table."""
        all_results = self.app_state.report_repo.get_all_results_for_range(
            model_id, date_from, date_to
        )
        self._bulk_results = all_results

        if not all_results:
            self.detail_placeholder.setVisible(True)
            self.detail_title.setVisible(False)
            self.res_table.setVisible(False)
            return

        # Show results
        self.detail_placeholder.setVisible(False)
        self.detail_title.setVisible(True)
        self.res_table.setVisible(True)

        total_rows = len(all_results)
        self.detail_title.setText(
            f"All Results — {total_rows} measurements across "
            f"{len(self._sessions_for_export)} sessions"
        )

        self.res_table.setSortingEnabled(False)
        self.res_table.setRowCount(total_rows)

        fail_counts: dict[str, int] = {}
        for i, r in enumerate(all_results):
            # Session#
            sid_item = QTableWidgetItem(str(r["session_id"]))
            sid_item.setData(Qt.ItemDataRole.UserRole, r["session_id"])
            self.res_table.setItem(i, 0, sid_item)

            # Date + Time
            started = r.get("started_at", "")
            try:
                dt_obj = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
                date_str = dt_obj.strftime("%Y-%m-%d")
                time_str = dt_obj.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                date_str = started[:10] if started else ""
                time_str = started[11:19] if len(started) >= 19 else ""
            self.res_table.setItem(i, 1, QTableWidgetItem(date_str))
            self.res_table.setItem(i, 2, QTableWidgetItem(time_str))

            # Module + Parameter
            self.res_table.setItem(i, 3, QTableWidgetItem(r.get("group_name", "")))
            self.res_table.setItem(i, 4, QTableWidgetItem(r.get("display_name", "")))

            # Measured
            unit = r.get("unit", "") or ""
            _u = f" {unit}" if unit else ""
            measured = r.get("measured_value", 0.0)
            m_item = QTableWidgetItem(f"{measured:,.2f}{_u}")
            m_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.res_table.setItem(i, 5, m_item)

            # Min
            min_val = r.get("limit_min", 0.0)
            min_item = QTableWidgetItem(f"{min_val:,.2f}{_u}")
            min_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.res_table.setItem(i, 6, min_item)

            # Max
            max_val = r.get("limit_max", 0.0)
            max_item = QTableWidgetItem(f"{max_val:,.2f}{_u}")
            max_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.res_table.setItem(i, 7, max_item)

            # User
            self.res_table.setItem(i, 8, QTableWidgetItem(r.get("operator_name", "")))

            # Result
            result = r.get("result", "PENDING")
            if result == "PENDING" and not (float(r.get("limit_min", 0.0)) or float(r.get("limit_max", 0.0))):
                result = "N/A"
            res_item = QTableWidgetItem(result)
            if result == "PASS":
                res_item.setForeground(_fg("pass"))
            elif result == "FAIL":
                res_item.setForeground(_fg("fail"))
                name = r.get("display_name", "")
                fail_counts[name] = fail_counts.get(name, 0) + 1
            elif result == "BYPASS":
                res_item.setForeground(_fg("warn"))
            elif result == "N/A":
                res_item.setForeground(_fg("text_muted"))
            self.res_table.setItem(i, 9, res_item)

        self.res_table.setSortingEnabled(True)

        # Set column widths
        header = self.res_table.horizontalHeader()
        header.resizeSection(0, 60)   # Session#
        header.resizeSection(1, 90)   # Date
        header.resizeSection(2, 70)   # Time
        header.resizeSection(3, 110)  # Module
        header.resizeSection(4, 140)  # Parameter
        header.resizeSection(5, 80)   # Measured
        header.resizeSection(6, 70)   # Min
        header.resizeSection(7, 70)   # Max
        header.resizeSection(8, 90)   # User
        header.resizeSection(9, 70)   # Result

        # Charts from all results
        total_pass = sum(1 for r in all_results if r.get("result") == "PASS")
        total_fail = sum(1 for r in all_results if r.get("result") == "FAIL")
        self.pie_chart.set_data(total_pass, total_fail)
        self.bar_chart.set_data(list(fail_counts.items()))

    # ─── Session selection → highlight ─────────────────────────────────

    def _on_session_selected(self, item: QTableWidgetItem) -> None:
        row = item.row()

        # Guard: skip empty state row
        if self.session_table.columnSpan(row, 0) > 1:
            return

        try:
            clicked_id = int(self.session_table.item(row, 0).text())
        except (ValueError, TypeError):
            return

        # Toggle highlight: clicking same session again clears it
        if self._highlighted_session_id == clicked_id:
            self._highlighted_session_id = None
            self._current_session_id = None
            self.comm_box.setVisible(False)
            self._clear_highlight()
            return

        self._current_session_id = clicked_id
        self._highlighted_session_id = clicked_id

        # Show comments
        self.comm_box.setVisible(True)
        self._load_comments(clicked_id)

        # Highlight rows in the bulk results table
        self._highlight_session(clicked_id)

        # Scroll to first matching row
        self._scroll_to_session(clicked_id)

    def _highlight_session(self, session_id: int) -> None:
        """Apply visual highlight to all rows belonging to the given session."""
        self._clear_highlight()
        for row in range(self.res_table.rowCount()):
            sid_item = self.res_table.item(row, 0)
            if sid_item and sid_item.data(Qt.ItemDataRole.UserRole) == session_id:
                for col in range(RESULTS_COL_COUNT):
                    cell = self.res_table.item(row, col)
                    if cell:
                        cell.setBackground(_fg("border"))

    def _clear_highlight(self) -> None:
        """Remove highlight from all rows."""
        for row in range(self.res_table.rowCount()):
            for col in range(RESULTS_COL_COUNT):
                cell = self.res_table.item(row, col)
                if cell:
                    cell.setBackground(QColor(0, 0, 0, 0))  # transparent

    def _scroll_to_session(self, session_id: int) -> None:
        """Scroll the results table to the first row of the given session."""
        for row in range(self.res_table.rowCount()):
            sid_item = self.res_table.item(row, 0)
            if sid_item and sid_item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.res_table.scrollToItem(sid_item)
                break

    def _load_comments(self, session_id: int) -> None:
        """Load comments for a session into the comments list."""
        detail = self.app_state.report_repo.get_session_detail(session_id)
        if not detail:
            return
        self.comm_list.clear()
        for c in detail.get("comments", []):
            self.comm_list.addItem(f"[{c['username']}]: {c['comment']}")

    # ─── Add comment ──────────────────────────────────────────────────

    def _on_add_comment(self) -> None:
        if not self._current_session_id:
            ToastManager.instance().warning("Please select a session first.")
            return
        txt = self.comm_input.toPlainText().strip()
        if not txt:
            return

        try:
            self.app_state.session_repo.add_comment(
                self._current_session_id,
                self.app_state.current_user["id"],
                txt
            )
            self.comm_input.clear()
            self._load_comments(self._current_session_id)
        except Exception as e:
            logger.error(f"Failed to add comment: {e}")

    # ─── Single-session export ─────────────────────────────────────────

    def _start_export(self, fmt: str) -> None:
        logger.info(f"Export requested: fmt={fmt}, session_id={self._current_session_id}")
        if not self._current_session_id:
            logger.warning("Export aborted: no session selected")
            return

        try:
            detail = self.app_state.report_repo.get_session_detail(self._current_session_id)
            if not detail:
                ToastManager.instance().error("No session data found.")
                return
        except Exception as e:
            logger.error(f"Failed to get session detail: {e}")
            ToastManager.instance().error(f"Failed to load session: {e}")
            return

        ext = "xlsx" if fmt == "excel" else "pdf"
        default_name = f"Session_{self._current_session_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}"

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        output_dir = os.path.join(project_root, "reports_output")
        os.makedirs(output_dir, exist_ok=True)

        file_path, _ = QFileDialog.getSaveFileName(
            self.window(), "Save Export",
            os.path.join(output_dir, default_name),
            f"{fmt.upper()} Files (*.{ext})"
        )
        if not file_path:
            return

        logger.info(f"Export starting: {file_path}")
        self.export_bar.setVisible(True)
        self.export_status.setText("Exporting...")

        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(2000)

        self.worker = ExportWorker(fmt, file_path, detail)
        self.worker.finished.connect(self._on_export_finished)
        self.worker.start()

    # ─── Bulk export ──────────────────────────────────────────────────

    def _start_bulk_export(self, fmt: str) -> None:
        logger.info(f"Bulk export requested: fmt={fmt}")
        if not self._bulk_results:
            ToastManager.instance().warning("No results to export. Run a search first.")
            return

        ext = "xlsx" if fmt == "excel" else "pdf"
        df = self.date_from.date().toString("yyyyMMdd")
        dt = self.date_to.date().toString("yyyyMMdd")
        default_name = f"Production_Report_{df}_{dt}.{ext}"

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        output_dir = os.path.join(project_root, "reports_output")
        os.makedirs(output_dir, exist_ok=True)

        file_path, _ = QFileDialog.getSaveFileName(
            self.window(), "Save Bulk Export",
            os.path.join(output_dir, default_name),
            f"{fmt.upper()} Files (*.{ext})"
        )
        if not file_path:
            return

        logger.info(f"Bulk export starting: {file_path}")
        self.export_bar.setVisible(True)
        self.export_status.setText("Exporting all sessions...")

        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(2000)

        self.worker = BulkExportWorker(
            fmt, file_path, self._sessions_for_export, self._bulk_results
        )
        self.worker.finished.connect(self._on_export_finished)
        self.worker.start()

    # ─── Export finish callback ────────────────────────────────────────

    def _on_export_finished(self, result: str) -> None:
        logger.info(f"Export finished: {result}")
        self.export_status.setText(result)
        if result.startswith("Success"):
            self.export_status.setProperty("status", "success")
            ToastManager.instance().success("Report exported successfully")
        else:
            self.export_status.setProperty("status", "error")
            ToastManager.instance().error(f"Export failed: {result}")
        self.export_status.style().unpolish(self.export_status)
        self.export_status.style().polish(self.export_status)
