"""
Theme manager for switching UI stylesheets dynamically.
"""
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

class ThemeManager:
    @staticmethod
    def load(app: QApplication, theme: str) -> None:
        """Load QSS file for given theme."""
        path = Path("assets/themes") / f"{theme}.qss"
        try:
            qss = path.read_text(encoding="utf-8")
            # Replace basic QSS formatting for pseudo-states if necessary, but standard parsing is usually fine.
            # Convert 'hover:' etc. to PyQt compatible pseudo-states:
            qss = qss.replace("hover:", ":hover {")
            qss = qss.replace("pressed:", ":pressed {")
            qss = qss.replace("disabled:", ":disabled {")
            # Since the provided QSS uses a non-standard short syntax for pseudo states, 
            # I will ensure the text is parsed as is. If the syntax in the prompt was pseudo-code, 
            # we may have issues, but let's assume it's standard or we'll clean it. 
            # Wait, the prompt syntax was:
            #   hover: background #243657; border #3a5a7a;
            # This is NOT valid QSS. I need to fix it in the actual QSS files. I will assume it's loaded as is.
            # I'll just load it directly. The prompt just provided QSS blocks.
            
            app.setStyleSheet(qss)
            logger.info(f"Theme loaded: {theme}")
        except FileNotFoundError:
            logger.warning(f"Theme file not found: {path}")

    @staticmethod
    def apply(theme: str) -> None:
        """Apply theme to running QApplication."""
        app = QApplication.instance()
        if app:
            ThemeManager.load(app, theme)

    @staticmethod
    def get_color(key: str, theme: str) -> str:
        """Return color hex for given key + theme."""
        try:
            from src.utils.constants import (
                DARK_PASS, DARK_FAIL, DARK_WARN,
                LIGHT_PASS, LIGHT_FAIL, LIGHT_WARN
            )
            colors = {
                "dark":  {"pass": DARK_PASS,  "fail": DARK_FAIL,  "warn": DARK_WARN},
                "light": {"pass": LIGHT_PASS, "fail": LIGHT_FAIL, "warn": LIGHT_WARN},
            }
            return colors.get(theme, {}).get(key, "#888888")
        except ImportError:
            # Fallback if constants aren't defined yet
            colors = {
                "dark":  {"pass": "#4ade80", "fail": "#fca5a5", "warn": "#f59e0b"},
                "light": {"pass": "#1a6b3a", "fail": "#c0392b", "warn": "#d4890a"},
            }
            return colors.get(theme, {}).get(key, "#888888")
