"""
param_card.py — Universal PLC Monitor
Visual card component for the Test Dashboard.
Supports real-time state updates, amber pulsing for running state,
and admin-only drag-to-reorder functionality.
"""
from __future__ import annotations

import logging
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
                             QApplication, QGraphicsOpacityEffect)
from PyQt6.QtCore import (Qt, pyqtSignal, QMimeData, QPropertyAnimation, 
                          QPoint)
from PyQt6.QtGui import QDrag

from src.logic.pass_fail_evaluator import EvalResult
from src.utils.constants import (
    RESULT_PASS, RESULT_FAIL, RESULT_PENDING, 
    RESULT_BYPASS, RESULT_RUNNING, RESULT_NA
)

logger = logging.getLogger(__name__)


class ParamCard(QFrame):
    """
    A single dashboard card representing one PLC parameter or result.
    """
    # Signal emitted when a drag operation ends on a target card
    # (source_id, target_id)
    drag_completed = pyqtSignal(int, int)

    def __init__(
        self, 
        register_id: int,
        display_name: str,
        group_name: str,
        unit: str,
        theme: str = "dark",
        can_drag: bool = False
    ) -> None:
        super().__init__()
        self._register_id = register_id
        self._display_name = display_name
        self._can_drag = can_drag
        self._current_result = RESULT_PENDING
        self._drag_start = QPoint()

        self.setObjectName("module_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        self._init_ui(group_name, unit)

    def _init_ui(self, group_name: str, unit: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(4)

        # 1. Header (Group + Drag Handle)
        header = QHBoxLayout()
        header.setSpacing(0)
        
        self.group_lbl = QLabel(group_name.upper() if group_name else "")
        self.group_lbl.setObjectName("card_group_label")
        header.addWidget(self.group_lbl)
        
        header.addStretch()
        
        self.drag_handle = QLabel("⋮")
        self.drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag_handle.setObjectName("card_drag_handle")
        self.drag_handle.setVisible(self._can_drag)
        header.addWidget(self.drag_handle)
        
        layout.addLayout(header)

        # 2. Parameter Name
        self.name_lbl = QLabel(self._display_name)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setObjectName("card_name_label")
        layout.addWidget(self.name_lbl)
        
        layout.addStretch()

        # 3. Value Display
        self.value_lbl = QLabel("---")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_lbl.setObjectName("card_value_label")
        layout.addWidget(self.value_lbl)

        # 4. Unit
        self.unit_lbl = QLabel(unit)
        self.unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_lbl.setObjectName("card_unit_label")
        layout.addWidget(self.unit_lbl)

        layout.addStretch()

        # 5. Result Badge
        self.result_lbl = QLabel("● PENDING")
        self.result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_lbl.setMinimumHeight(26)
        self.result_lbl.setObjectName("result_pending") # Controlled via QSS
        layout.addWidget(self.result_lbl)

    def set_size_mode(self, mode: str) -> None:
        """Adjusts font sizes based on density."""
        sizes = {
            "large":  {"name": 14, "value": 28, "unit": 12, "badge": 26},
            "medium": {"name": 13, "value": 22, "unit": 10, "badge": 24},
            "small":  {"name": 11, "value": 18, "unit": 9,  "badge": 22},
        }
        s = sizes.get(mode, sizes["medium"])
        
        # Use fixed classes for size if possible, or properties
        self.setProperty("size_mode", mode)
        self.style().unpolish(self)
        self.style().polish(self)
        self.result_lbl.setFixedHeight(s["badge"])

    def update_result(self, eval_result: EvalResult) -> None:
        """Update card content and visual state."""
        # 1. Update text
        if eval_result.display_str == "---" or eval_result.result == RESULT_PENDING:
            self.value_lbl.setText("---")
        else:
            self.value_lbl.setText(eval_result.display_str)
            
        # 2. Update visual result state
        self._set_result_state(eval_result.result)

    def _set_result_state(self, result: str) -> None:
        if self._current_result == result:
            return
            
        self._current_result = result
        
        obj_map = {
            RESULT_PASS:    "result_pass",
            RESULT_FAIL:    "result_fail",
            RESULT_PENDING: "result_pending",
            RESULT_BYPASS:  "result_pending",
            RESULT_RUNNING: "result_running",
            RESULT_NA:      "result_pending",
        }
        text_map = {
            RESULT_PASS:    "● PASS",
            RESULT_FAIL:    "● FAIL",
            RESULT_PENDING: "● PENDING",
            RESULT_BYPASS:  "● BYPASS",
            RESULT_RUNNING: "● RUNNING",
            RESULT_NA:      "● N/A",
        }
        
        self.result_lbl.setObjectName(obj_map.get(result, "result_pending"))
        self.result_lbl.setText(text_map.get(result, "● PENDING"))
        
        # Apply property for border color changes in QSS
        prop_val = {
            RESULT_PASS:    "pass",
            RESULT_FAIL:    "fail",
            RESULT_RUNNING: "running",
        }.get(result, "")
        self.setProperty("result", prop_val)
        
        # Force style refresh
        self.style().unpolish(self.result_lbl)
        self.style().polish(self.result_lbl)
        self.style().unpolish(self)
        self.style().polish(self)
        
        # Animation management
        if result == RESULT_RUNNING:
            self._start_pulse()
        else:
            self._stop_pulse()

    def _start_pulse(self) -> None:
        """Starts a subtle opacity pulse animation on the card content."""
        if hasattr(self, "_pulse_anim"):
            return
            
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._pulse_effect = effect
        
        self._pulse_anim = QPropertyAnimation(effect, b"opacity")
        self._pulse_anim.setDuration(1000)
        self._pulse_anim.setStartValue(1.0)
        self._pulse_anim.setEndValue(0.6)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.start()

    def _stop_pulse(self) -> None:
        """Stops animation and restores full opacity."""
        if hasattr(self, "_pulse_anim"):
            self._pulse_anim.stop()
            del self._pulse_anim
        if hasattr(self, "_pulse_effect"):
            self._pulse_effect.setOpacity(1.0)
            del self._pulse_effect
        self.setGraphicsEffect(None)

    def reset(self) -> None:
        """Reset to idle state."""
        self.value_lbl.setText("---")
        self._set_result_state(RESULT_PENDING)

    # --- DRAG SUPPORT ---

    def mousePressEvent(self, event) -> None:
        if self._can_drag and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self._can_drag:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self._register_id))
        drag.setMimeData(mime)
        
        # Visual feedback
        pixmap = self.grab().scaled(
            self.width() // 2, self.height() // 2,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        
        drag.exec(Qt.DropAction.MoveAction)
