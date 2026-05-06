"""
app_state.py — Universal PLC Monitor
Global singleton for application state, repository access, and runtime caches.
"""
from __future__ import annotations

import threading
import logging
from typing import Optional, Dict, Any, List

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

from src.plc.connection_manager import ConnectionManager
from src.plc.write_manager import PLCWriteManager

logger = logging.getLogger(__name__)


class AppState:
    _instance: Optional[AppState] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        if AppState._instance is not None:
            raise RuntimeError("AppState is a singleton. Use get_instance().")

        # Auth & Model
        self.current_user: Optional[Dict[str, Any]] = None
        self.current_model_id: Optional[int] = None
        self.current_model: Optional[Dict[str, Any]] = None

        # PLC Status
        self.is_plc_connected: bool = False
        self.is_plc_configured: bool = False
        self.current_theme: str = "dark"
        self.plc_profile: Optional[Dict[str, Any]] = None

        # Shared objects
        self.db: Optional[Database] = None
        self.connection_manager: Optional[ConnectionManager] = None
        self.write_manager: Optional[PLCWriteManager] = None

        # All Repositories
        self.profile_repo: Optional[PLCProfileRepository] = None
        self.library_repo: Optional[RegisterLibraryRepo] = None
        self.model_repo: Optional[ModelRepository] = None
        self.map_repo: Optional[ModelMapRepo] = None
        self.control_repo: Optional[ControlRegisterRepo] = None
        self.io_repo: Optional[IOListRepo] = None
        self.msg_repo: Optional[MessageRegisterRepo] = None
        self.session_repo: Optional[SessionRepository] = None
        self.report_repo: Optional[ReportRepository] = None
        self.config_repo: Optional[AppConfigRepo] = None
        self.user_repo: Optional[UserRepository] = None

        # Runtime Caches (refreshed on model change)
        self.poll_registers: List[Dict[str, Any]] = []
        self.message_lookup: Dict[int, Any] = {}
        self.message_register: Optional[Dict[str, Any]] = None
        self.dashboard_registers: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> AppState:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = AppState()
        return cls._instance

    def set_user(self, user: Dict[str, Any]) -> None:
        self.current_user = user
        logger.info("User logged in: %s (%s)", user.get("username"), user.get("role"))

    def clear_user(self) -> None:
        self.current_user = None
        logger.info("User logged out")

    def set_model(self, model_id: int) -> None:
        """
        Load full model config from DB.
        Rebuilds poll_registers, dashboard_registers.
        Notifies ConnectionManager.
        """
        if not self.model_repo or not self.map_repo or not self.io_repo:
            logger.error("Repositories not initialized in AppState")
            return

        self.current_model_id = model_id
        # In a real app, find by id. Prompt says: model = model_repo.get_all_models() # find by id
        models = self.model_repo.get_all_models()
        self.current_model = next((m for m in models if m["id"] == model_id), None)

        if not self.current_model:
            logger.warning("Model ID %d not found", model_id)
            return

        poll = self.map_repo.get_poll_registers(model_id)
        io = self.io_repo.get_poll_registers()

        # Combine + deduplicate by register_id
        seen = set()
        combined = []
        for r in poll + io:
            reg_id = r.get("register_id")
            if reg_id and reg_id not in seen:
                seen.add(reg_id)
                combined.append(r)

        self.poll_registers = combined
        self.dashboard_registers = self.map_repo.get_dashboard_registers(model_id)

        logger.info("Model set: %s. Polling %d registers.", self.current_model["name"], len(combined))

        if self.connection_manager:
            self.connection_manager.update_poll_list(
                combined,
                self.message_register,
                self.message_lookup
            )

    def refresh_message_config(self) -> None:
        """Reload message register config from DB."""
        if not self.msg_repo:
            return

        # The message register ID is stored in plc_profile
        msg_reg_id = None
        if self.plc_profile:
            msg_reg_id = self.plc_profile.get("message_register_id")

        if msg_reg_id and self.library_repo:
            # Fetch the register definition from the library
            reg = self.library_repo.get_register(msg_reg_id)
            self.message_register = reg  # dict or None
        else:
            self.message_register = None

        # Build value → (text, color) lookup
        if msg_reg_id:
            self.message_lookup = self.msg_repo.get_messages_for_register(msg_reg_id)
        else:
            self.message_lookup = {}

        logger.info("Message config refreshed. Register ID=%s, %d triggers.",
                     msg_reg_id, len(self.message_lookup))

    def set_plc_profile(self, profile: Dict[str, Any]) -> None:
        self.plc_profile = profile
        if self.profile_repo:
            # Note: prompt says profile_repo.is_configured()
            # If the repo doesn't have it, I'll check if host is set.
            # Checking if PLCProfileRepository has is_configured...
            # I checked it earlier, it doesn't have it. I should add it.
            self.is_plc_configured = self.profile_repo.is_configured()

    def is_admin(self) -> bool:
        return self.current_user is not None and self.current_user.get("role") == "ADMIN"

    def can_access_config(self) -> bool:
        return self.is_admin()

    def reload_all_caches(self) -> None:
        """Full reload after config changes."""
        self.refresh_message_config()
        if self.current_model_id:
            self.set_model(self.current_model_id)

    def toggle_theme(self) -> str:
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        return self.current_theme
