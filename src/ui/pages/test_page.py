"""
test_page.py — Universal PLC Monitor
The primary testing dashboard. Displays real-time parameters,
test results, cycle counters, and control buttons.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QGridLayout, 
                             QMessageBox, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.ui.app_state import AppState
from src.logic.pass_fail_evaluator import PassFailEvaluator, EvalResult
from src.ui.components.param_card import ParamCard
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.plc.data_model import RegisterReading
from src.utils.constants import (
    RESULT_PASS, RESULT_FAIL, RESULT_PENDING, RESULT_BYPASS, RESULT_RUNNING,
    MAX_DASHBOARD_CARDS, ROLE_COUNTER,
    CTRL_START_TEST, CTRL_STOP_TEST, CTRL_RESET_BATCH, CTRL_RESET_COUNTER,
    CTRL_ACK, CTRL_CUSTOM
)

logger = logging.getLogger(__name__)


class TestPage(QWidget):
    """
    Main testing dashboard showing parameter cards, overall result,
    cycle time, and action buttons.
    """

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self._cards: Dict[int, ParamCard] = {}
        self._card_order: List[int] = []
        self._evaluator: Optional[PassFailEvaluator] = None
        self._is_running = False
        self._session_id: Optional[int] = None
        self._last_test_start: Optional[datetime] = None
        
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- LEFT COLUMN: Main Dashboard Area ---
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        layout.addLayout(left_col, stretch=1)

        # 1. Model Banner & Quick Controls
        self.banner = QFrame()
        self.banner.setFixedHeight(50)
        self.banner.setObjectName("model_banner")
        banner_layout = QHBoxLayout(self.banner)
        
        self.model_name_lbl = QLabel("NO MODEL SELECTED")
        self.model_name_lbl.setObjectName("model_banner_text")
        banner_layout.addWidget(self.model_name_lbl)
        
        banner_layout.addStretch()

        self.btn_start = QPushButton("▶ START TEST")
        self.btn_start.setObjectName("btn_success")
        self.btn_start.setMinimumWidth(140)
        self.btn_start.clicked.connect(self._on_start_clicked)
        banner_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■ STOP")
        self.btn_stop.setObjectName("btn_danger")
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_stop.setVisible(False)
        banner_layout.addWidget(self.btn_stop)
        
        left_col.addWidget(self.banner)

        # 2. Cards Grid Area
        self.cards_area = QFrame()
        self.cards_area.setObjectName("cards_container")
        self.cards_grid = QGridLayout(self.cards_area)
        self.cards_grid.setSpacing(10)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        
        self.empty_lbl = QLabel("Please select a model from the Home screen.")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setObjectName("empty_dashboard_label")
        self.cards_grid.addWidget(self.empty_lbl, 0, 0)
        
        left_col.addWidget(self.cards_area, stretch=1)

        # 3. Dynamic Control Buttons Row
        self.ctrl_btn_row = QHBoxLayout()
        self.ctrl_btn_row.setSpacing(10)
        left_col.addLayout(self.ctrl_btn_row)

        # --- RIGHT COLUMN: Status & Counters ---
        right_widget = QWidget()
        right_widget.setFixedWidth(200)
        right_col = QVBoxLayout(right_widget)
        right_col.setSpacing(10)
        right_col.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(right_widget)

        # 1. Overall Result
        res_frame = QFrame()
        res_frame.setFixedHeight(100)
        res_frame.setObjectName("overall_result_card")
        res_layout = QVBoxLayout(res_frame)
        
        lbl_title = QLabel("OVERALL RESULT")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setObjectName("small_header_label")
        res_layout.addWidget(lbl_title)
        
        self.overall_lbl = QLabel("● PENDING")
        self.overall_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_lbl.setObjectName("result_pending")
        res_layout.addWidget(self.overall_lbl)
        
        right_col.addWidget(res_frame)

        # 2. Counters Area
        self.counters_area = QVBoxLayout()
        self.counters_area.setSpacing(8)
        right_col.addLayout(self.counters_area)
        right_col.addStretch()

        # 3. Cycle Time
        time_frame = QFrame()
        time_frame.setFixedHeight(60)
        time_frame.setObjectName("cycle_time_card")
        time_layout = QVBoxLayout(time_frame)
        
        lbl_cycle = QLabel("CYCLE TIME")
        lbl_cycle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_cycle.setObjectName("small_header_label")
        time_layout.addWidget(lbl_cycle)
        
        self.cycle_lbl = QLabel("0.0 s")
        self.cycle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cycle_lbl.setObjectName("cycle_time_value")
        time_layout.addWidget(self.cycle_lbl)
        
        right_col.addWidget(time_frame)

    def on_page_shown(self) -> None:
        """Called when the stack switches to this page."""
        if self.app_state.current_model_id:
            self.load_model(self.app_state.current_model_id)
        
        # Connect real-time signals
        cm = self.app_state.connection_manager
        if cm:
            try:
                cm.readings_updated.connect(self.on_readings_updated)
                cm.message_changed.connect(self.on_message_changed)
            except RuntimeError:
                pass # Already connected
        
        self.on_plc_state_changed(self.app_state.is_plc_connected)

    def load_model(self, model_id: int) -> None:
        """Initialize dashboard for the specific model."""
        regs = self.app_state.dashboard_registers
        model = self.app_state.current_model
        
        if not model:
            self.model_name_lbl.setText("NO MODEL SELECTED")
            return

        self.model_name_lbl.setText(f"{model['name']} TESTING")
        self.empty_lbl.setVisible(not regs)
        
        # 1. Setup Evaluator
        self._evaluator = PassFailEvaluator(regs)
        
        # 2. Build Card Grid
        self._build_card_grid(regs)
        
        # 3. Setup Action Buttons
        self._load_control_buttons()
        
        # 4. Setup Counters
        self._load_counters()

    def _build_card_grid(self, regs: list[dict]) -> None:
        """Dynamic grid sizing based on card count."""
        # Clear existing
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            w = item.widget()
            if w and w != self.empty_lbl:
                w.deleteLater()
        self._cards.clear()
        self._card_order.clear()

        n = len(regs)
        if n == 0: return
        
        # Determine grid density
        if n <= 4:   cols, mode = 2, "large"
        elif n <= 8: cols, mode = 3, "medium"
        else:        cols, mode = 4, "small"

        can_drag = self.app_state.is_admin()

        for i, reg in enumerate(regs[:MAX_DASHBOARD_CARDS]):
            rid = reg["register_id"]
            card = ParamCard(
                register_id  = rid,
                display_name = reg.get("display_name") or reg["name"],
                group_name   = reg.get("group_name", ""),
                unit         = reg.get("unit", ""),
                theme        = self.app_state.current_theme,
                can_drag     = can_drag
            )
            card.set_size_mode(mode)
            card.drag_completed.connect(self._on_card_dragged)
            
            row, col = divmod(i, cols)
            self.cards_grid.addWidget(card, row, col)
            self._cards[rid] = card
            self._card_order.append(rid)

    def _load_control_buttons(self) -> None:
        """Build custom action buttons from database."""
        while self.ctrl_btn_row.count():
            item = self.ctrl_btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        controls = self.app_state.control_repo.get_all_controls()
        # Buttons for test dashboard (excluding start/stop which are in banner)
        action_types = [CTRL_RESET_BATCH, CTRL_RESET_COUNTER, CTRL_ACK, CTRL_CUSTOM]
        
        for ctrl in controls:
            if ctrl["control_type"] in action_types:
                btn = QPushButton(ctrl["name"])
                btn.setObjectName("btn_secondary")
                btn.setFixedHeight(32)
                btn.clicked.connect(lambda _, c=ctrl: self._execute_control(c))
                self.ctrl_btn_row.addWidget(btn)
        
        # Also check for STOP_TEST to show in banner
        stop_ctrl = self.app_state.control_repo.get_control_by_type(CTRL_STOP_TEST)
        self.btn_stop.setVisible(bool(stop_ctrl))

    def _load_counters(self) -> None:
        """Build counter widgets from model mapping."""
        while self.counters_area.count():
            item = self.counters_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        dashboard_regs = self.app_state.dashboard_registers
        counters = [r for r in dashboard_regs if r.get("role") == ROLE_COUNTER]
        
        if not counters:
            lbl = QLabel("No counters configured.")
            lbl.setObjectName("no_counters_label")
            self.counters_area.addWidget(lbl)
            return

        for c in counters:
            frame = QFrame()
            frame.setObjectName("counter_card")
            c_layout = QVBoxLayout(frame)
            c_layout.setSpacing(0)
            
            val_lbl = QLabel("0")
            val_lbl.setObjectName(f"counter_val_{c['register_id']}")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setProperty("type", "counter_value")
            c_layout.addWidget(val_lbl)
            
            name_lbl = QLabel(c["display_name"] or c["name"])
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setObjectName("counter_name_label")
            c_layout.addWidget(name_lbl)
            
            self.counters_area.addWidget(frame)

    # --- Real-time Handlers ---

    def on_readings_updated(self, readings: Dict[int, RegisterReading]) -> None:
        """Main update loop from ConnectionManager."""
        if not self._evaluator: return
        
        # 1. Evaluate results
        eval_results = self._evaluator.evaluate_all(readings, self._is_running)
        
        # 2. Update cards
        for res in eval_results:
            card = self._cards.get(res.register_id)
            if card:
                card.update_result(res)
        
        # 3. Update overall status
        self._update_overall_status(eval_results)
        
        # 4. Update counters
        for reg_id, reading in readings.items():
            lbl = self.findChild(QLabel, f"counter_val_{reg_id}")
            if lbl:
                lbl.setText(str(int(reading.display_value)))

        # 5. Update cycle time if running
        if self._is_running and self._last_test_start:
            elapsed = (datetime.now() - self._last_test_start).total_seconds()
            self.cycle_lbl.setText(f"{elapsed:.1f} s")

    def on_message_changed(self, val: int, text: str, color: str) -> None:
        """
        D21 / Message register changed. 
        Determines when a test cycle starts or stops.
        """
        was_running = self._is_running
        
        # We consider the machine "Running" if the message value is > 1
        # (0=IDLE/READY, 1=PASS/COMPLETED, others=Error or Sequence)
        # Note: This logic can be moved to MessageRegisterRepo config later.
        self._is_running = (val > 1)
        
        if not was_running and self._is_running:
            # Cycle Started
            self._on_cycle_start()
        elif was_running and not self._is_running:
            # Cycle Stopped/Finished
            self._on_cycle_end()

    def _on_cycle_start(self) -> None:
        logger.info("Test cycle start detected via PLC message register")
        self._last_test_start = datetime.now()
        self.btn_start.setEnabled(False)
        # Reset visual state
        for card in self._cards.values():
            card.reset()
        
        # Open Session in DB (future implementation)
        # self._session_id = self.app_state.session_repo.open_session(...)

    def _on_cycle_end(self) -> None:
        logger.info("Test cycle end detected")
        self.btn_start.setEnabled(True)
        # Close Session and save results (future implementation)

    def on_plc_state_changed(self, connected: bool) -> None:
        """Updates banner styling based on connection status."""
        self.banner.setProperty("connected", connected)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.btn_start.setVisible(connected)

    def _update_overall_status(self, results: List[EvalResult]) -> None:
        """Determines the large status label on the right."""
        if self._is_running:
            overall = RESULT_RUNNING
        else:
            # Only consider non-bypass results for overall PASS/FAIL
            active = [r for r in results if r.result not in (RESULT_BYPASS, RESULT_PENDING)]
            if not active:
                overall = RESULT_PENDING
            elif any(r.result == RESULT_FAIL for r in active):
                overall = RESULT_FAIL
            elif all(r.result == RESULT_PASS for r in active):
                overall = RESULT_PASS
            else:
                overall = RESULT_PENDING

        self.overall_lbl.setText(f"● {overall}")
        self.overall_lbl.setObjectName(f"result_{overall.lower()}")
        
        # Force Style refresh
        self.overall_lbl.style().unpolish(self.overall_lbl)
        self.overall_lbl.style().polish(self.overall_lbl)

    # --- Control Actions ---

    def _on_start_clicked(self) -> None:
        start_ctrl = self.app_state.control_repo.get_control_by_type(CTRL_START_TEST)
        if not start_ctrl:
            QMessageBox.warning(self, "Config Missing", "Start Test register is not configured in CONFIG.")
            return
        self._execute_control(start_ctrl)

    def _on_stop_clicked(self) -> None:
        stop_ctrl = self.app_state.control_repo.get_control_by_type(CTRL_STOP_TEST)
        if stop_ctrl:
            self._execute_control(stop_ctrl)

    def _execute_control(self, control: dict) -> None:
        """Safe execution of PLC write with confirmation if needed."""
        if control.get("confirm_required"):
            if not ConfirmDialog.ask(self, "PLC Control", f"Are you sure you want to trigger {control['name']}?"):
                return
        
        if self.app_state.write_manager:
            self.app_state.write_manager.execute_control(control, self.app_state.current_user["id"])

    # --- Drag & Drop ---

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        src_id_str = event.mimeData().text()
        if not src_id_str.isdigit(): return
        
        src_id = int(src_id_str)
        pos = event.position().toPoint()
        
        # Find which card we dropped onto
        child = self.childAt(pos)
        while child and not isinstance(child, ParamCard):
            child = child.parent()
        
        if child and isinstance(child, ParamCard):
            tgt_id = child._register_id
            self._on_card_dragged(src_id, tgt_id)
            
        event.acceptProposedAction()

    def _on_card_dragged(self, src_id: int, tgt_id: int) -> None:
        """Swaps positions in DB and refreshes layout."""
        if src_id == tgt_id: return
        
        try:
            # 1. Update order in local list
            idx_src = self._card_order.index(src_id)
            idx_tgt = self._card_order.index(tgt_id)
            self._card_order[idx_src], self._card_order[idx_tgt] = self._card_order[idx_tgt], self._card_order[idx_src]
            
            # 2. Update DB with new positions
            model_id = self.app_state.current_model_id
            pos_updates = []
            for pos, rid in enumerate(self._card_order):
                mapping_id = self.app_state.map_repo.get_mapping_id(model_id, rid)
                if mapping_id:
                    pos_updates.append((mapping_id, pos))
            
            self.app_state.map_repo.update_card_positions(model_id, pos_updates)
            
            # 3. Refresh Grid
            self.load_model(model_id)
            
        except Exception as e:
            logger.error(f"Drag update failed: {e}")
