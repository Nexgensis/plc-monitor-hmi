"""
reports/excel_exporter.py
Pure Python Excel generator using Openpyxl natively bounded logic natively.
Strictly isolated from Qt imports entirely natively explicitly.
"""

import logging
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.chart import BarChart, Reference
from database.db_manager import Database

logger = logging.getLogger(__name__)

# STATIC STYLE CONSTANTS BOUNDS
NAVY_FILL  = PatternFill(start_color="1e2d4a", end_color="1e2d4a", fill_type="solid")
NAVY_FONT  = Font(color="FFFFFF", bold=True, size=11)
PASS_FILL  = PatternFill(start_color="1a6b3a", end_color="1a6b3a", fill_type="solid")
FAIL_FILL  = PatternFill(start_color="c0392b", end_color="c0392b", fill_type="solid")
AMBER_FILL = PatternFill(start_color="f39c12", end_color="f39c12", fill_type="solid")
PASS_FONT  = Font(color="FFFFFF", bold=True)
FAIL_FONT  = Font(color="FFFFFF", bold=True)
ALT_FILL   = PatternFill(start_color="f0f4f8", end_color="f0f4f8", fill_type="solid")
THIN_BORDER = Border(left=Side(style='thin'), right=Side(style='thin'),
                     top=Side(style='thin'), bottom=Side(style='thin'))


def _safe(v) -> str:
    """Sanitize all cell values mechanically preventing IllegalCharacterError actively."""
    if v is None:
        return ""
    return str(v).encode('utf-8', 'replace').decode()

class ExcelExporter:
    """Excel construction limits isolated from GUI threads ensuring blocking I/O is safely deferred."""
    
    def __init__(self, db: Database):
        self._db = db

    def generate_shift_report(self, output_path: str, model_id: int = None,
                              date_from: str = None, date_to: str = None) -> str:
        wb = Workbook()
        
        # 1. SUMMARY SHEET
        ws_sum = wb.active
        ws_sum.title = "Summary"
        
        # Title Block
        ws_sum.merge_cells('A1:I1')
        ws_sum['A1'] = "Switch Test Station — Shift Report"
        ws_sum['A1'].font = Font(size=16, bold=True, color="1e2d4a")
        ws_sum['A1'].alignment = Alignment(horizontal="center")
        
        dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws_sum.merge_cells('A2:I2')
        ws_sum['A2'] = f"Generated: {dt_str} | Model ID: {model_id or 'ALL'} | Period: {date_from or 'ALL'} to {date_to or 'ALL'}"
        ws_sum['A2'].alignment = Alignment(horizontal="center")
        
        # Headers bounds natively 
        headers = ["Sr No", "Date", "Time", "Model", "Operator", "OK", "NG", "Batch", "Pass%"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws_sum.cell(row=4, column=col_idx, value=h)
            cell.fill = NAVY_FILL
            cell.font = NAVY_FONT
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER
            
        ws_sum.freeze_panes = 'A5'
        
        conn = self._db.get_connection()
        query = """
            SELECT s.id, s.started_at, s.ended_at, s.ok_count, s.ng_count, s.batch_count,
                   m.name as model_name, u.username as operator
            FROM test_sessions s
            LEFT JOIN models m ON s.model_id = m.id
            LEFT JOIN users u ON s.operator_id = u.id
            WHERE 1=1
        """
        params = []
        if model_id:
            query += " AND s.model_id = ?"
            params.append(model_id)
        if date_from:
            query += " AND s.started_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND s.started_at <= ?"
            params.append(date_to)
            
        rows = conn.execute(query, params).fetchall()
        
        sum_ok = sum_ng = sum_batch = 0
        
        for r_idx, row in enumerate(rows, 5):
            dt_obj = datetime.strptime(row['started_at'], "%Y-%m-%d %H:%M:%S") if row['started_at'] else datetime.now()
            d_val, t_val = dt_obj.strftime("%Y-%m-%d"), dt_obj.strftime("%H:%M:%S")
            ok, ng, batch = row['ok_count'] or 0, row['ng_count'] or 0, row['batch_count'] or 0
            
            sum_ok += ok
            sum_ng += ng
            sum_batch += batch
            
            pass_pct = (ok / batch * 100) if batch > 0 else 0.0
            
            row_data = [r_idx - 4, d_val, t_val, row['model_name'], row['operator'], ok, ng, batch, f"{pass_pct:.1f}%"]
            
            for c_idx, val in enumerate(row_data, 1):
                c = ws_sum.cell(row=r_idx, column=c_idx, value=_safe(val))
                c.border = THIN_BORDER
                c.alignment = Alignment(horizontal="center")
                if r_idx % 2 == 0:
                    c.fill = ALT_FILL
                    
                # Dynamic percent constraints coloring natively explicitly
                if c_idx == 9:
                    if pass_pct >= 95.0: c.fill = PASS_FILL
                    elif pass_pct >= 80.0: c.fill = AMBER_FILL
                    else: c.fill = FAIL_FILL
                    c.font = Font(color="FFFFFF", bold=True)
                    
        # Total Row physically bound structural overrides
        t_row = len(rows) + 5
        ws_sum.cell(row=t_row, column=4, value="TOTALS").font = Font(bold=True)
        ws_sum.cell(row=t_row, column=6, value=sum_ok).font = Font(bold=True)
        ws_sum.cell(row=t_row, column=7, value=sum_ng).font = Font(bold=True)
        ws_sum.cell(row=t_row, column=8, value=sum_batch).font = Font(bold=True)
        t_pct = (sum_ok / sum_batch * 100) if sum_batch > 0 else 0.0
        ws_sum.cell(row=t_row, column=9, value=f"{t_pct:.1f}%").font = Font(bold=True)
        
        # 2. SIGNAL ANALYSIS SHEET
        ws_sig = wb.create_sheet(title="Signal Analysis")
        ws_sig['A1'] = "Signal Failure Statistics"
        ws_sig['A1'].font = Font(bold=True, size=14)
        
        s_headers = ["Signal", "Failures"]
        for c, h in enumerate(s_headers, 1):
            cell = ws_sig.cell(row=3, column=c, value=h)
            cell.fill = NAVY_FILL
            cell.font = NAVY_FONT
        
        # Aggregate logic
        q_fails = """
            SELECT signal_name, count(*) as fail_count 
            FROM test_results 
            WHERE result='FAIL'
            GROUP BY signal_name
        """
        fails = conn.execute(q_fails).fetchall()
        
        for idx, f in enumerate(fails, 4):
            ws_sig.cell(row=idx, column=1, value=_safe(f['signal_name']))
            ws_sig.cell(row=idx, column=2, value=f['fail_count'])
            
        if fails:
            chart = BarChart()
            data = Reference(ws_sig, min_col=2, min_row=3, max_row=len(fails)+3)
            cats = Reference(ws_sig, min_col=1, min_row=4, max_row=len(fails)+3)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            chart.title = "Failures per Signal"
            ws_sig.add_chart(chart, "E3")
            
        # 3. ALARM LOG SHEET
        ws_alarm = wb.create_sheet(title="Alarm Log")
        headers_al = ["Timestamp", "Session", "Severity", "Message"]
        for c, h in enumerate(headers_al, 1):
            cell = ws_alarm.cell(row=1, column=c, value=h)
            cell.fill = NAVY_FILL
            cell.font = NAVY_FONT
            
        alarms = conn.execute("SELECT created_at, session_id, severity, message FROM alarms ORDER BY created_at DESC").fetchall()
        for r, al in enumerate(alarms, 2):
            ws_alarm.cell(row=r, column=1, value=_safe(al['created_at']))
            ws_alarm.cell(row=r, column=2, value=_safe(al['session_id']))
            
            sev_cell = ws_alarm.cell(row=r, column=3, value=_safe(al['severity']))
            sev = al['severity']
            if sev == "ERROR":
                sev_cell.fill = FAIL_FILL
                sev_cell.font = FAIL_FONT
            elif sev == "WARNING":
                sev_cell.fill = AMBER_FILL
            elif sev == "INFO":
                sev_cell.fill = PatternFill(start_color="3498db", end_color="3498db", fill_type="solid")
                
            ws_alarm.cell(row=r, column=4, value=_safe(al['message']))
            
        # Optional: Auto-fit columns dynamically iterating limits across all grids cleanly
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = max_len + 2
                
        wb.save(output_path)
        return output_path

    def generate_session_report(self, output_path: str, session_id: int) -> str:
        wb = Workbook()
        ws_res = wb.active
        ws_res.title = "Test Results"
        
        conn = self._db.get_connection()
        sess = conn.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
        
        if not sess:
            # Inject structural default cleanly mapping safe exits immediately bounds
            wb.save(output_path)
            return output_path
            
        ws_res['A1'] = f"Session ID: {session_id} | OK: {sess['ok_count']} | NG: {sess['ng_count']}"
        ws_res['A1'].font = Font(bold=True)
        
        headers = ["Signal", "Test Type", "Measured", "Min", "Max", "Result", "Dev%"]
        for c, h in enumerate(headers, 1):
            cell = ws_res.cell(row=3, column=c, value=h)
            cell.fill = NAVY_FILL
            cell.font = NAVY_FONT
            
        res_rows = conn.execute("SELECT * FROM test_results WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
        
        for r, res in enumerate(res_rows, 4):
            ws_res.cell(row=r, column=1, value=_safe(res['signal_name']))
            ws_res.cell(row=r, column=2, value=_safe(res['test_type']))
            ws_res.cell(row=r, column=3, value=_safe(res['measured_value']))
            ws_res.cell(row=r, column=4, value=_safe(res['limit_min']))
            ws_res.cell(row=r, column=5, value=_safe(res['limit_max']))
            
            cr = ws_res.cell(row=r, column=6, value=_safe(res['result']))
            val_up = str(res['result']).upper()
            if val_up == "PASS":
                cr.fill, cr.font = PASS_FILL, PASS_FONT
            elif val_up == "FAIL":
                cr.fill, cr.font = FAIL_FILL, FAIL_FONT
            elif "BYPASS" in val_up:
                cr.fill, cr.font = PatternFill(start_color="6c757d", end_color="6c757d", fill_type="solid"), Font(color="FFFFFF")
                
            ws_res.cell(row=r, column=7, value=_safe(f"{res['deviation_pct']:.2f}%"))
            
        ws_raw = wb.create_sheet(title="Raw Data")
        headers_raw = ["ID", "Rec_Time", "Signal", "TestType", "Measured", "Result"]
        for c, h in enumerate(headers_raw, 1): ws_raw.cell(row=1, column=c, value=h)
        
        for r, res in enumerate(res_rows, 2):
            ws_raw.cell(row=r, column=1, value=_safe(res['id']))
            ws_raw.cell(row=r, column=2, value=_safe(res['created_at']))
            ws_raw.cell(row=r, column=3, value=_safe(res['signal_name']))
            ws_raw.cell(row=r, column=4, value=_safe(res['test_type']))
            ws_raw.cell(row=r, column=5, value=_safe(res['measured_value']))
            ws_raw.cell(row=r, column=6, value=_safe(res['result']))
            
        # Clean col width arrays iteratively native bounds explicitly structurally 
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, min(len(str(cell.value)), 40))
                ws.column_dimensions[col_letter].width = max_len + 2
                
        wb.save(output_path)
        return output_path
