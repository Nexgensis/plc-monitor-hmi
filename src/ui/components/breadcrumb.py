"""
breadcrumb.py — Universal PLC Monitor
Breadcrumb navigation widget for showing the current page path.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt
from src.utils.constants import (
    PAGE_MODEL, PAGE_TEST, PAGE_MANUAL, PAGE_CONFIG,
    PAGE_IO_LIST, PAGE_REPORTS, PAGE_SETTINGS
)

PAGE_LABELS = {
    PAGE_MODEL: "Home",
    PAGE_TEST: "Test",
    PAGE_MANUAL: "Manual",
    PAGE_CONFIG: "Config",
    PAGE_IO_LIST: "I/O List",
    PAGE_REPORTS: "Reports",
    PAGE_SETTINGS: "Settings",
}

PAGE_HIERARCHY = {
    PAGE_MODEL: [PAGE_MODEL],
    PAGE_TEST: [PAGE_MODEL, PAGE_TEST],
    PAGE_MANUAL: [PAGE_MODEL, PAGE_MANUAL],
    PAGE_CONFIG: [PAGE_MODEL, PAGE_CONFIG],
    PAGE_IO_LIST: [PAGE_MODEL, PAGE_IO_LIST],
    PAGE_REPORTS: [PAGE_MODEL, PAGE_REPORTS],
    PAGE_SETTINGS: [PAGE_MODEL, PAGE_SETTINGS],
}


class Breadcrumb(QFrame):
    crumb_clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("breadcrumb")
        self.setAccessibleName("Breadcrumb navigation")
        self.setFixedHeight(32)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(15, 0, 15, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._current_page = ""

    def update_path(self, page_name: str) -> None:
        if page_name == self._current_page:
            return
        self._current_page = page_name
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            old = item.widget()
            if old is not None:
                # hide immediately: deleteLater() is deferred until the event
                # loop runs, and an unhidden stale widget would overlay the
                # rebuilt crumbs (visible as doubled text).
                old.hide()
                old.deleteLater()

        crumbs = PAGE_HIERARCHY.get(self._current_page, [self._current_page])
        for i, page in enumerate(crumbs):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("breadcrumb_sep")
                self._layout.addWidget(sep)

            label = PAGE_LABELS.get(page, page)
            if page == self._current_page:
                lbl = QLabel(label)
                lbl.setObjectName("breadcrumb_current")
                self._layout.addWidget(lbl)
            else:
                btn = QPushButton(label)
                btn.setObjectName("breadcrumb_link")
                btn.clicked.connect(lambda checked, p=page: self.crumb_clicked.emit(p))
                self._layout.addWidget(btn)

        self._layout.addStretch()
