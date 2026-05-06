# tests/test_settings_visual.py
"""
Standalone visual test for SettingsWindow.
Run: python tests/test_settings_visual.py
"""

import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from src.db.database import Database
from src.db.seed import seed_database
from src.db.user_repo import UserRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.plc_profile_repo import PLCProfileRepository
from src.ui.app_state import AppState
from src.ui.settings_window import SettingsWindow
from src.ui.styles.style_loader import StyleLoader

def run_visual_test():
    logging.basicConfig(level=logging.INFO)
    
    # 1. Setup real DB
    db_path = "settings_visual.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = Database(db_path)
    db.initialize()
    seed_database(db)
    
    # 2. Build full AppState
    state = AppState.get_instance()
    state.db = db
    state.user_repo = UserRepository(db)
    state.model_repo = ModelRepository(db)
    state.param_repo = ParameterRepository(db)
    state.session_repo = SessionRepository(db)
    state.report_repo = ReportRepository(db)
    state.plc_profile_repo = PLCProfileRepository(db)
    
    # 3. Set current user
    state.current_user = {"id": 1, "username": "admin", "role": "ADMIN"}
    state.plc_profile = state.plc_profile_repo.get_profile()
    
    # 4. GUI setup
    app = QApplication(sys.argv)
    StyleLoader.apply_style(app)
    
    # 5. Show window
    win = SettingsWindow(state)
    win.show()
    
    # 6. Print Checklist
    print("\n" + "="*40)
    print("=== SETTINGS VISUAL TEST ===")
    print("="*40)
    print("\nLEFT PANEL — model list:")
    print("  [ ] MI-7646AZ visible with status dot")
    print("  [ ] Add Model opens dialog")
    print("  [ ] Add with 'Copy from' duplicates params")
    print("  [ ] Delete shows confirmation")
    print("\nTAB 1 — Parameters:")
    print("  [ ] 3 rows for MI-7646AZ")
    print("  [ ] Add row → row appears in table")
    print("  [ ] Move Up/Down reorders")
    print("  [ ] Delete shows confirmation")
    print("  [ ] Save updates DB")
    print("\nTAB 2 — Register Mapping:")
    print("  [ ] SpinBoxes show current register values")
    print("  [ ] Change a value → Modbus addr updates")
    print("  [ ] Duplicate registers → amber banner")
    print("  [ ] Green/amber/gray row indicators")
    print("\nTAB 3 — Limit Values:")
    print("  [ ] Min/Max spinboxes populated")
    print("  [ ] Min > Max → red highlight")
    print("  [ ] Save to DB works")
    print("  [ ] Push to PLC (needs mock server)")
    print("\nTAB 4 — Model Block:")
    print("  [ ] Values [37,38,37,2,1,0] visible")
    print("  [ ] Add/remove values works")
    print("  [ ] Write (needs mock server)")
    print("\nTAB 5 — Connection:")
    print("  [ ] Shows current PLC profile")
    print("  [ ] Edit Profile opens dialog")
    print("  [ ] Test Connection (needs mock server)")
    print("\nRIGHT PANEL — Live PLC:")
    print("  [ ] Shows param register values")
    print("  [ ] Refresh reads from PLC (if connected)")
    print("  [ ] Write log shows entries after push")
    print("\n" + "="*40)
    
    # 7. Cleanup on exit
    exit_code = app.exec()
    
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"Note: Could not delete {db_path}: {e}")
            
    sys.exit(exit_code)

if __name__ == "__main__":
    run_visual_test()
