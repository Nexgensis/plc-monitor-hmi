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
import bcrypt
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
from src.db.block_repo import BlockRepo

# UI & Logic Imports
from src.ui.app_state import AppState
from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager

# Constants
from src.utils.constants import APP_NAME


def setup_logging():
    """Rotating log file setup (5MB x 3)."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
        
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
        "user":     UserRepository(db),
        "block":    BlockRepo(db)
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
    state.block_repo   = repos["block"]

    # 6. Load Persistent Settings
    saved_theme = repos["config"].get_theme()
    ThemeManager.apply(saved_theme)
    state.current_theme = saved_theme

    # 6.1 Restore accessibility settings (font size + high contrast)
    saved_font = repos["config"].get_font_size()
    font = app.font()
    font.setPointSize(saved_font)
    app.setFont(font)
    if repos["config"].get_high_contrast():
        ThemeManager.apply_high_contrast(True)
    
    # 7. Initialize PLC Profile & Message Config
    profile = repos["profile"].get_profile()
    state.set_plc_profile(profile)
    state.refresh_message_config()

    # 7.1 Seed Default Users if empty (with bcrypt-hashed passwords)
    try:
        if not repos["user"].get_all_users():
            logger.info("First run detected. Seeding default accounts.")
            admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt(rounds=12)).decode("utf-8")
            op_hash    = bcrypt.hashpw(b"op123",    bcrypt.gensalt(rounds=12)).decode("utf-8")
            sup_hash   = bcrypt.hashpw(b"super123", bcrypt.gensalt(rounds=12)).decode("utf-8")
            repos["user"].create_user("ADMIN", admin_hash, "ADMIN")
            repos["user"].create_user("OPERATOR", op_hash, "OPERATOR")
            repos["user"].create_user("SUPERVISOR", sup_hash, "SUPERVISOR")
            logger.info("Default users seeded: ADMIN, OPERATOR, SUPERVISOR")
    except Exception as e:
        logger.error("Failed to seed default users: %s", e)

    # 7.2 Fix legacy plaintext passwords — re-hash any user whose
    #     password_hash is not a valid bcrypt hash (missing $2b$ prefix).
    _LEGACY_PASSWORDS = {"ADMIN": "admin123", "OPERATOR": "op123", "SUPERVISOR": "super123"}
    try:
        for user in repos["user"].get_all_users():
            u = repos["user"].get_user_by_username(user["username"])
            if not u:
                continue
            stored = u.get("password_hash") or ""
            if stored.startswith("$2b$"):
                continue  # already bcrypt-hashed
            legacy_pw = _LEGACY_PASSWORDS.get(user["username"])
            if legacy_pw:
                new_hash = bcrypt.hashpw(legacy_pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
                repos["user"].update_user(u["id"], password_hash=new_hash)
                logger.info("Re-hashed legacy password for user '%s'", user["username"])
            else:
                logger.warning("User '%s' has a non-bcrypt password but no known default — skipping", user["username"])
    except Exception as e:
        logger.error("Failed to fix legacy passwords: %s", e)
    
    # 8. Start Main Window
    try:
        window = MainWindow(state)
        window.show()
        
        # Delayed startup tasks (first run check, login overlay)
        QTimer.singleShot(100, window.on_startup)
        
        # 9. Application Event Loop
        exit_code = app.exec()
        
        # 10. Graceful Shutdown
        if state.write_manager:
            state.write_manager.stop()
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
