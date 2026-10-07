"""
app_config_repo.py — Universal PLC Monitor
Manages global application settings like first-run flag and theme.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .database import Database

logger = logging.getLogger(__name__)


class AppConfigRepo:
    """
    Repository for general application configuration stored in app_config table.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_value(self, key: str, default: str = "") -> str:
        """Retrieves a config value by key."""
        row = self.db.fetchone("SELECT value FROM app_config WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_value(self, key: str, value: str) -> None:
        """Sets a config value, creating it if it doesn't exist."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO app_config (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """
        self.db.execute(query, (key, str(value), now))
        logger.info("Config set: %s = %s", key, value)

    def is_first_run(self) -> bool:
        """Checks if this is the first time the app is running."""
        val = self.get_value("first_run", "1")
        return val == "1"

    def mark_setup_complete(self) -> None:
        """Marks the setup wizard as completed."""
        self.set_value("first_run", "0")

    def get_theme(self) -> str:
        """Retrieves the current UI theme."""
        return self.get_value("theme", "dark")

    def set_theme(self, theme: str) -> None:
        """Saves the preferred UI theme."""
        self.set_value("theme", theme)

    def get_max_dashboard_cards(self) -> int:
        """Retrieves the maximum number of dashboard cards allowed."""
        val = self.get_value("max_dashboard_cards", "20")
        try:
            return max(1, min(30, int(val)))
        except (ValueError, TypeError):
            return 20

    def set_max_dashboard_cards(self, count: int) -> None:
        """Sets the maximum number of dashboard cards (clamped 1-30)."""
        self.set_value("max_dashboard_cards", str(max(1, min(30, count))))

    def get_font_size(self) -> int:
        """Retrieves the font size setting."""
        val = self.get_value("font_size", "13")
        try:
            return max(9, min(20, int(val)))
        except (ValueError, TypeError):
            return 13

    def set_font_size(self, size: int) -> None:
        """Saves the font size setting (clamped 9-20)."""
        self.set_value("font_size", str(max(9, min(20, size))))

    def get_high_contrast(self) -> bool:
        """Retrieves the high contrast mode setting."""
        return self.get_value("high_contrast", "0") == "1"

    def set_high_contrast(self, enabled: bool) -> None:
        """Saves the high contrast mode setting."""
        self.set_value("high_contrast", "1" if enabled else "0")
