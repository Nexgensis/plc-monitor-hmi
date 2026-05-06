"""
exporters.py — Universal PLC Monitor
Logic for exporting test session data to Excel and PDF formats.
Uses openpyxl for Excel and reportlab for PDF.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
except ImportError:
    openpyxl = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
except ImportError:
    SimpleDocTemplate = None


class ExcelExporter:
    @staticmethod
    def export_session(file_path: str, data: Dict[str, Any]) -> str:
        if not openpyxl:
            return "Error: openpyxl library not installed."
            
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Test Session"
            
            # Header
            ws["A1"] = "PLC MONITOR — TEST CERTIFICATE"
            ws["A1"].font = Font(bold=True, size=14)
            
            session = data["session"]
            ws["A3"] = "Model:"
            ws["B3"] = session["model_name"]
            ws["A4"] = "Date:"
            ws["B4"] = session["started_at"]
            ws["A5"] = "Operator:"
            ws["B5"] = session["operator_name"]
            ws["A6"] = "Overall Result:"
            ws["B6"] = session["overall_result"]
            
            # Results Table
            ws["A8"] = "Module"
            ws["B8"] = "Parameter"
            ws["C8"] = "Value"
            ws["D8"] = "Result"
            for cell in ["A8", "B8", "C8", "D8"]:
                ws[cell].font = Font(bold=True)
                ws[cell].fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            
            row = 9
            for grp, results in data["results"].items():
                for r in results:
                    ws.cell(row=row, column=1, value=grp)
                    ws.cell(row=row, column=2, value=r["display_name"])
                    ws.cell(row=row, column=3, value=r["measured_value"])
                    ws.cell(row=row, column=4, value=r["result"])
                    row += 1
            
            wb.save(file_path)
            return f"Success: Exported to {file_path}"
        except Exception as e:
            return f"Error: {str(e)}"


class PDFExporter:
    @staticmethod
    def export_session(file_path: str, data: Dict[str, Any]) -> str:
        if not SimpleDocTemplate:
            return "Error: reportlab library not installed."
            
        try:
            doc = SimpleDocTemplate(file_path, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            session = data["session"]
            story.append(Paragraph(f"Test Certificate: {session['model_name']}", styles['Title']))
            story.append(Spacer(1, 12))
            
            meta = [
                ["Date:", session["started_at"]],
                ["Operator:", session["operator_name"]],
                ["Overall Result:", session["overall_result"]]
            ]
            t_meta = Table(meta, colWidths=[100, 300])
            story.append(t_meta)
            story.append(Spacer(1, 20))
            
            # Results Table
            table_data = [["Module", "Parameter", "Value", "Result"]]
            for grp, results in data["results"].items():
                for r in results:
                    table_data.append([grp, r["display_name"], str(r["measured_value"]), r["result"]])
            
            t_results = Table(table_data, colWidths=[100, 150, 100, 100])
            t_results.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('ALIGN', (0,0), (-1,-1), 'CENTER')
            ]))
            story.append(t_results)
            
            doc.build(story)
            return f"Success: Exported to {file_path}"
        except Exception as e:
            return f"Error: {str(e)}"
