"""
tests/test_exporters.py
Unit tests for ExcelExporter and PDFExporter logic using a temporary database.
"""

import os
import pytest
from openpyxl import load_workbook
from src.db.database import Database
from src.db.session_repo import SessionRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.report_repo import ReportRepository
from src.reports.excel_exporter import ExcelExporter
from src.reports.pdf_exporter import PDFExporter

@pytest.fixture
def populated_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    db.initialize()
    
    session_repo = SessionRepository(db)
    model_repo = ModelRepository(db)
    param_repo = ParameterRepository(db)
    report_repo = ReportRepository(db)
    
    # 1. Create a model
    model_id = model_repo.create_model("MI-7646AZ", "Test Desc", "M123")
    
    # 2. Add parameters
    param_repo.add_parameter(model_id, "Volt", "Output Voltage", "V", 0, 10, 11, 12, 13, 1)
    param_repo.add_parameter(model_id, "Curr", "Output Current", "A", 1, 14, 15, 16, 17, 1)
    params = param_repo.get_model_parameters(model_id)
    
    # 3. Create 5 sessions
    for i in range(5):
        sid = session_repo.open_session(model_id, 1)
        is_failing = (i == 4) # Last one fails
        
        for p in params:
            result = "FAIL" if is_failing else "PASS"
            session_repo.record_result(
                sid, p["id"], p["param_name"],
                5.0, 4.0, 6.0, result, 0.0
            )
            
        ok = 0 if is_failing else 1
        ng = 1 if is_failing else 0
        session_repo.close_session(sid, ok, ng, 1)
        
    return {
        "db": db, 
        "report_repo": report_repo, 
        "model_id": model_id,
        "session_ids": [1, 2, 3, 4, 5]
    }

class TestExcelExporter:
    def test_shift_report_creates_file(self, tmp_path, populated_db):
        exporter = ExcelExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "shift_report.xlsx")
        
        result = exporter.generate_shift_report(out_path, model_id=populated_db["model_id"])
        
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_shift_report_has_3_sheets(self, tmp_path, populated_db):
        exporter = ExcelExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "shift_report.xlsx")
        exporter.generate_shift_report(out_path, model_id=populated_db["model_id"])
        
        wb = load_workbook(out_path)
        assert len(wb.sheetnames) == 3
        assert "Summary" in wb.sheetnames
        assert "Parameter Analysis" in wb.sheetnames
        assert "Alarm Log" in wb.sheetnames

    def test_summary_sheet_row_count(self, tmp_path, populated_db):
        exporter = ExcelExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "shift_report.xlsx")
        exporter.generate_shift_report(out_path, model_id=populated_db["model_id"])
        
        wb = load_workbook(out_path)
        ws = wb["Summary"]
        # Header (1), Subheader (2), Empty (3), Headers (4), 5 data rows (5-9), Total (10)
        # Note: My implementation adds a spacer row and headers on row 4.
        # Let's count non-empty rows in column B (Session ID)
        sessions_found = 0
        for r in range(5, 20):
            if ws.cell(row=r, column=2).value:
                sessions_found += 1
        assert sessions_found == 5

    def test_pass_pct_cell_green_when_100(self, tmp_path, populated_db):
        exporter = ExcelExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "shift_report.xlsx")
        exporter.generate_shift_report(out_path, model_id=populated_db["model_id"])
        
        wb = load_workbook(out_path)
        ws = wb["Summary"]
        # First data row is row 5. Pass% is col 10 (J).
        # Session 1 was 100% OK.
        fill = ws["J5"].fill
        assert fill.start_color.index == "001A6B3A" # PASS_FILL

    def test_illegal_chars_handled(self, tmp_path, populated_db):
        # Insert a session comment with null byte
        db = populated_db["db"]
        db.execute("INSERT INTO session_comments (session_id, operator_id, comment) VALUES (1, 1, 'Bad\x00data')")
        
        exporter = ExcelExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "session_illegal.xlsx")
        
        # This should NOT raise IllegalCharacterError
        exporter.generate_session_report(out_path, session_id=1)
        assert os.path.exists(out_path)

class TestPDFExporter:
    def test_certificate_creates_file(self, tmp_path, populated_db):
        exporter = PDFExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "cert.pdf")
        
        result = exporter.generate_test_certificate(out_path, session_id=1)
        
        assert os.path.exists(result)
        assert os.path.getsize(result) > 5000 # Minimum size for valid certificate

    def test_certificate_valid_pdf_header(self, tmp_path, populated_db):
        exporter = PDFExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "cert.pdf")
        exporter.generate_test_certificate(out_path, session_id=1)
        
        with open(out_path, 'rb') as f:
            header = f.read(4)
        assert header == b'%PDF'

    def test_fail_session_creates_file(self, tmp_path, populated_db):
        exporter = PDFExporter(populated_db["report_repo"])
        out_path = str(tmp_path / "fail_cert.pdf")
        
        # Session 5 was failing
        result = exporter.generate_test_certificate(out_path, session_id=5)
        assert os.path.exists(result)
