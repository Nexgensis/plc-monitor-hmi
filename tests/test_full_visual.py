"""
test_full_visual.py — Universal PLC Monitor
Standalone visual test script to verify end-to-end UI behavior 
with a seeded database and simulated environment.
"""
import sys
import os
import socket
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import Database
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.register_library_repo import RegisterLibraryRepo
from src.db.model_repo import ModelRepository
from src.db.model_map_repo import ModelMapRepo
from src.db.control_repo import ControlRegisterRepo
from src.db.io_list_repo import IOListRepo
from src.db.message_repo import MessageRegisterRepo
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.app_config_repo import AppConfigRepo
from src.db.user_repo import UserRepository

from src.ui.app_state import AppState
from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager

def check_mock_server():
    """Verify if a Modbus mock server is running on localhost."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", 5020))
        print("[OK] Mock PLC Server detected on port 5020")
        return True
    except:
        print("[WARN] Mock PLC Server not detected. Some live values will show '---'.")
        print("  To run mock server: python scripts/mock_plc.py")
        return False
    finally:
        s.close()

def run_visual_test():
    app = QApplication(sys.argv)
    ThemeManager.apply("dark")
    
    # 1. Setup Test Database
    db_path = "test_visual.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = Database.get_instance()
    db.db_path = db_path
    db.initialize()
    
    # 2. Instantiate Repos
    repos = {
        "profile":  PLCProfileRepository(db),
        "library":  RegisterLibraryRepo(db),
        "model":    ModelRepository(db),
        "map":      ModelMapRepo(db),
        "control":  ControlRegisterRepo(db),
        "io":       IOListRepo(db),
        "msg":      MessageRegisterRepo(db),
        "session":  SessionRepository(db),
        "report":   ReportRepository(db),
        "config":   AppConfigRepo(db),
        "user":     UserRepository(db)
    }

    # 3. Seed Test Data
    print("Seeding test data...")
    
    # Users
    repos["user"].create_user("ADMIN", "Admin@1234", "ADMIN")
    repos["user"].create_user("OPERATOR", "Op@1234", "OPERATOR")
    
    # Library
    r_val = repos["library"].create_register(
        name="Test Current", register_address=100, register_type="HOLDING", 
        data_type="UINT16", scale_factor=0.01, unit="A"
    )
    r_ctrl = repos["library"].create_register(
        name="Cycle Trigger", register_address=10, register_type="COIL", 
        data_type="BOOL", access="READ_WRITE"
    )
    r_msg = repos["library"].create_register(
        name="PLC Message", register_address=20, register_type="HOLDING", 
        data_type="UINT16"
    )

    # Models & Maps
    mid = repos["model"].create_model("TEST-SW-001", "Standard Test Model", "600-X1")
    repos["map"].add_mapping(mid, r_val, role="MEASURED", display_name="Primary Signal", group_name="Main Module")
    repos["map"].add_mapping(mid, r_msg, role="RESULT", display_name="Machine State")
    
    # Controls
    repos["control"].create_control("START TEST", r_ctrl, "START_TEST", 1, reset_after_ms=500)
    
    # I/O
    repos["io"].create_io_row("Safety Door", r_ctrl, "Safety", on_label="CLOSED", off_label="OPEN")
    
    # Messages
    repos["msg"].add_message_mapping(r_msg, 0, "SYSTEM READY", "green")
    repos["msg"].add_message_mapping(r_msg, 1, "TEST IN PROGRESS", "amber")
    repos["msg"].add_message_mapping(r_msg, 2, "TEST COMPLETED", "green")
    repos["msg"].add_message_mapping(r_msg, 3, "ALARM: OVERCURRENT", "red")

    # PLC Profile
    repos["profile"].update_profile(brand="Mock", host="127.0.0.1", port=5020, protocol="TCP")
    repos["config"].mark_setup_complete()

    # 4. AppState Setup
    state = AppState.get_instance()
    state.db = db
    for k, v in repos.items():
        setattr(state, f"{k}_repo" if k != "config" else "config_repo", v)
    
    state.set_plc_profile(repos["profile"].get_profile())
    state.refresh_message_config()

    # 5. Launch Window
    print("\n=== FULL APP VISUAL TEST ===")
    print("Checklist:")
    print("  [ ] Login with admin / Admin@1234")
    print("  [ ] Select TEST-SW-001 model")
    print("  [ ] Verify Dashboard shows 'Primary Signal' card")
    print("  [ ] Verify I/O Status shows 'Safety Door'")
    print("  [ ] Toggle Dark/Light theme in Settings")
    
    check_mock_server()
    
    window = MainWindow(state)
    window.show()
    QTimer.singleShot(100, window.on_startup)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_visual_test()
