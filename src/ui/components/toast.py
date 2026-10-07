"""
toast.py — Universal PLC Monitor
Non-blocking toast notification system. Notifications slide in from the top-right
and auto-dismiss after a configurable timeout.
"""
from __future__ import annotations

import logging
from enum import Enum
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal

logger = logging.getLogger(__name__)


class ToastLevel(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ToastNotification(QWidget):
    """A single toast notification widget."""

    closed = pyqtSignal(object)  # emits self

    # token key used to resolve the accent stripe/icon per theme
    LEVEL_ACCENT_TOKEN = {
        ToastLevel.INFO:    "accent",
        ToastLevel.SUCCESS: "pass",
        ToastLevel.WARNING: "warn",
        ToastLevel.ERROR:   "fail",
    }
    # panel backgrounds per theme (tinted surfaces; see assets/themes/*.qss)
    LEVEL_BG = {
        "dark": {
            ToastLevel.INFO:    "#1e3a5f",
            ToastLevel.SUCCESS: "#064e3b",
            ToastLevel.WARNING: "#451a03",
            ToastLevel.ERROR:   "#450a0a",
        },
        "light": {
            ToastLevel.INFO:    "#e8f6fb",
            ToastLevel.SUCCESS: "#e7f8ef",
            ToastLevel.WARNING: "#fdf4e3",
            ToastLevel.ERROR:   "#fdecec",
        },
    }
    LEVEL_ICONS = {
        ToastLevel.INFO:    "ℹ",
        ToastLevel.SUCCESS: "✓",
        ToastLevel.WARNING: "⚠",
        ToastLevel.ERROR:   "✕",
    }

    def __init__(self, message: str, level: ToastLevel = ToastLevel.INFO,
                 duration: int = 3000, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(340)
        self.setFixedHeight(56)

        from src.ui.theme_manager import ThemeManager

        theme = ThemeManager.current()
        accent = ThemeManager.get_color(self.LEVEL_ACCENT_TOKEN[level])
        bg = self.LEVEL_BG.get(theme, self.LEVEL_BG["dark"])[level]
        msg_color = ThemeManager.get_color("text_primary")
        close_color = ThemeManager.get_color("text_muted")
        icon = self.LEVEL_ICONS[level]

        self.setStyleSheet(f"""
            ToastNotification {{
                background-color: {bg};
                border-left: 4px solid {accent};
                border-radius: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color: {accent}; font-size: 16px; font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f"color: {msg_color}; font-size: 12px; background: transparent; border: none;"
        )
        layout.addWidget(msg_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"color: {close_color}; font-size: 10px; background: transparent; "
            "border: none; border-radius: 10px;"
        )
        close_btn.clicked.connect(self._close)
        layout.addWidget(close_btn)
        
        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._close)
        self._timer.start(duration)
        
        # Opacity effect for fade animation
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        
        self.setAccessibleName(f"{level.value} notification: {message}")
    
    def _close(self) -> None:
        """Fade out and close."""
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim.finished.connect(self._emit_closed)
        self._fade_anim.start()
    
    def _emit_closed(self) -> None:
        self.closed.emit(self)
        self.close()
    
    def enterEvent(self, event) -> None:
        """Pause auto-dismiss on hover."""
        self._timer.stop()
        super().enterEvent(event)
    
    def leaveEvent(self, event) -> None:
        """Resume auto-dismiss on leave."""
        self._timer.start(1500)
        super().leaveEvent(event)


class ToastManager:
    """Singleton that manages stacking toast notifications on screen."""
    
    _instance: "ToastManager | None" = None
    _toasts: list[ToastNotification] = []
    _offset_y: int = 60
    
    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._instance is None:
            cls._instance = ToastManager()
        return cls._instance
    
    def show(self, message: str, level: ToastLevel = ToastLevel.INFO,
             duration: int = 3000) -> None:
        """Show a toast notification."""
        from PyQt6.QtWidgets import QApplication
        
        app = QApplication.instance()
        if not app:
            return
        
        # Find the main window as parent
        parent = None
        for w in app.topLevelWidgets():
            if w.isVisible():
                parent = w
                break
        
        toast = ToastNotification(message, level, duration, parent)
        toast.closed.connect(self._on_toast_closed)
        self._toasts.append(toast)
        
        self._reposition_toasts()
        toast.show()
        toast.raise_()
    
    def _on_toast_closed(self, toast: ToastNotification) -> None:
        try:
            from PyQt6.sip import isdeleted as sip_isdeleted
            if not sip_isdeleted(toast) and toast in self._toasts:
                self._toasts.remove(toast)
        except (ImportError, RuntimeError, ValueError):
            pass
        self._reposition_toasts()
    
    def _reposition_toasts(self) -> None:
        """Stack toasts from top-right corner."""
        if not self._toasts:
            return
        
        # Clean up deleted toasts
        try:
            from PyQt6.sip import isdeleted as sip_isdeleted
            self._toasts = [t for t in self._toasts if not sip_isdeleted(t)]
        except ImportError:
            pass
        if not self._toasts:
            return
        
        # Find main window for positioning reference
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return
        
        main_win = None
        for w in app.topLevelWidgets():
            if w.isVisible() and hasattr(w, 'width'):
                main_win = w
                break
        
        if not main_win:
            return
        
        x = main_win.x() + main_win.width() - 360
        y = main_win.y() + self._offset_y
        
        for toast in self._toasts:
            try:
                toast.move(x, y)
                y += toast.height() + 8
            except RuntimeError:
                continue
    
    def info(self, message: str, duration: int = 3000) -> None:
        self.show(message, ToastLevel.INFO, duration)
    
    def success(self, message: str, duration: int = 3000) -> None:
        self.show(message, ToastLevel.SUCCESS, duration)
    
    def warning(self, message: str, duration: int = 4000) -> None:
        self.show(message, ToastLevel.WARNING, duration)
    
    def error(self, message: str, duration: int = 5000) -> None:
        self.show(message, ToastLevel.ERROR, duration)
