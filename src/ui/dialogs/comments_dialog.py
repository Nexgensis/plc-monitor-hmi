"""
ui/dialogs/comments_dialog.py
Dialog for viewing and adding comments to test sessions.
"""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QListWidget, QTextEdit, QPushButton,
    QSplitter, QFrame
)
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState

log = logging.getLogger(__name__)

class CommentsDialog(QDialog):
    """
    Operator interface for recording session-specific notes and observations.
    """
    
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._state = app_state
        
        self.setWindowTitle("Session Comments")
        self.setMinimumSize(600, 480)
        
        self._setup_ui()
        self._populate_sessions()
        
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Session Selection
        session_box = QHBoxLayout()
        session_box.addWidget(QLabel("Session:"))
        self.session_selector = QComboBox()
        self.session_selector.setMinimumWidth(350)
        self.session_selector.currentIndexChanged.connect(self._on_session_changed)
        session_box.addWidget(self.session_selector)
        session_box.addStretch()
        layout.addLayout(session_box)
        
        # Main Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Comments List
        left_container = QFrame()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.addWidget(QLabel("Previous Comments:"))
        self.comments_list = QListWidget()
        self.comments_list.setStyleSheet("background: #f8f9fc; border: 1px solid #d0d8e8; border-radius: 4px;")
        self.comments_list.setWordWrap(True)
        left_layout.addWidget(self.comments_list)
        splitter.addWidget(left_container)
        
        # Right: New Comment Input
        right_container = QFrame()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.addWidget(QLabel("New Comment:"))
        
        self.new_comment = QTextEdit()
        self.new_comment.setPlaceholderText("Enter up to 500 characters...")
        self.new_comment.textChanged.connect(self._on_text_changed)
        self.new_comment.setStyleSheet("border: 1px solid #d0d8e8; border-radius: 4px; padding: 8px;")
        right_layout.addWidget(self.new_comment)
        
        self.char_counter = QLabel("0/500")
        self.char_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.char_counter.setStyleSheet("color: #6c757d; font-size: 11px;")
        right_layout.addWidget(self.char_counter)
        
        splitter.addWidget(right_container)
        
        # Set initial sizes for splitter
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        
        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setStyleSheet("padding: 6px; background: #34495e; color: white; border-radius: 4px;")
        self.btn_close.clicked.connect(self.reject)
        
        self.btn_add = QPushButton("Add Comment")
        self.btn_add.setFixedWidth(140)
        self.btn_add.setStyleSheet("padding: 6px; background: #27ae60; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_add.clicked.connect(self._on_add_comment)
        
        btn_box.addWidget(self.btn_close)
        btn_box.addWidget(self.btn_add)
        layout.addLayout(btn_box)

    def _populate_sessions(self) -> None:
        """Fetch last 20 sessions and populate combo box."""
        if not self._state.report_repo:
            return
            
        sessions = self._state.report_repo.get_sessions_summary(limit=20)
        
        self.session_selector.blockSignals(True)
        self.session_selector.clear()
        
        for s in sessions:
            # Format: "2024-01-08 14:02 | MI-7646AZ | OK:3 NG:1"
            dt_str = s["started_at"][:16] if s["started_at"] else "N/A"
            model_str = s.get("model_number", "UNK")
            label = f"{dt_str} | {model_str} | OK:{s['ok_count']} NG:{s['ng_count']}"
            self.session_selector.addItem(label, s["session_id"])
            
        self.session_selector.blockSignals(False)
        
        # Trigger initial load if sessions exist
        if self.session_selector.count() > 0:
            self._on_session_changed()

    def _on_session_changed(self) -> None:
        """Load comments for the selected session."""
        session_id = self.session_selector.currentData()
        if session_id is None:
            return
            
        self.comments_list.clear()
        
        if not self._state.session_repo:
            return
            
        comments = self._state.session_repo.get_session_comments(session_id)
        for c in comments:
            # Format: "[HH:MM] username: comment text"
            time_str = c["created_at"][11:16] if c.get("created_at") else "??:??"
            user_str = c.get("username", "Unknown")
            text = c.get("comment", "")
            self.comments_list.addItem(f"[{time_str}] {user_str}: {text}")

    def _on_add_comment(self) -> None:
        """Validate and record a new session comment."""
        session_id = self.session_selector.currentData()
        if session_id is None:
            return
            
        text = self.new_comment.toPlainText().strip()
        if not text:
            return
            
        if len(text) > 500:
            text = text[:500]
            
        if not self._state.session_repo:
            return
            
        user_id = self._state.current_user["id"] if self._state.current_user else 0
        
        try:
            self._state.session_repo.record_comment(session_id, user_id, text)
            self.new_comment.clear()
            self._on_session_changed()
            log.info(f"Comment added to session {session_id}")
        except Exception as e:
            log.error(f"Failed to record comment: {e}")

    def _on_text_changed(self) -> None:
        """Update character counter and styling."""
        count = len(self.new_comment.toPlainText())
        self.char_counter.setText(f"{count}/500")
        
        if count > 450:
            self.char_counter.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 11px;")
        else:
            self.char_counter.setStyleSheet("color: #6c757d; font-size: 11px;")
        
        if count > 500:
            # Optionally visual feedback of overflow
            pass
