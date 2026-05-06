"""
main.py — Universal PLC Monitor
Application entry point. Initializes database, repositories, 
background communication threads, and the main window.
"""
from __future__ import annotations

import sys
import os

# Ensure the root directory is in the Python path so 'src' can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from logging.handlers import RotatingFileHandler
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Repository Imports
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

# UI & Logic Imports
from src.ui.app_state import AppState
from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager

# Constants
from src.utils.constants import APP_NAME


def setup_logging():
    """Rotating log file setup (5MB x 3)."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    handler = RotatingFileHandler(
        os.path.join(log_dir, "plc_monitor.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    # Also log to console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root_logger.addHandler(console)


def main():
    # 1. Setup Logging
    setup_logging()
    logger = logging.getLogger("Main")
    logger.info("--- Starting %s ---", APP_NAME)

    # 2. QApplication Setup
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    # Apply default theme (will be overridden by DB setting later)
    ThemeManager.apply("dark")

    # 3. Database Initialization
    try:
        db = Database.get_instance()
        db.initialize()
    except Exception as e:
        logger.critical("Failed to initialize database: %s", e)
        sys.exit(1)

    # 4. Repository Instantiation
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

    # 5. AppState Initialization
    state = AppState.get_instance()
    state.db = db
    
    # Bind repositories
    state.profile_repo = repos["profile"]
    state.library_repo = repos["library"]
    state.model_repo   = repos["model"]
    state.map_repo     = repos["map"]
    state.control_repo = repos["control"]
    state.io_repo      = repos["io"]
    state.msg_repo     = repos["msg"]
    state.session_repo = repos["session"]
    state.report_repo  = repos["report"]
    state.config_repo  = repos["config"]
    state.user_repo    = repos["user"]

    # 6. Load Persistent Settings
    saved_theme = repos["config"].get_theme()
    ThemeManager.apply(saved_theme)
    state.current_theme = saved_theme
    
    # 7. Initialize PLC Profile & Message Config
    profile = repos["profile"].get_profile()
    state.set_plc_profile(profile)
    state.refresh_message_config()

    # 7.1 Seed Default Users if empty
    try:
        if not repos["user"].get_all_users():
            logger.info("First run detected. Seeding default accounts (ADMIN/admin123, OPERATOR/op123).")
            repos["user"].create_user("ADMIN", "admin123", "ADMIN")
            repos["user"].create_user("OPERATOR", "op123", "OPERATOR")
            repos["user"].create_user("SUPERVISOR", "super123", "SUPERVISOR")
    except Exception as e:
        logger.error("Failed to seed default users: %s", e)
    
    # 8. Start Main Window
    try:
        window = MainWindow(state)
        window.show()
        
        # Delayed startup tasks (first run check, login overlay)
        QTimer.singleShot(100, window.on_startup)
        
        # 9. Application Event Loop
        exit_code = app.exec()
        
        # 10. Graceful Shutdown
        if state.connection_manager:
            state.connection_manager.stop()
            
        db.close_all()
        logger.info("--- %s closed cleanly ---", APP_NAME)
        sys.exit(exit_code)
        
    except Exception as e:
        logger.critical("Unhandled application exception: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
