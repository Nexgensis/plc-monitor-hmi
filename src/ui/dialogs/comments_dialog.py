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
        self.setAccessibleName("Session comments dialog")
        self.setMinimumSize(600, 480)
        
        self._setup_ui()
        self._populate_sessions()
        
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        session_box = QHBoxLayout()
        session_box.addWidget(QLabel("Session:"))
        self.session_selector = QComboBox()
        self.session_selector.setMinimumWidth(350)
        self.session_selector.setAccessibleName("Select session")
        self.session_selector.setToolTip("Select a test session to view or add comments")
        self.session_selector.currentIndexChanged.connect(self._on_session_changed)
        session_box.addWidget(self.session_selector)
        session_box.addStretch()
        layout.addLayout(session_box)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_container = QFrame()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.addWidget(QLabel("Previous Comments:"))
        self.comments_list = QListWidget()
        self.comments_list.setObjectName("comments_list")
        self.comments_list.setWordWrap(True)
        self.comments_list.setAccessibleName("Previous comments")
        self.comments_list.setToolTip("List of comments previously added to this session")
        left_layout.addWidget(self.comments_list)
        splitter.addWidget(left_container)
        
        right_container = QFrame()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.addWidget(QLabel("New Comment:"))
        
        self.new_comment = QTextEdit()
        self.new_comment.setPlaceholderText("Enter up to 500 characters...")
        self.new_comment.setAccessibleName("New comment")
        self.new_comment.setToolTip("Type your comment here, max 500 characters")
        self.new_comment.textChanged.connect(self._on_text_changed)
        self.new_comment.setObjectName("comments_new_comment")
        right_layout.addWidget(self.new_comment)
        
        self.char_counter = QLabel("0/500")
        self.char_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.char_counter.setObjectName("comments_char_counter")
        right_layout.addWidget(self.char_counter)
        
        splitter.addWidget(right_container)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.setAccessibleName("Close dialog")
        self.btn_close.clicked.connect(self.reject)
        
        self.btn_add = QPushButton("Add Comment")
        self.btn_add.setFixedWidth(140)
        self.btn_add.setObjectName("btn_success")
        self.btn_add.setAccessibleName("Add comment")
        self.btn_add.setToolTip("Submit the comment to the selected session")
        self.btn_add.clicked.connect(self._on_add_comment)
        
        btn_box.addWidget(self.btn_close)
        btn_box.addWidget(self.btn_add)
        layout.addLayout(btn_box)

    def _populate_sessions(self) -> None:
        if not self._state.report_repo:
            return
            
        sessions = self._state.report_repo.get_sessions_summary(limit=20)
        
        self.session_selector.blockSignals(True)
        self.session_selector.clear()
        
        for s in sessions:
            dt_str = s["started_at"][:16] if s["started_at"] else "N/A"
            model_str = s.get("model_number", "UNK")
            label = f"{dt_str} | {model_str} | OK:{s['ok_count']} NG:{s['ng_count']}"
            self.session_selector.addItem(label, s["session_id"])
            
        self.session_selector.blockSignals(False)
        
        if self.session_selector.count() > 0:
            self._on_session_changed()

    def _on_session_changed(self) -> None:
        session_id = self.session_selector.currentData()
        if session_id is None:
            return
            
        self.comments_list.clear()
        
        if not self._state.session_repo:
            return
            
        comments = self._state.session_repo.get_session_comments(session_id)
        for c in comments:
            time_str = c["created_at"][11:16] if c.get("created_at") else "??:??"
            user_str = c.get("username", "Unknown")
            text = c.get("comment", "")
            self.comments_list.addItem(f"[{time_str}] {user_str}: {text}")

    def _on_add_comment(self) -> None:
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
        count = len(self.new_comment.toPlainText())
        self.char_counter.setText(f"{count}/500")
        
        if count > 450:
            self.char_counter.setProperty("warning", True)
        else:
            self.char_counter.setProperty("warning", False)
        
        self.style().unpolish(self.char_counter)
        self.style().polish(self.char_counter)
        
        if count > 500:
            cursor = self.new_comment.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.movePosition(cursor.MoveOperation.Start, cursor.MoveMode.KeepAnchor)
            text = cursor.selectedText()[:500]
            cursor.insertText(text)
