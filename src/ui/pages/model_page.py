"""
model_page.py — Universal PLC Monitor
The entry page after login where operators select the switch model to be tested.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QGridLayout, QProgressBar,
                             QScrollArea, QGroupBox, QTableWidget, QTableWidgetItem,
                             QHeaderView)
from PyQt6.QtCore import Qt, QTimer

from src.ui.app_state import AppState
from src.utils.constants import PAGE_TEST, PAGE_CONFIG

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
        self._push_timer = QTimer(self)
        self._push_timer.timeout.connect(self._on_push_step)
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 1. Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("SELECT MODEL")
        title.setObjectName("page_title")
        header.addWidget(title)
        
        subtitle = QLabel("Choose the switch model to begin testing")
        subtitle.setObjectName("page_subtitle")
        header.addWidget(subtitle)
        layout.addLayout(header)

        # 2. No Models Warning (Conditional)
        self.no_models_banner = QFrame()
        self.no_models_banner.setObjectName("warning_banner")
        banner_layout = QHBoxLayout(self.no_models_banner)
        banner_layout.addWidget(QLabel("⚠ No models configured in the database."))
        btn_go_config = QPushButton("Go to CONFIG")
        btn_go_config.setObjectName("btn_warning")
        btn_go_config.clicked.connect(lambda: self._navigate(PAGE_CONFIG))
        banner_layout.addWidget(btn_go_config)
        self.no_models_banner.setVisible(False)
        layout.addWidget(self.no_models_banner)

        # 3. Model Grid (Scrollable)
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

        # 4. PLC & Push Status Area
        self.status_card = QFrame()
        self.status_card.setObjectName("status_card")
        status_layout = QVBoxLayout(self.status_card)
        
        self.plc_status_lbl = QLabel("PLC Status: Verifying...")
        self.plc_status_lbl.setObjectName("plc_status_text")
        status_layout.addWidget(self.plc_status_lbl)
        
        self.push_container = QWidget()
        push_layout = QVBoxLayout(self.push_container)
        push_layout.setContentsMargins(0, 5, 0, 0)
        self.push_lbl = QLabel("Ready to sync model configuration.")
        push_layout.addWidget(self.push_lbl)
        self.push_bar = QProgressBar()
        self.push_bar.setFixedHeight(8)
        self.push_bar.setTextVisible(False)
        push_layout.addWidget(self.push_bar)
        self.push_container.setVisible(False)
        status_layout.addWidget(self.push_container)

        # 5. Register Summary (Collapsible)
        self.summary_box = QGroupBox("Selected Model Configuration")
        self.summary_box.setVisible(False)
        summary_layout = QVBoxLayout(self.summary_box)
        self.reg_table = QTableWidget(0, 4)
        self.reg_table.setHorizontalHeaderLabels(["Name", "Address", "Type", "Role"])
        self.reg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.reg_table.setFixedHeight(180)
        summary_layout.addWidget(self.reg_table)
        status_layout.addWidget(self.summary_box)
        
        layout.addWidget(self.status_card)

        # 6. Start Button
        self.btn_start = QPushButton("▶ START AUTO TEST")
        self.btn_start.setObjectName("btn_success")
        self.btn_start.setFixedHeight(56)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.btn_start)

    def on_page_shown(self) -> None:
        """Rebuild list and check status."""
        self._refresh_models()
        self._check_plc_status()

    def _refresh_models(self) -> None:
        """Fetch all models from DB and create buttons."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        models = self.app_state.model_repo.get_all_models()
        self.no_models_banner.setVisible(len(models) == 0)

        for i, m in enumerate(models):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setObjectName("model_btn")
            btn_layout = QVBoxLayout(btn)
            
            name_lbl = QLabel(m["name"])
            name_lbl.setStyleSheet("font-size: 18px; font-weight: bold; background:transparent;")
            btn_layout.addWidget(name_lbl)
            
            desc_lbl = QLabel(m["model_number"] or m["description"] or "Standard Config")
            desc_lbl.setStyleSheet("font-size: 12px; color: #5a7a9a; background:transparent;")
            btn_layout.addWidget(desc_lbl)
            
            model_id = m["id"]
            btn.clicked.connect(lambda _, mid=model_id: self._on_model_selected(mid))
            
            row, col = divmod(i, 2)
            self.grid.addWidget(btn, row, col)

    def _check_plc_status(self) -> None:
        if not self.app_state.is_plc_configured:
            self.plc_status_lbl.setText("⚠ PLC connection not configured. Please contact Administrator.")
            self.plc_status_lbl.setStyleSheet("color: #ef4444;")
        elif not self.app_state.is_plc_connected:
            self.plc_status_lbl.setText("● PLC offline. Attempting to reconnect...")
            self.plc_status_lbl.setStyleSheet("color: #f59e0b;")
        else:
            self.plc_status_lbl.setText("✓ PLC Online & Ready")
            self.plc_status_lbl.setStyleSheet("color: #22c55e;")

    def _on_model_selected(self, model_id: int) -> None:
        self._selected_model_id = model_id
        
        # UI Feedback: Uncheck others
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(False)
        
        # Start Sync Simulation
        self.push_container.setVisible(True)
        self.push_bar.setValue(0)
        self.push_lbl.setText("Initializing sync...")
        self.push_lbl.setStyleSheet("color: #f59e0b;")
        self._push_timer.start(50)
        self.btn_start.setEnabled(False)

        # Load Summary
        self._load_register_summary(model_id)

    def _on_push_step(self) -> None:
        val = self.push_bar.value() + 5
        self.push_bar.setValue(val)
        
        if val >= 100:
            self._push_timer.stop()
            self.push_lbl.setText("✓ Configuration synced successfully")
            self.push_lbl.setStyleSheet("color: #22c55e;")
            self.btn_start.setEnabled(True)
            # Actually set the model in app state now
            self.app_state.set_model(self._selected_model_id)

    def _load_register_summary(self, model_id: int) -> None:
        self.summary_box.setVisible(True)
        mappings = self.app_state.map_repo.get_model_mappings(model_id, enabled_only=True)
        
        self.reg_table.setRowCount(min(len(mappings), 8))
        for i, m in enumerate(mappings[:8]):
            self.reg_table.setItem(i, 0, QTableWidgetItem(m["display_name"]))
            self.reg_table.setItem(i, 1, QTableWidgetItem(f"D{m['register_address']}"))
            self.reg_table.setItem(i, 2, QTableWidgetItem(m["register_type"]))
            self.reg_table.setItem(i, 3, QTableWidgetItem(m["role"]))

    def _on_start_clicked(self) -> None:
        """Navigate to test page via callback."""
        self.on_model_confirmed()

    def _navigate(self, page: str) -> None:
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(page)
