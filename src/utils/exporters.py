"""
exporters.py — Universal PLC Monitor
Consolidated Excel and PDF export for single-session and bulk reports.
Uses openpyxl for Excel and reportlab for PDF.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
except ImportError:
    openpyxl = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as _pdf_canvas
except ImportError:
    SimpleDocTemplate = None

# ─── Shared styles ────────────────────────────────────────────────────

NAVY = "1E2D4A"
LIGHT_GREY = "F3F4F6"
HEADER_FILL = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid") if openpyxl else None
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10) if openpyxl else None
PASS_FILL = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid") if openpyxl else None
FAIL_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") if openpyxl else None
THIN_BORDER = (
    Border(left=Side(style='thin'), right=Side(style='thin'),
           top=Side(style='thin'), bottom=Side(style='thin'))
    if openpyxl else None
)


class ExcelExporter:
    """Static methods for Excel export — single session and bulk."""

    @staticmethod
    def _header_row(ws, row: int, headers: List[str]) -> None:
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER

    @staticmethod
    def _data_cell(ws, row: int, col: int, value, result: str = None) -> None:
        cell = ws.cell(row=row, column=col, value=value)
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="center")
        if result == "PASS" and PASS_FILL:
            cell.fill = PASS_FILL
        elif result == "FAIL" and FAIL_FILL:
            cell.fill = FAIL_FILL

    @staticmethod
    def export_session(file_path: str, data: Dict[str, Any]) -> str:
        """Export a single session to Excel (backward compatible)."""
        if not openpyxl:
            return "Error: openpyxl library not installed."

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Test Session"

            session = data["session"]
            ws.merge_cells("A1:F1")
            ws["A1"] = f"TEST CERTIFICATE — SESSION #{session.get('id', '')}"
            ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
            ws["A1"].fill = HEADER_FILL if HEADER_FILL else PatternFill()
            ws["A1"].alignment = Alignment(horizontal="center")

            ws["A3"] = "Model:"; ws["B3"] = session.get("model_name", "")
            ws["A4"] = "Date:"; ws["B4"] = session.get("started_at", "")
            ws["A5"] = "Operator:"; ws["B5"] = session.get("operator_name", "")
            ws["A6"] = "Result:"; ws["B6"] = session.get("overall_result", "")

            headers = ["Module", "Parameter", "Measured", "Min", "Max", "Result"]
            ExcelExporter._header_row(ws, 8, headers)

            row = 9
            for grp, results in data.get("results", {}).items():
                for r in results:
                    ExcelExporter._data_cell(ws, row, 1, grp, r.get("result"))
                    ExcelExporter._data_cell(ws, row, 2, r.get("display_name", ""), r.get("result"))
                    ExcelExporter._data_cell(ws, row, 3, _fmt_meas(r, "measured_value"), r.get("result"))
                    ExcelExporter._data_cell(ws, row, 4, _fmt_meas(r, "limit_min"), r.get("result"))
                    ExcelExporter._data_cell(ws, row, 5, _fmt_meas(r, "limit_max"), r.get("result"))
                    ExcelExporter._data_cell(ws, row, 6, r.get("result", ""), r.get("result"))
                    row += 1

            ws.column_dimensions['A'].width = 18
            ws.column_dimensions['B'].width = 25
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 10
            ws.column_dimensions['E'].width = 10
            ws.column_dimensions['F'].width = 10

            wb.save(file_path)
            return f"Success: Exported to {file_path}"
        except Exception as e:
            logger.error(f"Excel export error: {e}")
            return f"Error: {str(e)}"

    @staticmethod
    def export_bulk(file_path: str, data: Dict[str, Any]) -> str:
        """
        Bulk export: all sessions in a date range.
        data = {"sessions": [...], "results": [...], "generated_at": "..."}
        Produces 3 sheets: Summary, All Results, Failures Only.
        """
        if not openpyxl:
            return "Error: openpyxl library not installed."

        try:
            wb = openpyxl.Workbook()
            sessions = data.get("sessions", [])
            all_results = data.get("results", [])
            generated = data.get("generated_at", "")

            # ── Sheet 1: Summary ──
            ws_sum = wb.active
            ws_sum.title = "Summary"
            ws_sum.merge_cells("A1:I1")
            ws_sum["A1"] = f"PRODUCTION REPORT — Generated {generated}"
            ws_sum["A1"].font = Font(bold=True, size=14, color="FFFFFF")
            ws_sum["A1"].fill = HEADER_FILL if HEADER_FILL else PatternFill()
            ws_sum["A1"].alignment = Alignment(horizontal="center")

            sum_headers = ["#", "Date", "Time", "Model", "Operator", "OK", "NG", "Pass%", "Result"]
            ExcelExporter._header_row(ws_sum, 3, sum_headers)

            total_ok = 0
            total_ng = 0
            for i, s in enumerate(sessions, 1):
                try:
                    dt_obj = datetime.strptime(s["started_at"], "%Y-%m-%d %H:%M:%S")
                    date_str = dt_obj.strftime("%Y-%m-%d")
                    time_str = dt_obj.strftime("%H:%M:%S")
                except (ValueError, KeyError):
                    date_str = str(s.get("started_at", ""))[:10]
                    time_str = str(s.get("started_at", ""))[11:19] if len(str(s.get("started_at", ""))) >= 19 else ""

                ok = s.get("ok_count", 0)
                ng = s.get("ng_count", 0)
                total_ok += ok
                total_ng += ng
                rate = ok / (ok + ng) * 100 if (ok + ng) > 0 else 0
                result = s.get("overall_result", "")

                row_data = [s.get("session_id", i), date_str, time_str,
                            s.get("model_name", ""), s.get("operator_name", ""),
                            ok, ng, f"{rate:.1f}%", result]
                for col, val in enumerate(row_data, 1):
                    ExcelExporter._data_cell(ws_sum, i + 3, col, val, result)

            # Totals row
            total_rate = total_ok / (total_ok + total_ng) * 100 if (total_ok + total_ng) > 0 else 0
            totals_row = len(sessions) + 4
            ws_sum.cell(row=totals_row, column=1, value="TOTALS").font = Font(bold=True)
            ws_sum.cell(row=totals_row, column=6, value=total_ok).font = Font(bold=True)
            ws_sum.cell(row=totals_row, column=7, value=total_ng).font = Font(bold=True)
            ws_sum.cell(row=totals_row, column=8, value=f"{total_rate:.1f}%").font = Font(bold=True)

            for col_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
                ws_sum.column_dimensions[col_letter].width = 14

            # ── Sheet 2: All Results ──
            ws_all = wb.create_sheet("All Results")
            res_headers = ["Session#", "Date", "Time", "Module", "Parameter",
                           "Measured", "Min", "Max", "User", "Result"]
            ExcelExporter._header_row(ws_all, 1, res_headers)

            for i, r in enumerate(all_results, 2):
                try:
                    dt_obj = datetime.strptime(r.get("started_at", ""), "%Y-%m-%d %H:%M:%S")
                    date_str = dt_obj.strftime("%Y-%m-%d")
                    time_str = dt_obj.strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    date_str = str(r.get("started_at", ""))[:10]
                    time_str = str(r.get("started_at", ""))[11:19] if len(str(r.get("started_at", ""))) >= 19 else ""

                row_data = [
                    r.get("session_id", ""), date_str, time_str,
                    r.get("group_name", ""), r.get("display_name", ""),
                    _fmt_meas(r, "measured_value"), _fmt_meas(r, "limit_min"),
                    _fmt_meas(r, "limit_max"), r.get("operator_name", ""),
                    _row_result_display(r)
                ]
                result = _row_result_display(r)
                for col, val in enumerate(row_data, 1):
                    ExcelExporter._data_cell(ws_all, i, col, val, result)

            for col_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']:
                ws_all.column_dimensions[col_letter].width = 14

            # ── Sheet 3: Failures Only ──
            failures = [r for r in all_results if r.get("result") == "FAIL"]
            ws_fail = wb.create_sheet("Failures")
            ExcelExporter._header_row(ws_fail, 1, res_headers)

            for i, r in enumerate(failures, 2):
                try:
                    dt_obj = datetime.strptime(r.get("started_at", ""), "%Y-%m-%d %H:%M:%S")
                    date_str = dt_obj.strftime("%Y-%m-%d")
                    time_str = dt_obj.strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    date_str = str(r.get("started_at", ""))[:10]
                    time_str = str(r.get("started_at", ""))[11:19] if len(str(r.get("started_at", ""))) >= 19 else ""

                row_data = [
                    r.get("session_id", ""), date_str, time_str,
                    r.get("group_name", ""), r.get("display_name", ""),
                    _fmt_meas(r, "measured_value"), _fmt_meas(r, "limit_min"),
                    _fmt_meas(r, "limit_max"), r.get("operator_name", ""), "FAIL"
                ]
                for col, val in enumerate(row_data, 1):
                    ExcelExporter._data_cell(ws_fail, i, col, val, "FAIL")

            for col_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']:
                ws_fail.column_dimensions[col_letter].width = 14

            wb.save(file_path)
            return f"Success: Exported to {file_path}"
        except Exception as e:
            logger.error(f"Bulk Excel export error: {e}")
            return f"Error: {str(e)}"


# ─── PDF formatting helpers & numbered canvas ───────────────────────────

NAVY_RGB = colors.Color(30/255, 45/255, 74/255)
WHITE_RGB = colors.white

BADGE_STYLES = {
    "PASS": (ParagraphStyle('BadgePass', fontSize=7, leading=9,
                            textColor=colors.Color(6/255, 95/255, 70/255),
                            backColor=colors.Color(209/255, 250/255, 229/255),
                            borderPadding=(2, 5), alignment=1)),
    "FAIL": (ParagraphStyle('BadgeFail', fontSize=7, leading=9,
                            textColor=colors.Color(153/255, 27/255, 27/255),
                            backColor=colors.Color(254/255, 226/255, 226/255),
                            borderPadding=(2, 5), alignment=1)),
    "PENDING": (ParagraphStyle('BadgePending', fontSize=7, leading=9,
                               textColor=colors.Color(146/255, 64/255, 14/255),
                               backColor=colors.Color(254/255, 243/255, 199/255),
                               borderPadding=(2, 5), alignment=1)),
    "BYPASS": (ParagraphStyle('BadgeBypass', fontSize=7, leading=9,
                              textColor=colors.Color(30/255, 64/255, 175/255),
                              backColor=colors.Color(219/255, 234/255, 254/255),
                              borderPadding=(2, 5), alignment=1)),
    "RUNNING": (ParagraphStyle('BadgeRunning', fontSize=7, leading=9,
                               textColor=colors.Color(120/255, 129/255, 141/255),
                               backColor=colors.Color(203/255, 213/255, 225/255),
                               borderPadding=(2, 5), alignment=1)),
    "N/A": (ParagraphStyle('BadgeNa', fontSize=7, leading=9,
                           textColor=colors.Color(75/255, 85/255, 99/255),
                           backColor=colors.Color(229/255, 231/255, 235/255),
                           borderPadding=(2, 5), alignment=1)),
}


def _badge_pdf(text: str) -> Paragraph:
    """Returns a colored pill-badge Paragraph for a PASS/FAIL/PENDING/N/A status."""
    key = str(text).strip().upper()
    style = BADGE_STYLES.get(key, BADGE_STYLES["PENDING"])
    return Paragraph(key, style)


def _row_result_display(row: dict) -> str:
    """Map a stored result row to its display status (PENDING+zero limits → N/A)."""
    result = str(row.get("result", "")).strip().upper()
    if result == "PENDING":
        try:
            lo = float(row.get("limit_min", 0.0))
            hi = float(row.get("limit_max", 0.0))
        except (TypeError, ValueError):
            lo = hi = 0.0
        if lo == 0.0 and hi == 0.0:
            return "N/A"
    return result


def _fmt_num(value, decimals: int = 2) -> str:
    """Format a number with comma grouping, e.g. 4540200 -> 4,540,200.00."""
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return str(value)
    if fv == int(fv) and decimals == 0:
        return f"{int(fv):,}"
    return f"{fv:,.{decimals}f}"


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return f"{value}%"


def _fmt_meas(row: dict, key: str, decimals: int = 2) -> str:
    """Format a numeric value with its engineering unit (from register library)."""
    num = _fmt_num(row.get(key, 0), decimals)
    unit = str(row.get("unit", "") or "").strip()
    return f"{num} {unit}".strip()


class _NumberedCanvas(_pdf_canvas.Canvas):
    """Canvas that draws a header and 'Page X of Y' footer on every page."""

    def __init__(self, *args, **kwargs):
        self._saved_page_states = []
        self._doc_title = kwargs.pop("doc_title", "PRODUCTION REPORT")
        self._doc_range = kwargs.pop("doc_range", "")
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_decoration(total)
            super().showPage()
        super().save()

    def _draw_page_decoration(self, total_pages: int) -> None:
        w, h = A4

        header_y = h - 14
        self.setStrokeColor(NAVY_RGB)
        self.setLineWidth(1.2)
        self.line(30, page_y(header_y, h), w - 30, page_y(header_y, h))

        self.setFillColor(NAVY_RGB)
        self.setFont("Helvetica-Bold", 8)
        self.drawString(30, page_y(header_y - 4, h), self._doc_title)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawRightString(w - 30, page_y(header_y - 4, h), self._doc_range)

        footer_y = 28
        self.setFillColor(colors.grey)
        self.setFont("Helvetica", 7.5)
        self.drawString(30, footer_y, "Confidential — Internal Quality Document")
        self.drawRightString(w - 30, footer_y, f"Page {self._pageNumber} of {total_pages}")

        self.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        self.setLineWidth(0.6)
        self.line(30, page_y(footer_y + 8, h), w - 30, page_y(footer_y + 8, h))


def page_y(y_from_top, page_h):
    """Convert a y measured from top into bottom-relative for reportlab canvas."""
    return page_h - y_from_top


class PDFExporter:
    """Static methods for PDF export — single session and bulk."""

    @staticmethod
    def export_session(file_path: str, data: Dict[str, Any]) -> str:
        """Export a single session as a PDF test certificate."""
        if not SimpleDocTemplate:
            return "Error: reportlab library not installed."

        try:
            doc = SimpleDocTemplate(file_path, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            session = data["session"]
            title_style = ParagraphStyle(
                'CertTitle', parent=styles['Heading1'],
                alignment=1, textColor=colors.white,
                backColor=colors.Color(30/255, 45/255, 74/255),
                borderPadding=10
            )
            story.append(Paragraph(
                f"TEST CERTIFICATE — SESSION #{session.get('id', '')}", title_style))
            story.append(Spacer(1, 15))

            meta = [
                ["Model:", session.get("model_name", "")],
                ["Date:", session.get("started_at", "")],
                ["Operator:", session.get("operator_name", "")],
                ["Overall Result:", session.get("overall_result", "")]
            ]
            t_meta = Table(meta, colWidths=[100, 300])
            story.append(t_meta)
            story.append(Spacer(1, 20))

            table_data = [["Module", "Parameter", "Measured", "Min", "Max", "Result"]]
            for grp, results in data.get("results", {}).items():
                for r in results:
                    table_data.append([
                        grp, r.get("display_name", ""),
                        _fmt_meas(r, "measured_value"),
                        _fmt_meas(r, "limit_min"),
                        _fmt_meas(r, "limit_max"),
                        r.get("result", "")
                    ])

            t_results = Table(table_data, colWidths=[80, 120, 70, 60, 60, 60])
            t_results.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(30/255, 45/255, 74/255)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
            ]))
            story.append(t_results)

            doc.build(story)
            return f"Success: Exported to {file_path}"
        except Exception as e:
            logger.error(f"PDF export error: {e}")
            return f"Error: {str(e)}"

    @staticmethod
    def export_bulk(file_path: str, data: Dict[str, Any]) -> str:
        """
        Bulk PDF: header + KPI stats + summary table + compact multi-session detail.
        Produces a dense, executive-style report of 4-6 pages for ~20 sessions.
        data = {"sessions": [...], "results": [...], "generated_at": "..."}
        """
        if not SimpleDocTemplate:
            return "Error: reportlab library not installed."

        try:
            sessions = data.get("sessions", [])
            all_results = data.get("results", [])
            generated = data.get("generated_at", "")
            date_from = data.get("date_from", "")
            date_to = data.get("date_to", "")

            range_str = f"{date_from} — {date_to}" if (date_from and date_to) else generated

            doc = SimpleDocTemplate(
                file_path, pagesize=A4,
                rightMargin=20, leftMargin=20,
                topMargin=40, bottomMargin=40
            )
            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle(
                'ReportTitle', parent=styles['Title'],
                fontSize=20, leading=24, textColor=WHITE_RGB,
                backColor=NAVY_RGB, borderPadding=(12, 14)
            )
            story.append(Paragraph("PRODUCTION REPORT", title_style))
            story.append(Spacer(1, 6))

            # ── Totals ──
            total_ok = sum(s.get("ok_count", 0) for s in sessions)
            total_ng = sum(s.get("ng_count", 0) for s in sessions)
            total_sessions = len(sessions)
            total_tested = total_ok + total_ng
            total_rate = total_ok / total_tested * 100 if total_tested > 0 else 0

            # ── KPI Cards ──
            def _kpi_card(label, value, value_color, bg_color):
                inner = Table(
                    [[Paragraph(f"<b>{label}</b>", ParagraphStyle(
                        'kplb', fontSize=7, textColor=colors.Color(100/255, 116/255, 139/255)))],
                     [Paragraph(f"<b>{value}</b>", ParagraphStyle(
                         'kpv', fontSize=15, leading=18, textColor=value_color))]],
                    colWidths=[120]
                )
                inner.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ]))
                wrapper = Table([[inner]], colWidths=[120])
                wrapper.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                    ('BOX', (0, 0), (-1, -1), 0.75, colors.Color(0.75, 0.78, 0.82)),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                return wrapper

            green_bg = colors.Color(240/255, 253/255, 244/255)
            red_bg = colors.Color(254/255, 242/255, 242/255)
            blue_bg = colors.Color(239/255, 246/255, 255/255)
            amber_bg = colors.Color(255/255, 251/255, 235/255)

            kpis = Table([
                [_kpi_card("TOTAL SESSIONS", str(total_sessions), NAVY_RGB, blue_bg),
                 _kpi_card("TOTAL OK", str(total_ok), colors.Color(5/255, 120/255, 60/255), green_bg),
                 _kpi_card("TOTAL NG", str(total_ng), colors.Color(190/255, 18/255, 60/255), red_bg),
                 _kpi_card("PASS RATE", _fmt_pct(total_rate), colors.Color(180/255, 83/255, 9/255), amber_bg)]
            ], colWidths=[128, 128, 128, 128])
            kpis.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            story.append(kpis)
            story.append(Spacer(1, 6))

            # ── Session Summary table ──
            story.append(Paragraph("Session Summary", styles['Heading2']))
            story.append(Spacer(1, 6))
            sum_headers = ["#", "Date", "Time", "Model", "OK", "NG", "Pass%", "Result"]
            sum_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('hdr', fontSize=7.5,
                                                                  textColor=WHITE_RGB)) for h in sum_headers]]
            for s in sessions:
                try:
                    dt_obj = datetime.strptime(s["started_at"], "%Y-%m-%d %H:%M:%S")
                    date_str = dt_obj.strftime("%Y-%m-%d")
                    time_str = dt_obj.strftime("%H:%M:%S")
                except (ValueError, KeyError):
                    date_str = str(s.get("started_at", ""))[:10]
                    time_str = str(s.get("started_at", ""))[11:19] if len(str(s.get("started_at", ""))) >= 19 else ""
                ok = s.get("ok_count", 0)
                ng = s.get("ng_count", 0)
                rate = ok / (ok + ng) * 100 if (ok + ng) > 0 else 0
                sum_data.append([
                    Paragraph(str(s.get("session_id", "")), ParagraphStyle('c', fontSize=7)),
                    Paragraph(date_str, ParagraphStyle('c', fontSize=7)),
                    Paragraph(time_str, ParagraphStyle('c', fontSize=7)),
                    Paragraph(str(s.get("model_name", "")), ParagraphStyle('c', fontSize=7)),
                    Paragraph(str(ok), ParagraphStyle('c', fontSize=7)),
                    Paragraph(str(ng), ParagraphStyle('c', fontSize=7)),
                    Paragraph(_fmt_pct(rate), ParagraphStyle('c', fontSize=7, alignment=1)),
                    _badge_pdf(s.get("overall_result", "")),
                ])
            t_sum = Table(sum_data, colWidths=[35, 62, 52, 70, 35, 35, 50, 60])
            t_sum.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), NAVY_RGB),
                ('TEXTCOLOR', (0, 0), (-1, 0), WHITE_RGB),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.87, 0.9)),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(t_sum)
            story.append(Spacer(1, 10))

            # ── Quality Alert / Exception summary (failed params) ──
            failures = [r for r in all_results if str(r.get("result", "")).strip().upper() == "FAIL"]
            if failures:
                story.append(Paragraph("Quality Alert — Failed Parameters", styles['Heading2']))
                story.append(Spacer(1, 6))
                fail_headers = ["Session", "Module", "Parameter", "Measured", "Min", "Max", "Result"]
                fail_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('hdr', fontSize=7.5,
                                                                      textColor=WHITE_RGB)) for h in fail_headers]]
                for r in failures:
                    fail_data.append([
                        Paragraph(str(r.get("session_id", "")), ParagraphStyle('c', fontSize=7)),
                        Paragraph(str(r.get("group_name", "")), ParagraphStyle('c', fontSize=7)),
                        Paragraph(str(r.get("display_name", "")), ParagraphStyle('c', fontSize=7)),
                        Paragraph(_fmt_meas(r, "measured_value"), ParagraphStyle('c', fontSize=7)),
                        Paragraph(_fmt_meas(r, "limit_min"), ParagraphStyle('c', fontSize=7)),
                        Paragraph(_fmt_meas(r, "limit_max"), ParagraphStyle('c', fontSize=7)),
                        _badge_pdf("FAIL"),
                    ])
                t_fail = Table(fail_data, colWidths=[45, 60, 100, 70, 60, 60, 55])
                t_fail.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(153/255, 27/255, 27/255)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), WHITE_RGB),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.9, 0.9, 0.9)),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(KeepTogether([t_fail]))
                story.append(Spacer(1, 10))

            # ── Per-session detail (compact, multi per page) ──
            session_ids = []
            for r in all_results:
                sid = r.get("session_id")
                if sid and sid not in session_ids:
                    session_ids.append(sid)

            for i, sid in enumerate(session_ids):
                sess_results = [r for r in all_results if r.get("session_id") == sid]
                if not sess_results:
                    continue

                first = sess_results[0]
                heading = Paragraph(
                    f"Session #{sid} — {first.get('started_at', '')}",
                    ParagraphStyle('SessHead', parent=styles['Heading4'], fontSize=9.5,
                                   textColor=NAVY_RGB, spaceAfter=3)
                )
                block = [heading, Spacer(1, 2)]

                detail_headers = ["Module", "Parameter", "Measured", "Min", "Max", "User", "Result"]
                detail_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('hdr', fontSize=7,
                                                                         textColor=WHITE_RGB)) for h in detail_headers]]
                for r in sess_results:
                    res_label = _row_result_display(r)
                    detail_data.append([
                        Paragraph(str(r.get("group_name", "")), ParagraphStyle('c', fontSize=6.8)),
                        Paragraph(str(r.get("display_name", "")), ParagraphStyle('c', fontSize=6.8)),
                        Paragraph(_fmt_meas(r, "measured_value"), ParagraphStyle('c', fontSize=6.8)),
                        Paragraph(_fmt_meas(r, "limit_min"), ParagraphStyle('c', fontSize=6.8)),
                        Paragraph(_fmt_meas(r, "limit_max"), ParagraphStyle('c', fontSize=6.8)),
                        Paragraph(str(r.get("operator_name", "")), ParagraphStyle('c', fontSize=6.8)),
                        _badge_pdf(res_label),
                    ])

                t_detail = Table(detail_data, colWidths=[62, 95, 70, 60, 60, 60, 55])
                t_detail.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), NAVY_RGB),
                    ('TEXTCOLOR', (0, 0), (-1, 0), WHITE_RGB),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.88, 0.9, 0.92)),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.965, 0.97, 0.98)]),
                ]))

                # Green/red left-border hint for result column
                for idx, row_detail in enumerate(sess_results, start=1):
                    res = str(row_detail.get("result", "")).strip().upper()
                    if res == "PASS":
                        t_detail.setStyle(TableStyle([
                            ('BACKGROUND', (6, idx), (6, idx), colors.Color(209/255, 250/255, 229/255)),
                            ('ALIGN', (6, idx), (6, idx), 'CENTER'),
                        ]))
                    elif res == "FAIL":
                        t_detail.setStyle(TableStyle([
                            ('BACKGROUND', (6, idx), (6, idx), colors.Color(254/255, 226/255, 226/255)),
                            ('ALIGN', (6, idx), (6, idx), 'CENTER'),
                        ]))

                block.append(t_detail)
                # Don't force every session onto its own page — let them flow and keep together.
                if i < len(session_ids) - 1:
                    story.append(KeepTogether(block))
                    story.append(Spacer(1, 8))
                else:
                    story.append(KeepTogether(block))

            doc.build(
                story,
                canvasmaker=lambda *args, **kw: _NumberedCanvas(
                    *args,
                    doc_title="PRODUCTION REPORT",
                    doc_range=range_str,
                    **kw,
                )
            )
            return f"Success: Exported to {file_path}"
        except Exception as e:
            logger.error(f"Bulk PDF export error: {e}")
            return f"Error: {str(e)}"
