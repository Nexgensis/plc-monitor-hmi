# src/ui/components/message_bar.py
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QWidget
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)

class MessageBar(QFrame):
    """
    Full-width navy bottom status bar with a 
    pop-up history log.
    """
    def __init__(self, max_history: int = 100, parent: QWidget | None = None):
        super().__init__(parent)
        self._max_history = max_history
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("background-color: #1e2d4a;")
        self.setFixedHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.current_msg = QLabel("")
        self.current_msg.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(self.current_msg, stretch=1)
        
        self.history_btn = QPushButton("▲")
        self.history_btn.setFixedWidth(30)
        self.history_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2a3f6c;
            }
        """)
        self.history_btn.clicked.connect(self._toggle_history)
        layout.addWidget(self.history_btn)
        
        # History popup window
        self.popup = QFrame(self.window())
        self.popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.popup.setStyleSheet("""
            QFrame {
                background-color: #1e2d4a;
                border: 1px solid #3a4f8c;
            }
            QListWidget {
                background-color: #1e2d4a;
                color: white;
                border: none;
                outline: none;
            }
            QListWidget::item:selected {
                background: #2a3f6c;
            }
        """)
        
        popup_layout = QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(1, 1, 1, 1)
        
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(200)
        popup_layout.addWidget(self.history_list)
        
        self.popup.hide()

    def _toggle_history(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
        else:
            global_pos = self.mapToGlobal(QPoint(0, 0))
            popup_width = self.width() // 2 if self.width() > 600 else 300
            if popup_width < 300: 
                popup_width = 300
                
            self.popup.resize(popup_width, 200)
            
            x = global_pos.x() + self.width() - popup_width
            y = global_pos.y() - 200
            self.popup.move(x, y)
            self.popup.show()

    def show_message(self, text: str, level: str = "INFO") -> None:
        """
        Displays a new message in the bar and appends it to history.
        """
        colors = {
            "INFO":    "#ffffff",
            "WARNING": "#f39c12",
            "ERROR":   "#e74c3c",
            "SUCCESS": "#2ecc71",
        }
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {text}"
        color = colors.get(level, "#ffffff")
        
        self.current_msg.setText(full_msg)
        self.current_msg.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
        
        # Flash effect: briefly bold then normal
        QTimer.singleShot(
            500, 
            lambda: self.current_msg.setStyleSheet(f"color: {color}; font-weight: normal; font-size: 13px;")
        )
        
        # Add to history list (prepend)
        item = QListWidgetItem(full_msg)
        item.setForeground(QColor(color))
        self.history_list.insertItem(0, item)
        
        if self.history_list.count() > self._max_history:
            self.history_list.takeItem(self.history_list.count() - 1)

    def clear(self) -> None:
        self.current_msg.setText("")
        self.history_list.clear()
