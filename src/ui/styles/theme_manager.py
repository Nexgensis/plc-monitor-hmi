"""
ui/styles/theme_manager.py
Singleton managing dark / light QSS themes with a signal for live reloading.
"""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication


LIGHT_QSS = """
/* =====================  LIGHT THEME  ===================== */
QMainWindow, QDialog, QWidget {
    background-color: #f0f2f5;
    font-family: "Segoe UI";
    font-size: 13px;
    color: #1a1a2e;
}

/* --- Buttons --- */
QPushButton {
    background-color: #1e2d4a;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
}
QPushButton:hover    { background-color: #243657; }
QPushButton:pressed  { background-color: #162238; }
QPushButton:disabled { background-color: #b0b8c8; color: #7a8090; }

QPushButton#btn_danger         { background-color: #c0392b; }
QPushButton#btn_danger:hover   { background-color: #e74c3c; }
QPushButton#btn_success        { background-color: #1a6b3a; }
QPushButton#btn_success:hover  { background-color: #218f4e; }
QPushButton#btn_secondary      { background-color: #6c757d; }
QPushButton#btn_secondary:hover{ background-color: #5a6268; }

/* Theme toggle — looks like an outlined pill */
QPushButton#btn_theme {
    background-color: transparent;
    color: #1e2d4a;
    border: 1.5px solid #1e2d4a;
    border-radius: 14px;
    padding: 4px 14px;
    font-size: 12px;
    min-height: 28px;
    min-width: 80px;
}
QPushButton#btn_theme:hover { background-color: #e0e7f0; }

/* --- Inputs --- */
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1.5px solid #c0c8d8;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    color: #1a1a2e;
    min-height: 34px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #1e2d4a;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: none;
}
QComboBox::down-arrow {
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #1a1a2e;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #c0c8d8;
    selection-background-color: #d0ddf0;
    selection-color: #1a1a2e;
}

/* --- Tables --- */
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8f9fc;
    gridline-color: #d8dde8;
    selection-background-color: #d0ddf0;
    selection-color: #1a1a2e;
    border: 1px solid #d8dde8;
}
QHeaderView::section {
    background-color: #1e2d4a;
    color: white;
    font-weight: 600;
    height: 36px;
    padding: 4px 8px;
    border: 1px solid #d8dde8;
}

/* --- Tabs --- */
QTabWidget::pane {
    border: 1px solid #c0c8d8;
    border-radius: 4px;
    background: #f0f2f5;
}
QTabBar::tab {
    background: #d8dde8;
    color: #1a1a2e;
    padding: 8px 20px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-size: 13px;
}
QTabBar::tab:selected { background: #1e2d4a; color: white; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #b8c2d8; }

/* --- Group Boxes --- */
QGroupBox {
    border: 1.5px solid #c0c8d8;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: 600;
    color: #1e2d4a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}

/* --- Labels --- */
QLabel#label_title {
    font-size: 18px;
    font-weight: 700;
    color: #1e2d4a;
}
QLabel#label_subtitle { font-size: 13px; color: #5a6a8a; }

/* --- Frames --- */
QFrame#card { background: #ffffff; border: 1px solid #d0d8e8; border-radius: 8px; }
QFrame#status_bar_frame { background-color: #1e2d4a; color: white; min-height: 32px; }

/* --- Status indicators --- */
QLabel#indicator_ok  { background-color: #1a6b3a; color: white; border-radius: 4px; padding: 4px 12px; }
QLabel#indicator_ng  { background-color: #c0392b; color: white; border-radius: 4px; padding: 4px 12px; }
QLabel#indicator_idle{ background-color: #6c757d; color: white; border-radius: 4px; padding: 4px 12px; }
QLabel#plc_connected    { background-color: #1a6b3a; color: white; }
QLabel#plc_disconnected { background-color: #c0392b; color: white; }

/* --- Scroll bars --- */
QScrollBar:vertical   { border: none; background: #f0f2f5; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #1e2d4a; min-height: 20px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; }
QScrollBar:horizontal { border: none; background: #f0f2f5; height: 8px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #1e2d4a; min-width: 20px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { border: none; background: none; }

/* --- Form labels alignment --- */
QFormLayout QLabel { min-width: 160px; }
"""


DARK_QSS = """
/* =====================  DARK THEME  ===================== */
QMainWindow, QDialog, QWidget {
    background-color: #12161e;
    font-family: "Segoe UI";
    font-size: 13px;
    color: #dce4f0;
}

/* --- Buttons --- */
QPushButton {
    background-color: #2a3f66;
    color: #dce4f0;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
}
QPushButton:hover    { background-color: #334d7a; }
QPushButton:pressed  { background-color: #1e3054; }
QPushButton:disabled { background-color: #2c3040; color: #5a6070; }

QPushButton#btn_danger         { background-color: #7d2020; }
QPushButton#btn_danger:hover   { background-color: #a02828; }
QPushButton#btn_success        { background-color: #145230; }
QPushButton#btn_success:hover  { background-color: #1a6b3a; }
QPushButton#btn_secondary      { background-color: #3a4050; }
QPushButton#btn_secondary:hover{ background-color: #454c60; }

QPushButton#btn_theme {
    background-color: transparent;
    color: #a0b8e0;
    border: 1.5px solid #a0b8e0;
    border-radius: 14px;
    padding: 4px 14px;
    font-size: 12px;
    min-height: 28px;
    min-width: 80px;
}
QPushButton#btn_theme:hover { background-color: #1e2d4a; }

/* --- Inputs --- */
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {
    background: #1c2230;
    border: 1.5px solid #364060;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    color: #dce4f0;
    min-height: 34px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #4a7ada;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: none;
}
QComboBox::down-arrow {
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #a0b8e0;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: #1c2230;
    border: 1px solid #364060;
    color: #dce4f0;
    selection-background-color: #2a3f66;
    selection-color: #dce4f0;
}

/* --- Tables --- */
QTableWidget {
    background: #1c2230;
    alternate-background-color: #202836;
    gridline-color: #2e3c50;
    selection-background-color: #2a3f66;
    selection-color: #dce4f0;
    border: 1px solid #2e3c50;
    color: #dce4f0;
}
QHeaderView::section {
    background-color: #0f1624;
    color: #a0b8e0;
    font-weight: 600;
    height: 36px;
    padding: 4px 8px;
    border: 1px solid #2e3c50;
}

/* --- Tabs --- */
QTabWidget::pane { border: 1px solid #364060; border-radius: 4px; background: #12161e; }
QTabBar::tab {
    background: #1c2230;
    color: #8090a8;
    padding: 8px 20px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #2a3f66; color: #dce4f0; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #222c3e; }

/* --- Group Boxes --- */
QGroupBox {
    border: 1.5px solid #364060;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: 600;
    color: #a0b8e0;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }

/* --- Labels --- */
QLabel#label_title { font-size: 18px; font-weight: 700; color: #a0b8e0; }
QLabel#label_subtitle { font-size: 13px; color: #6a7a98; }

/* --- Frames --- */
QFrame#card { background: #1c2230; border: 1px solid #2e3c50; border-radius: 8px; }
QFrame#status_bar_frame { background-color: #0f1624; color: #dce4f0; min-height: 32px; }

/* --- Status indicators --- */
QLabel#indicator_ok  { background-color: #145230; color: #90e0b0; border-radius: 4px; padding: 4px 12px; }
QLabel#indicator_ng  { background-color: #7d2020; color: #f0a0a0; border-radius: 4px; padding: 4px 12px; }
QLabel#indicator_idle{ background-color: #2c3040; color: #8090a8; border-radius: 4px; padding: 4px 12px; }
QLabel#plc_connected    { background-color: #145230; color: #90e0b0; }
QLabel#plc_disconnected { background-color: #7d2020; color: #f0a0a0; }

/* --- Scroll bars --- */
QScrollBar:vertical   { border: none; background: #12161e; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #2a3f66; min-height: 20px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; }
QScrollBar:horizontal { border: none; background: #12161e; height: 8px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #2a3f66; min-width: 20px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { border: none; background: none; }

/* --- Form labels alignment --- */
QFormLayout QLabel { min-width: 160px; }
"""


class ThemeManager(QObject):
    """Singleton. Call ThemeManager.instance() everywhere."""

    theme_changed = pyqtSignal(str)   # emits "dark" or "light"

    _instance: "ThemeManager | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._theme = "light"

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def current(self) -> str:
        return self._theme

    def is_dark(self) -> bool:
        return self._theme == "dark"

    def toggle(self) -> None:
        self._theme = "dark" if self._theme == "light" else "light"
        self._apply()
        self.theme_changed.emit(self._theme)

    def set_theme(self, theme: str) -> None:
        if theme not in ("dark", "light"):
            return
        self._theme = theme
        self._apply()
        self.theme_changed.emit(self._theme)

    def _apply(self) -> None:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(DARK_QSS if self._theme == "dark" else LIGHT_QSS)
