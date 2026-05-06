"""
PDF certificate and summary generation using reportlab.
"""
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

class PDFExporter:
    NAVY = colors.Color(30/255, 45/255, 74/255)
    GREEN = colors.Color(209/255, 250/255, 229/255)
    RED = colors.Color(254/255, 226/255, 226/255)

    def __init__(self, report_repo):
        self.repo = report_repo

    def _safe(self, v) -> str:
        if v is None: return ""
        return str(v).encode('utf-8', 'replace').decode().strip()

    def generate_test_certificate(self, output_path: str, session_id: int) -> str:
        detail = self.repo.get_session_detail(session_id)
        if not detail: raise ValueError("Session not found")
        
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, textColor=colors.white, backColor=self.NAVY, borderPadding=10)
        story.append(Paragraph(f"TEST CERTIFICATE - SESSION #{session_id}", title_style))
        story.append(Spacer(1, 15))
        
        s = detail["session"]
        info_data = [
            ["Start Time:", self._safe(s["started_at"]), "OK Parts:", self._safe(s["ok_count"])],
            ["End Time:", self._safe(s["ended_at"]), "NG Parts:", self._safe(s["ng_count"])]
        ]
        info_table = Table(info_data, colWidths=[100, 150, 100, 150])
        info_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
            ('BACKGROUND', (2,0), (2,-1), colors.whitesmoke),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))
        
        data = [["Module", "Parameter", "Measured", "Min", "Max", "Result"]]
        t_style = [
            ('BACKGROUND', (0,0), (-1,0), self.NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')
        ]
        
        row_count = 1
        for mod, params in detail["results"].items():
            for p in params:
                res = p["result"]
                data.append([
                    self._safe(mod), self._safe(p["param_name"]), 
                    f"{p['measured_value']:.3f}", f"{p['limit_min']:.3f}", 
                    f"{p['limit_max']:.3f}", res
                ])
                if res == "PASS": t_style.append(('BACKGROUND', (5, row_count), (5, row_count), self.GREEN))
                elif res == "FAIL": t_style.append(('BACKGROUND', (5, row_count), (5, row_count), self.RED))
                row_count += 1
                
        table = Table(data, colWidths=[80, 120, 70, 70, 70, 70])
        table.setStyle(TableStyle(t_style))
        story.append(table)
        
        story.append(Spacer(1, 30))
        footer = Paragraph("Minda PLC Monitoring System — Automated Report Generation", styles['Italic'])
        story.append(footer)
        
        doc.build(story)
        return output_path

    def generate_shift_summary_pdf(self, output_path: str, model_id=None, date_from=None, date_to=None) -> str:
        sessions = self.repo.get_sessions_summary(model_id, date_from, date_to)
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, textColor=colors.white, backColor=self.NAVY, borderPadding=10)
        story.append(Paragraph("SHIFT SUMMARY REPORT", title_style))
        story.append(Spacer(1, 15))
        
        data = [["ID", "Date", "Model", "OK", "NG", "Pass%"]]
        for s in sessions:
            data.append([
                str(s["session_id"]), s["started_at"][:10], self._safe(s["model_name"]),
                str(s["ok_count"]), str(s["ng_count"]), f"{s['pass_rate_pct']:.1f}%"
            ])
            
        table = Table(data, colWidths=[50, 80, 150, 60, 60, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), self.NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
        ]))
        story.append(table)
        
        doc.build(story)
        return output_path
