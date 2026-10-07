"""
Theme manager for switching UI stylesheets dynamically.

Single live styling entry point for the app (loads assets/themes/*.qss).
Provides:
  - ThemeManager.apply(theme)        apply a stylesheet + notify subscribers
  - ThemeManager.theme_changed       signal bus: str theme name
  - ThemeManager.get_color(key, ...) design-token bridge to src.utils.constants
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Resolved from this file: <root>/src/ui/theme_manager.py -> <root>/assets/themes
_THEMES_DIR = Path(__file__).resolve().parents[2] / "assets" / "themes"

# Appended on top of the active theme when high-contrast mode is on
# (shared by SettingsPage and startup restore in main.py).
HIGH_CONTRAST_OVERRIDE = """
QPushButton { border: 2px solid #ffffff !important; }
QLineEdit, QComboBox { border: 2px solid #ffffff !important; }
QTableWidget { gridline-color: #ffffff !important; }
"""


class _ThemeBus(QObject):
    """Broadcasts theme changes so custom-painted widgets can recolor."""
    theme_changed = pyqtSignal(str)


class ThemeManager:
    """Static facade: stylesheet loading + theme-change broadcast + tokens."""

    _bus: Optional[_ThemeBus] = None
    _current: str = "dark"

    # token key -> (DARK_ constant name, LIGHT_ constant name)
    _TOKENS: dict[str, tuple[str, str]] = {
        "bg_primary":     ("DARK_BG_PRIMARY", "LIGHT_BG_PRIMARY"),
        "bg_secondary":   ("DARK_BG_SECONDARY", "LIGHT_BG_SECONDARY"),
        "bg_card":        ("DARK_BG_CARD", "LIGHT_BG_CARD"),
        "border":         ("DARK_BORDER", "LIGHT_BORDER"),
        "text_primary":   ("DARK_TEXT_PRIMARY", "LIGHT_TEXT_PRIMARY"),
        "text_muted":     ("DARK_TEXT_MUTED", "LIGHT_TEXT_MUTED"),
        "accent":         ("DARK_ACCENT", "LIGHT_ACCENT"),
        "pass":           ("DARK_PASS", "LIGHT_PASS"),
        "fail":           ("DARK_FAIL", "LIGHT_FAIL"),
        "running":        ("DARK_RUNNING", "LIGHT_RUNNING"),
        "warn":           ("DARK_WARN", "LIGHT_WARN"),
        "sidebar_bg":     ("DARK_SIDEBAR_BG", "LIGHT_SIDEBAR_BG"),
        "sidebar_active": ("DARK_SIDEBAR_ACTIVE", "LIGHT_SIDEBAR_ACTIVE"),
    }

    # ── signal bus ────────────────────────────────────────────────────

    @classmethod
    def bus(cls) -> _ThemeBus:
        if cls._bus is None:
            cls._bus = _ThemeBus()
        return cls._bus

    @classmethod
    def current(cls) -> str:
        return cls._current

    # ── loading / applying ────────────────────────────────────────────

    @staticmethod
    def load(app: QApplication, theme: str) -> None:
        """Load QSS file for given theme and apply it to the app."""
        path = _THEMES_DIR / f"{theme}.qss"
        try:
            qss = path.read_text(encoding="utf-8")
            app.setStyleSheet(qss)
            logger.info("Theme loaded: %s", theme)
        except FileNotFoundError:
            logger.warning("Theme file not found: %s", path)

    @classmethod
    def apply(cls, theme: str) -> None:
        """Apply theme to running QApplication and notify subscribers."""
        app = QApplication.instance()
        if not app:
            logger.warning("ThemeManager.apply('%s') called before QApplication", theme)
            return
        cls.load(app, theme)
        cls._current = theme
        cls.bus().theme_changed.emit(theme)

    @staticmethod
    def apply_high_contrast(enabled: bool) -> None:
        """
        Append the high-contrast override to the CURRENT stylesheet.
        Call ThemeManager.apply(theme) first if the theme needs re-loading.
        """
        app = QApplication.instance()
        if app and enabled:
            app.setStyleSheet(app.styleSheet() + HIGH_CONTRAST_OVERRIDE)

    # ── design-token bridge ───────────────────────────────────────────

    @classmethod
    def get_color(cls, key: str, theme: Optional[str] = None) -> str:
        """
        Resolve a design token (see _TOKENS keys) for the given theme
        (defaults to the currently applied theme). Falls back to #888888
        on unknown keys.
        """
        from src.utils import constants as c

        theme = theme or cls._current
        names = cls._TOKENS.get(key)
        if not names:
            logger.warning("Unknown color token: %s", key)
            return "#888888"
        name = names[0] if theme == "dark" else names[1]
        return getattr(c, name, "#888888")
