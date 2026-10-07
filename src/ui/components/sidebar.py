"""
sidebar.py — Universal PLC Monitor
Industrial SCADA/HMI navigation sidebar with role-based access control,
SVG vector icons, section grouping, and expandable/collapsible support.
"""
from __future__ import annotations

import logging
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QSpacerItem, QSizePolicy, QFrame as QFrameType)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from src.utils.constants import NAV_ITEMS, NAV_SECTIONS
from src.utils.icons import get_icon

logger = logging.getLogger(__name__)

COLLAPSED_WIDTH = 64
EXPANDED_WIDTH = 176

# Icon tinting — slate idle, cyan active (SCADA palette)
IDLE_COLOR = "#94A3B8"
ACTIVE_COLOR = "#22D3EE"
ICON_SIZE = 21


def render_icon_pixmap(svg_body: str, color: str, size: int = ICON_SIZE) -> QPixmap:
    """Render a single-color SVG pixmap."""
    svg = get_icon(svg_body, color)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


class SidebarRow(QPushButton):
    """Single sidebar entry: left accent indicator + SVG icon + title text."""

    def __init__(self, icon_name: str, label: str, parent: QFrame) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self.setObjectName("nav_row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)
        self.setToolTip(label)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(9)

        self.indicator = QFrame()
        self.indicator.setObjectName("nav_indicator")
        self.indicator.setFixedWidth(3)
        self.indicator.setVisible(False)
        lay.addWidget(self.indicator)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("nav_row_icon")
        self.icon_label.setPixmap(render_icon_pixmap(icon_name, IDLE_COLOR))
        self.icon_label.setFixedSize(QSize(ICON_SIZE, ICON_SIZE))
        lay.addWidget(self.icon_label)

        self.text_label = QLabel(label)
        self.text_label.setObjectName("nav_row_text")
        lay.addWidget(self.text_label)
        lay.addStretch(1)

    def set_active(self, active: bool, pixmap: QPixmap | None = None) -> None:
        self.indicator.setVisible(active)
        self.setProperty("active", active)
        if pixmap is not None:
            self.icon_label.setPixmap(pixmap)
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QFrame):
    nav_clicked = pyqtSignal(str)
    theme_toggle = pyqtSignal()
    logout = pyqtSignal()

    def __init__(self, app_state: any) -> None:
        super().__init__()
        self.app_state = app_state
        self.setObjectName("sidebar")
        self.setFixedWidth(EXPANDED_WIDTH)
        self.setAccessibleName("Navigation sidebar")

        self._rows: dict[str, SidebarRow] = {}
        self._section_headers: dict[str, QLabel] = {}
        self._is_expanded = True  # Always expanded
        self._text_labels: list[QLabel] = []
        self.toggle_btn: QPushButton

        self._init_ui()

    # ─── UI construction ────────────────────────────────────────────────

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Brand header block
        brand = self._make_brand()
        layout.addWidget(brand, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(10)

        by_page = {p: (icon, label, roles) for p, icon, label, roles in NAV_ITEMS}

        # Sectioned navigation
        for title, page_ids in NAV_SECTIONS:
            header = self._make_section_header(title)
            self._section_headers[title] = header
            layout.addWidget(header)
            for page_id in page_ids:
                if page_id not in by_page:
                    continue
                icon_name, label, _roles = by_page[page_id]
                row = SidebarRow(icon_name, label, self)
                self._rows[page_id] = row
                self._text_labels.append(row.text_label)
                row.released.connect(lambda p=page_id: self._nav(p))
                layout.addWidget(row)

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum,
                                         QSizePolicy.Policy.Expanding))

        # Toggle button - hidden since always expanded
        self.toggle_btn = QPushButton("▶")
        self.toggle_btn.setObjectName("nav_toggle_btn")
        self.toggle_btn.setToolTip("Expand sidebar")
        self.toggle_btn.setVisible(False)  # Hidden: always expanded
        self.toggle_btn.clicked.connect(self._toggle_expand)
        layout.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Bottom separator
        layout.addWidget(self._make_separator(), alignment=Qt.AlignmentFlag.AlignHCenter)

        # Theme row (system access)
        theme_row = SidebarRow("theme", "Theme", self)
        theme_row.released.connect(self._theme)
        theme_row.setAccessibleName("Toggle theme")
        self._theme_row = theme_row
        layout.addWidget(theme_row)

        # Logout row
        logout_row = SidebarRow("logout", "Logout", self)
        logout_row.released.connect(self._logout)
        logout_row.setAccessibleName("Logout")
        self._logout_row = logout_row
        layout.addWidget(logout_row)

    def _make_brand(self) -> QFrame:
        brand = QFrame()
        brand.setObjectName("nav_brand")
        lay = QVBoxLayout(brand)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(3)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("nav_brand_icon")
        icon_lbl.setPixmap(render_icon_pixmap("model", ACTIVE_COLOR, 26))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        self.brand_name = QLabel("PLC MONITOR")
        self.brand_name.setObjectName("nav_brand_name")
        self.brand_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.brand_name)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("nav_status_dot")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_connection_status(False)
        lay.addWidget(self.status_dot)

        self.brand_name.setVisible(True)  # Always visible since expanded
        self.status_dot.setVisible(True)  # Always visible since expanded
        return brand

    def _make_section_header(self, title: str) -> QLabel:
        lbl = QLabel(title)
        lbl.setObjectName("nav_section")
        lbl.setContentsMargins(14, 8, 0, 2)
        lbl.setVisible(True)  # Always visible since expanded
        return lbl

    def _make_separator(self) -> QFrameType:
        sep = QFrameType()
        sep.setObjectName("nav_separator")
        sep.setFixedHeight(1)
        sep.setFixedWidth(48)
        return sep

    # ─── Signals / behavior ─────────────────────────────────────────────

    def _nav(self, page_id: str) -> None:
        if any(it[0] == page_id for it in NAV_ITEMS):
            self.nav_clicked.emit(page_id)

    def _theme(self) -> None:
        self.theme_toggle.emit()

    def _logout(self) -> None:
        self.logout.emit()

    @property
    def theme_btn(self) -> SidebarRow:
        return self._theme_row

    @property
    def logout_btn(self) -> SidebarRow:
        return self._logout_row

    def set_connection_status(self, connected: bool) -> None:
        connected = bool(connected)
        if hasattr(self, "status_dot"):
            self.status_dot.setProperty("online", connected)
            self.status_dot.setToolTip("PLC online" if connected else "PLC offline")
            self.status_dot.style().unpolish(self.status_dot)
            self.status_dot.style().polish(self.status_dot)

    def rebuild_for_role(self, role: str) -> None:
        """Show/hide items based on role access list in NAV_ITEMS."""
        page_roles = {it[0]: it[3] for it in NAV_ITEMS}
        for pid, row in self._rows.items():
            row.setVisible(role in page_roles.get(pid, []))
        # Hide section headers with no visible items (always show if any visible)
        for title, page_ids in NAV_SECTIONS:
            any_visible = any(
                pid in self._rows and self._rows[pid].isVisible() for pid in page_ids
            )
            header = self._section_headers.get(title)
            if header is not None:
                header.setVisible(any_visible)

    def set_active(self, page_name: str) -> None:
        """Highlight the active item with cyan icon + left accent bar."""
        for pid, row in self._rows.items():
            is_active = (pid == page_name)
            row.set_active(is_active, render_icon_pixmap(
                row._icon_name, ACTIVE_COLOR if is_active else IDLE_COLOR))
        self._theme_row.set_active(False)
        self._logout_row.set_active(False)

    # ─── Expand / collapse ──────────────────────────────────────────────

    def _toggle_expand(self) -> None:
        self._is_expanded = not self._is_expanded
        target_width = EXPANDED_WIDTH if self._is_expanded else COLLAPSED_WIDTH

        for anim_attr in (b"maximumWidth", b"minimumWidth"):
            anim = QPropertyAnimation(self, anim_attr)
            anim.setDuration(180)
            anim.setStartValue(self.width())
            anim.setEndValue(target_width)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.start()
            setattr(self, "_anim", anim)

        self._toggle_expanded_labels()
        self.toggle_btn.setText("◀" if self._is_expanded else "▶")
        self.toggle_btn.setToolTip(
            "Collapse sidebar" if self._is_expanded else "Expand sidebar")

    def _toggle_expanded_labels(self) -> None:
        # Always show labels since we're always expanded
        for lbl in self._text_labels:
            lbl.setVisible(True)
        for header in self._section_headers.values():
            header.setVisible(True)
        self.brand_name.setVisible(True)
        self.status_dot.setVisible(True)