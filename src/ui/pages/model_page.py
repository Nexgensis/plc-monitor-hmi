"""
model_page.py — Universal PLC Monitor
The entry page after login where operators select the switch model to be tested.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QGridLayout, QProgressBar,
                             QScrollArea)
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState
from src.utils.constants import PAGE_CONFIG

logger = logging.getLogger(__name__)


class ModelPage(QWidget):
    """
    Model selection dashboard with PLC status verification and 
    configuration push simulation.
    """

    def __init__(self, app_state: AppState, on_model_confirmed: Callable) -> None:
        super().__init__()
        self.app_state = app_state
        self.on_model_confirmed = on_model_confirmed
        self._selected_model_id: Optional[int] = None
        self.setAccessibleName("Model selection page")
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("SELECT MODEL")
        title.setObjectName("page_title")
        header.addWidget(title)
        
        subtitle = QLabel("Choose the switch model to begin testing")
        subtitle.setObjectName("page_subtitle")
        header.addWidget(subtitle)
        layout.addLayout(header)

        self.no_models_banner = QFrame()
        self.no_models_banner.setObjectName("warning_banner")
        banner_layout = QHBoxLayout(self.no_models_banner)
        banner_layout.addWidget(QLabel("⚠ No models configured in the database."))
        btn_go_config = QPushButton("⚙ Go to CONFIG")
        btn_go_config.setObjectName("btn_warning")
        btn_go_config.clicked.connect(lambda: self._navigate(PAGE_CONFIG))
        banner_layout.addWidget(btn_go_config)
        self.no_models_banner.setVisible(False)
        layout.addWidget(self.no_models_banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("model_scroll")
        
        container = QWidget()
        container.setObjectName("model_container")
        self.grid = QGridLayout(container)
        self.grid.setSpacing(20)
        self.grid.setContentsMargins(10, 10, 10, 10)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self.status_card = QFrame()
        self.status_card.setObjectName("status_card")
        status_layout = QVBoxLayout(self.status_card)
        
        self.plc_status_lbl = QLabel("PLC Status: Verifying...")
        self.plc_status_lbl.setObjectName("model_plc_status")
        self.plc_status_lbl.setProperty("status", "ok")
        status_layout.addWidget(self.plc_status_lbl)
        
        self.push_container = QWidget()
        push_layout = QVBoxLayout(self.push_container)
        push_layout.setContentsMargins(0, 5, 0, 0)
        self.push_lbl = QLabel("Ready to sync model configuration.")
        self.push_lbl.setObjectName("model_push_lbl")
        self.push_lbl.setProperty("status", "ok")
        push_layout.addWidget(self.push_lbl)
        self.push_bar = QProgressBar()
        self.push_bar.setFixedHeight(8)
        self.push_bar.setObjectName("model_push_bar")
        self.push_bar.setTextVisible(False)
        push_layout.addWidget(self.push_bar)
        self.push_container.setVisible(False)
        status_layout.addWidget(self.push_container)
        
        layout.addWidget(self.status_card)

        self.btn_start = QPushButton("▶ START AUTO TEST")
        self.btn_start.setObjectName("btn_success")
        self.btn_start.setFixedHeight(42)
        self.btn_start.setEnabled(False)
        self.btn_start.setAccessibleName("Start auto test")
        self.btn_start.setToolTip("Start automatic testing with the selected model")
        self.btn_start.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.btn_start)

    def on_page_shown(self) -> None:
        self._refresh_models()
        self._check_plc_status()

    def _refresh_models(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        models = self.app_state.model_repo.get_all_models()
        self.no_models_banner.setVisible(len(models) == 0)

        for i, m in enumerate(models):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setObjectName("model_btn")
            btn.setAccessibleName(m["name"])
            btn.setToolTip(f"Select model: {m['name']}")
            btn_layout = QVBoxLayout(btn)
            btn_layout.setContentsMargins(16, 14, 16, 14)
            btn_layout.setSpacing(6)

            # Top row: name + active status pill
            top_row = QHBoxLayout()
            top_row.setSpacing(6)
            name_lbl = QLabel(m["name"])
            name_lbl.setObjectName("model_page_title")
            top_row.addWidget(name_lbl)
            top_row.addStretch()

            active = m.get("is_active", 1)
            status_pill = QLabel("ACTIVE" if active else "INACTIVE")
            status_pill.setObjectName("badge_pill")
            status_pill.setProperty("pill_kind", "status")
            status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top_row.addWidget(status_pill)
            btn_layout.addLayout(top_row)

            desc_lbl = QLabel(m["model_number"] or m["description"] or "Standard Config")
            desc_lbl.setObjectName("model_page_desc")
            desc_lbl.setWordWrap(True)
            btn_layout.addWidget(desc_lbl)

            # Footer meta row
            try:
                mapping_count = len(self.app_state.map_repo.get_model_mappings(m["id"], enabled_only=True))
            except Exception:
                mapping_count = 0
            created = (m.get("created_at") or "")[:10] or "—"
            meta_lbl = QLabel(f"{mapping_count} params   ·   {created}")
            meta_lbl.setObjectName("model_page_meta")
            btn_layout.addWidget(meta_lbl)

            model_id = m["id"]
            btn.setProperty("model_id", model_id)
            btn.clicked.connect(lambda _, mid=model_id: self._on_model_selected(mid))
            
            row, col = divmod(i, 2)
            self.grid.addWidget(btn, row, col)

    def _check_plc_status(self) -> None:
        if not self.app_state.is_plc_configured:
            self.plc_status_lbl.setText("⚠ PLC connection not configured. Please contact Administrator.")
            self.plc_status_lbl.setProperty("status", "error")
        elif not self.app_state.is_plc_connected:
            self.plc_status_lbl.setText("● PLC offline. Attempting to reconnect...")
            self.plc_status_lbl.setProperty("status", "warning")
        else:
            self.plc_status_lbl.setText("✓ PLC Online & Ready")
            self.plc_status_lbl.setProperty("status", "ok")
        self.plc_status_lbl.style().unpolish(self.plc_status_lbl)
        self.plc_status_lbl.style().polish(self.plc_status_lbl)

    def _on_model_selected(self, model_id: int) -> None:
        self._selected_model_id = model_id
        
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(w.property("model_id") == model_id)
        
        self.push_container.setVisible(True)
        self.push_bar.setRange(0, 0)
        self.push_lbl.setText("Syncing model configuration...")
        self.push_lbl.setProperty("status", "warning")
        self.push_lbl.style().unpolish(self.push_lbl)
        self.push_lbl.style().polish(self.push_lbl)
        self.btn_start.setEnabled(False)

        try:
            self.app_state.set_model(model_id)
            self.push_bar.setRange(0, 100)
            self.push_bar.setValue(100)
            self.push_lbl.setText("✓ Configuration synced successfully")
            self.push_lbl.setProperty("status", "ok")
            self.push_lbl.style().unpolish(self.push_lbl)
            self.push_lbl.style().polish(self.push_lbl)
            self.btn_start.setEnabled(True)
        except Exception as e:
            self.push_bar.setRange(0, 100)
            self.push_bar.setValue(0)
            self.push_lbl.setText(f"✗ Sync failed: {e}")
            self.push_lbl.setProperty("status", "error")
            self.push_lbl.style().unpolish(self.push_lbl)
            self.push_lbl.style().polish(self.push_lbl)
            self.btn_start.setEnabled(False)

    def _on_start_clicked(self) -> None:
        self.on_model_confirmed()

    def _navigate(self, page: str) -> None:
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(page)
