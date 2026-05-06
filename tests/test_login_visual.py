"""
Standalone visual test for the Login Window.
Run with: python -m tests.test_login_visual
"""
import sys
import logging
from PyQt6.QtWidgets import QApplication

from src.db.database import Database
from src.db.seed import seed_database
from src.ui.app_state import AppState
from src.ui.login_window import LoginWindow
from src.ui.styles.style_loader import StyleLoader

# Repositories
from src.db.repositories import (
    UserRepository,
    ModelRepository,
    ParameterRepository,
    SessionRepository,
    ReportRepository,
    PLCProfileRepository
)

from src.plc.plc_driver import PLCDriverFactory
from src.plc.connection_manager import ConnectionManager
from src.plc.data_model import PLCDataModel
from src.plc.write_manager import PLCWriteManager

def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    setup_logging()
    app = QApplication(sys.argv)
    
    # 1. Create real DB
    db = Database.get_instance("plc_monitor.db")
    db.initialize()

    # 2. Seed database
    seed_database(db)

    # 3. Init all repos + AppState
    user_repo = UserRepository(db)
    model_repo = ModelRepository(db)
    param_repo = ParameterRepository(db)
    session_repo = SessionRepository(db)
    report_repo = ReportRepository(db)
    profile_repo = PLCProfileRepository(db)

    state = AppState.get_instance()
    state.db = db
    state.user_repo = user_repo
    state.model_repo = model_repo
    state.param_repo = param_repo
    state.session_repo = session_repo
    state.report_repo = report_repo
    state.plc_profile_repo = profile_repo
    
    # In order to force connection to mock server running locally on 5020:
    profile = profile_repo.get_profile()
    if profile:
        profile['connection_type'] = 'TCP'
        profile['ip_address'] = '127.0.0.1'
        profile['port'] = 5020
    state.set_plc_profile(profile)

    # 4. Create real ConnectionManager
    data_model = PLCDataModel()
    driver = PLCDriverFactory.create_from_profile(profile)
    
    conn_mgr = ConnectionManager(
        plc_profile=profile,
        model_parameters=[],
        data_model=data_model
    )
    
    # 5. Create real WriteManager
    write_mgr = PLCWriteManager(driver, db, state)
    
    state.connection_manager = conn_mgr
    state.write_manager = write_mgr
    state.is_plc_connected = False  # Start falsely, let CM connect it 
    
    # Start polling
    conn_mgr.start()

    # 6. QApplication + StyleLoader
    StyleLoader.load(app)

    # 7. Show LoginWindow
    window = LoginWindow(state)
    window.show()

    # 8. Print checklist
    print("\n" + "="*40)
    print("=== LOGIN VISUAL TEST ===")
    print("Credentials: admin/Admin@1234  operator/Op@1234")
    print("")
    print("Check these after logging in as Admin:")
    print("  [ ] Right panel appears with welcome message")
    print("  [ ] Settings button visible")
    print("  [ ] Reports button visible")
    print("  [ ] Model combo shows MI-7646AZ")
    print("  [ ] Selecting model shows push status")
    print("  [ ] If mock server running: push status green")
    print("  [ ] If no server: push status shows 'not connected'")
    print("")
    print("Log in as Operator and check:")
    print("  [ ] Settings button HIDDEN")
    print("  [ ] Reports button HIDDEN")
    print("")
    print("Mock server (optional):")
    print("  Terminal 1: python -m tests.mock_plc_server --port 5020")
    print("="*40 + "\n")

    # 9. Exit gracefully
    exit_code = app.exec()
    conn_mgr.stop()
    db.close_all()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
