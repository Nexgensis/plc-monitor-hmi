"""
CounterPanel component.
Displays production counters and cycle time on the right side of the Test Page.
"""
import logging
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt

logger = logging.getLogger(__name__)

class CounterPanel(QFrame):
    reset_batch_clicked = pyqtSignal()
    reset_coupler_clicked = pyqtSignal()
    reset_all_clicked = pyqtSignal()

    def __init__(self, app_state=None):
        super().__init__()
        self._app_state = app_state
        self.setFixedWidth(180)
        self.setObjectName("card")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Overall result badge
        self.overall_lbl = QLabel("● PENDING")
        self.overall_lbl.setObjectName("result_pending")
        self.overall_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_lbl.setMinimumHeight(56)
        self.overall_lbl.setStyleSheet("font-size: 20px; font-weight: bold; border-radius: 6px; background-color: rgba(128,128,128,0.1); border: 1px solid #888;")
        layout.addWidget(self.overall_lbl)
        
        # Counters
        self.ok_val_lbl = self._create_counter(layout, "OK COUNT", "green")
        self.ng_val_lbl = self._create_counter(layout, "NG COUNT", "red")
        self.batch_val_lbl = self._create_counter(layout, "BATCH RUN")
        self.coupler_val_lbl = self._create_counter(layout, "COUPLER RUN")
        
        # Cycle Time
        ct_layout = QVBoxLayout()
        ct_layout.setSpacing(0)
        ct_lbl = QLabel("CYCLE TIME")
        ct_lbl.setStyleSheet("font-size: 9px; color: #888888;")
        self.cycle_val_lbl = QLabel("0.0 s")
        self.cycle_val_lbl.setStyleSheet("font-size: 14px; font-family: monospace; font-weight: bold;")
        ct_layout.addWidget(ct_lbl)
        ct_layout.addWidget(self.cycle_val_lbl)
        layout.addLayout(ct_layout)
        
        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #333333;")
        layout.addWidget(div)
        
        # Action buttons
        btn_batch = QPushButton("RST Batch")
        btn_batch.setObjectName("btn_secondary")
        btn_batch.clicked.connect(self.reset_batch_clicked.emit)
        
        btn_coupler = QPushButton("RST Coupler")
        btn_coupler.setObjectName("btn_secondary")
        btn_coupler.clicked.connect(self.reset_coupler_clicked.emit)
        
        btn_all = QPushButton("RST All")
        btn_all.setObjectName("btn_danger")
        btn_all.clicked.connect(self.reset_all_clicked.emit)
        
        layout.addWidget(btn_batch)
        layout.addWidget(btn_coupler)
        layout.addWidget(btn_all)
        layout.addStretch()

    def _create_counter(self, parent_layout, title, color="default"):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        
        val_lbl = QLabel("0")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if color == "green":
            val_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #22c55e; border: none; background: transparent;")
        elif color == "red":
            val_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #ef4444; border: none; background: transparent;")
        else:
            val_lbl.setStyleSheet("font-size: 18px; font-weight: bold; border: none; background: transparent;")
            
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size: 9px; color: #888888; border: none; background: transparent;")
        
        layout.addWidget(val_lbl)
        layout.addWidget(title_lbl)
        parent_layout.addWidget(frame)
        
        return val_lbl

    def update_overall(self, result: str) -> None:
        if result == "PASS":
            self.overall_lbl.setText("● PASS")
            self.overall_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #22c55e; border-radius: 6px; background-color: rgba(34, 197, 94, 0.1); border: 1px solid #22c55e;")
        elif result == "FAIL":
            self.overall_lbl.setText("● FAIL")
            self.overall_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #ef4444; border-radius: 6px; background-color: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444;")
        else:
            self.overall_lbl.setText("● PENDING")
            self.overall_lbl.setStyleSheet("font-size: 20px; font-weight: bold; border-radius: 6px; background-color: rgba(128,128,128,0.1); border: 1px solid #888;")

    def update_counts(self, ok: int, ng: int, batch: int, coupler: int) -> None:
        self.ok_val_lbl.setText(str(ok))
        self.ng_val_lbl.setText(str(ng))
        self.batch_val_lbl.setText(str(batch))
        self.coupler_val_lbl.setText(str(coupler))

    def update_cycle_time(self, seconds: float) -> None:
        self.cycle_val_lbl.setText(f"{seconds:.1f} s")

    def reset_display(self) -> None:
        self.update_overall("PENDING")
