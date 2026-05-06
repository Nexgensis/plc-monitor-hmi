"""
Standalone visual test for Step 4 UI components.
Launches the full MainWindow with a seeded database for manual verification.
"""
import sys
import os
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

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
from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager

def run_visual_test():
    # 1. Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # 2. Setup isolated DB
    db_path = "visual_test.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = Database(db_path)
    db.initialize()
    seed_database(db)
    
    # 3. Build AppState
    state = AppState.get_instance()
    state.db = db
    state.user_repo = UserRepository(db)
    state.model_repo = ModelRepository(db)
    state.param_repo = ParameterRepository(db)
    state.session_repo = SessionRepository(db)
    state.report_repo = ReportRepository(db)
    state.plc_profile_repo = PLCProfileRepository(db)
    
    state.plc_profile = state.plc_profile_repo.get_profile()
    state.is_plc_configured = False # Force "not configured" notice
    state.d21_messages = state.plc_profile_repo.get_d21_messages()
    
    # Mock hardware managers for visual test
    from unittest.mock import MagicMock
    state.connection_manager = MagicMock()
    state.write_manager = MagicMock()
    
    # 4. Launch App
    app = QApplication(sys.argv)
    ThemeManager.load(app, "dark")
    
    window = MainWindow(state)
    
    print("\n" + "="*30)
    print("=== STEP 4 VISUAL TEST ===")
    print("="*30)
    print("\nDARK THEME (default):")
    print("  [ ] Dark background, sidebar visible")
    print("  [ ] Login card centered, role dropdown, password")
    print("  [ ] PLC notice: not configured warning shown")
    print("  [ ] Wrong password: shake animation + error label")
    print("  [ ] Login admin/Admin@1234 -> model page")
    print("\nMODEL PAGE:")
    print("  [ ] 4 large buttons: SW-0256/A/C/U")
    print("  [ ] Buttons in correct order")
    print("  [ ] Click a model -> button highlights")
    print("  [ ] Push status shows not configured")
    print("  [ ] Start Auto Test button appears")
    print("\nSIDEBAR:")
    print("  [ ] 6 nav items visible after login")
    print("  [ ] Active item highlighted")
    print("  [ ] Settings only for Admin")
    print("  [ ] Theme toggle icon (dark/light)")
    print("  [ ] Logout button at bottom")
    print("\nLIGHT THEME:")
    print("  [ ] Toggle theme -> switches to light")
    print("  [ ] White cards, navy sidebar, clean")
    print("  [ ] All text readable")
    print("\nLOGOUT:")
    print("  [ ] Click logout -> login overlay reappears")
    print("  [ ] Sidebar hidden after logout")
    print("\nCredentials: admin/Admin@1234  operator/Op@1234")
    print("="*30 + "\n")
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_visual_test()
