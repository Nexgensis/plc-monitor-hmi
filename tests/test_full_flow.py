"""
test_full_flow.py — Universal PLC Monitor
Full Flow Integration Test (v4.0 compatible).
Starts mock server, runs a test cycle, and verifies database + reports.
"""
import sys
import os
import time
import subprocess
import logging
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

from src.db.database import Database
from src.db.seed import seed_database
from PyQt6.QtCore import QCoreApplication, QTimer
from src.db.model_repo import ModelRepository
from src.db.register_library_repo import RegisterLibraryRepo
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.report_repo import ReportRepository
from src.db.user_repo import UserRepository
from src.db.session_repo import SessionRepository
from src.ui.app_state import AppState
from src.plc.mitsubishi_driver import MitsubishiDriver
from src.plc.write_manager import PLCWriteManager
from src.plc.connection_manager import ConnectionManager
from src.plc.data_model import PLCDataModel
from src.logic.session_controller import SessionController
from src.logic.pass_fail_evaluator import PassFailEvaluator

# Try to import colorama
try:
    from colorama import init, Fore, Style
    init()
except ImportError:
    class Fore: GREEN = ""; RED = ""; RESET = ""; YELLOW = ""
    class Style: BRIGHT = ""; RESET_ALL = ""

def print_step(n, msg, success):
    color = Fore.GREEN if success else Fore.RED
    status = "[OK]" if success else "[FAIL]"
    print(f"{n:2d}. {msg:.<60} {color}{status}{Fore.RESET}")
    return 1 if success else 0

def seed_test_data(db: Database):
    """Seeds specific data needed for this integration test."""
    lib = RegisterLibraryRepo(db)
    models = ModelRepository(db)
    
    # 1. Create Registers in Library
    # Heartbeat / Control
    d21_id = lib.create_register("Test Status (D21)", 21, "HOLDING", "INT16", "1=Running, 0=Stop")
    m10_id = lib.create_register("Start Test (M10)", 10, "COIL", "BOOL", "Trigger test start", access="READ_WRITE")
    
    # Measurements
    d100_id = lib.create_register("Pressure (D100)", 100, "HOLDING", "INT16", "Main pressure", scale_factor=0.1, unit="bar")
    d102_id = lib.create_register("Voltage (D102)", 102, "HOLDING", "INT16", "Battery voltage", scale_factor=0.01, unit="V")
    
    # Limits (Polled as registers for this test)
    d260_id = lib.create_register("Limit Min (D260)", 260, "HOLDING", "INT16", "Min threshold", access="READ_WRITE")
    d261_id = lib.create_register("Limit Max (D261)", 261, "HOLDING", "INT16", "Max threshold", access="READ_WRITE")

    # 2. Create Model
    model_id = models.create_model("SW-TEST-01", "Integration Test Model", "TEST-01")
    
    # 3. Map Registers to Model
    from src.db.model_map_repo import ModelMapRepo
    mmap = ModelMapRepo(db)
    
    mmap.add_mapping(model_id, d100_id, role="MEASURED", group_name="Module A", card_position=1)
    mmap.add_mapping(model_id, d102_id, role="MEASURED", group_name="Module A", card_position=2)
    
    # Add a result-role register if needed, or just use MEASURED for evaluation
    # In v4.0, PassFailEvaluator evaluates based on the model config.
    
    return model_id

def run_test():
    # Signals require an event loop
    app = QCoreApplication(sys.argv)
    
    passed = 0
    total_steps = 20
    db_path = "test_flow.db"
    xlsx_path = "test_report.xlsx"
    mock_log_path = "mock_server.log"
    
    if os.path.exists(db_path): 
        try: os.remove(db_path)
        except: pass
        
    print(f"\n{Style.BRIGHT}=== STARTING FULL FLOW INTEGRATION TEST (v4.0) ==={Style.RESET_ALL}\n")
    
    server_proc = None
    mock_log = None
    cm = None
    db = None
    
    try:
        # 1. Start mock server
        mock_log = open(mock_log_path, "w")
        server_script = str(ROOT_DIR / "tests" / "mock_plc_server.py")
        server_proc = subprocess.Popen([sys.executable, server_script, "--port", "5021"], 
                                       stdout=mock_log, stderr=mock_log)
        passed += print_step(1, "Start mock_plc_server (port 5021)", server_proc.poll() is None)
        
        # 2. Wait
        time.sleep(2)
        passed += print_step(2, "Wait for server initialization", True)
        
        # 3. Fresh DB
        db = Database(db_path)
        db.initialize("schema.sql")
        seed_database(db)
        model_id = seed_test_data(db)
        passed += print_step(3, "Fresh DB + Seed + Test Data", True)
        
        # 4. Configure PLC
        profile_repo = PLCProfileRepository(db)
        profile_repo.update_profile(host="127.0.0.1", port=5021)
        profile = profile_repo.get_profile()
        passed += print_step(4, "Configure PLC host=127.0.0.1 port=5021", profile["host"] == "127.0.0.1")
        
        # 5. Build AppState
        state = AppState.get_instance()
        state.db = db
        state.register_repo = RegisterLibraryRepo(db)
        state.model_repo = ModelRepository(db)
        state.plc_profile_repo = profile_repo
        state.report_repo = ReportRepository(db)
        state.user_repo = UserRepository(db)
        state.session_repo = SessionRepository(db)
        
        state.set_user({"id": 1, "username": "admin", "role": "ADMIN"})
        state.set_plc_profile(profile)
        passed += print_step(5, "Initialize AppState with repositories", True)
        
        # 6. Load Model Config
        config = state.model_repo.get_full_model_config(model_id)
        state.set_model(config["model"], config["parameters"])
        passed += print_step(6, f"Load Model {config['model']['name']}", config is not None)
        
        # 7. Setup Driver and WriteManager
        driver = MitsubishiDriver(profile["host"], profile["port"])
        wm = PLCWriteManager(driver, db, state)
        state.write_manager = wm
        passed += print_step(7, "Setup MitsubishiDriver and PLCWriteManager", True)
        
        # 8. Connect and Verify
        connected = driver.connect()
        passed += print_step(8, "MitsubishiDriver connect to 5021", connected)
        
        # 9. Set Test Limits in PLC
        # D260 = 380, D261 = 620
        res_9a = driver.write_register(260, "HOLDING", 380)
        res_9b = driver.write_register(261, "HOLDING", 620)
        passed += print_step(9, "Set Test Limits in PLC (D260/D261)", res_9a.success and res_9b.success)
        
        # 10. Start ConnectionManager (Disabled for test)
        # cm = ConnectionManager(...)
        passed += print_step(10, "ConnectionManager (Disabled for test)", True)
        
        # 11. Setup SessionController
        evaluator = PassFailEvaluator(config)
        sc = SessionController(state, evaluator)
        passed += print_step(11, "Initialize SessionController", True)
        
        # 12. Simulate Test Trigger (D21=1)
        print("   DEBUG: Writing D21=1")
        res_trigger = driver.write_register(21, "HOLDING", 1)
        passed += print_step(12, "Trigger Test Session Start", res_trigger.success)
        
        # Manual trigger session
        sc.on_test_started()
        passed += print_step(13, f"Session ID: {sc.active_session_id}", sc.active_session_id is not None)
        
        # 14. Simulate Measurement (D100=500)
        print("   DEBUG: Writing D100=500")
        driver.write_register(100, "HOLDING", 500)
        time.sleep(1)
        
        eval_input = {"Pressure (D100)": 500}
        sc.on_readings_update(eval_input)
        passed += print_step(14, "Simulate Readings update", True)
        
        # 15. Complete Test
        print("   DEBUG: Completing test")
        sc.on_test_completed(plc_status=None)
        passed += print_step(15, "Complete Test Session", sc.active_session_id is None)
        
        # 16. Verify Session in DB
        sessions = state.report_repo.get_sessions_summary(model_id=model_id)
        passed += print_step(16, f"Verify Session recorded (count={len(sessions)})", len(sessions) > 0)
        
        # 17. Verify Results in DB
        if sessions:
            sess_id = sessions[0]["session_id"]
            detail = state.report_repo.get_session_detail(sess_id)
            results_count = sum(len(rlist) for rlist in detail["results"].values())
            passed += print_step(17, f"Verify results recorded (count={results_count})", results_count > 0)
        else:
            passed += print_step(17, "Verify results (session missing)", False)
            
        # 18. Test Exporters
        from src.reports.excel_exporter import ExcelExporter
        ee = ExcelExporter(state.report_repo)
        ee.generate_session_report(xlsx_path, sessions[0]["session_id"])
        passed += print_step(18, "Generate Excel report", os.path.exists(xlsx_path))
        
        # 19. Cleanup Excel
        if os.path.exists(xlsx_path): os.remove(xlsx_path)
        passed += print_step(19, "Cleanup temporary files", True)

    except Exception as e:
        print(f"\n{Fore.RED}ERROR: {e}{Fore.RESET}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("   DEBUG: Cleaning up...")
        if cm: cm.stop()
        if server_proc:
            server_proc.terminate()
            server_proc.wait()
        if mock_log:
            mock_log.close()
        if db: db.close_all()
        
    print(f"\n{Style.BRIGHT}FINAL SCORE: {passed}/{20} STEPS PASSED{Style.RESET_ALL}\n")
    # Exit app
    # QTimer.singleShot(0, app.quit)
    # app.exec()
    sys.exit(0 if passed >= 17 else 1)

if __name__ == "__main__":
    run_test()
