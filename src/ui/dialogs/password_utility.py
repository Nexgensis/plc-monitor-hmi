"""
ui/dialogs/password_utility.py
Self-service GUI tool managing authorization passwords and enforcing hardcoded strength mechanics.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFormLayout, QComboBox, QProgressBar)
from PyQt6.QtCore import Qt

from src.db.user_repo import UserRepository
from src.ui.app_state import AppState

class PasswordUtilityDialog(QWidget):
    """
    Form intercepting password modifications enforcing security validation loops logically
    explicitly embedded dynamically natively.
    """

    def __init__(self, db, app_state: AppState, router=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._user_repo = UserRepository(db)
        self._app_state = app_state
        self._router = router
        self.setWindowTitle("Password Change")
        self.setAccessibleName("Password change dialog")
        
        self._setup_ui()
        self._populate_users()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        form_layout = QFormLayout()
        
        self.combo_user = QComboBox()
        self.combo_user.setAccessibleName("Select user")
        self.combo_user.setToolTip("Select the user whose password you want to change")
        
        self.edit_current = QLineEdit()
        self.edit_current.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_current.setAccessibleName("Current password")
        self.btn_eye_current = self._make_eye_btn(self.edit_current)
        curr_layout = QHBoxLayout()
        curr_layout.setContentsMargins(0,0,0,0)
        curr_layout.addWidget(self.edit_current)
        curr_layout.addWidget(self.btn_eye_current)
        
        self.edit_new = QLineEdit()
        self.edit_new.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_new.setAccessibleName("New password")
        self.edit_new.textChanged.connect(self._check_strength)
        self.btn_eye_new = self._make_eye_btn(self.edit_new)
        new_layout = QHBoxLayout()
        new_layout.setContentsMargins(0,0,0,0)
        new_layout.addWidget(self.edit_new)
        new_layout.addWidget(self.btn_eye_new)
        
        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_confirm.setAccessibleName("Confirm new password")
        self.btn_eye_confirm = self._make_eye_btn(self.edit_confirm)
        confirm_layout = QHBoxLayout()
        confirm_layout.setContentsMargins(0,0,0,0)
        confirm_layout.addWidget(self.edit_confirm)
        confirm_layout.addWidget(self.btn_eye_confirm)
        
        form_layout.addRow("Select User:", self.combo_user)
        form_layout.addRow("Current Password:", curr_layout)
        form_layout.addRow("New Password:", new_layout)
        form_layout.addRow("Confirm Password:", confirm_layout)
        
        layout.addLayout(form_layout)
        
        strength_label = QLabel("Password Strength:")
        strength_label.setObjectName("password_strength_lbl")
        layout.addWidget(strength_label)

        self.progress_strength = QProgressBar()
        self.progress_strength.setObjectName("password_strength_bar")
        self.progress_strength.setAccessibleName("Password strength indicator")
        self.progress_strength.setToolTip("Shows password strength from weak to strong")
        self.progress_strength.setRange(0, 100)
        self.progress_strength.setValue(0)
        self.progress_strength.setTextVisible(False)
        self.progress_strength.setFixedHeight(10)
        layout.addWidget(self.progress_strength)
        
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("password_status")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.hide()
        layout.addWidget(self.lbl_status)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.setAccessibleName("Close")
        self.btn_close.clicked.connect(self._on_close)
        
        self.btn_change = QPushButton("Change Password")
        self.btn_change.setObjectName("btn_success")
        self.btn_change.setAccessibleName("Change password")
        self.btn_change.setToolTip("Save the new password")
        self.btn_change.clicked.connect(self._on_change_clicked)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_change)
        
        layout.addLayout(btn_layout)

    def _on_close(self) -> None:
        if self._router:
            self._router.show_login()

    def _make_eye_btn(self, field: QLineEdit) -> QPushButton:
        btn = QPushButton("👁")
        btn.setCheckable(True)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda checked, f=field: self._toggle_eye(f, checked))
        return btn

    def _toggle_eye(self, field: QLineEdit, checked: bool) -> None:
        if checked:
            field.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            field.setEchoMode(QLineEdit.EchoMode.Password)

    def _populate_users(self) -> None:
        """Route available selection arrays by role hierarchy mappings."""
        if not self._app_state.current_user:
            return
            
        users = self._user_repo.get_all_users()
        if self._app_state.is_admin():
            for u in users:
                self.combo_user.addItem(u["username"], u["id"])
            curr_id = self._app_state.current_user["id"]
            idx = self.combo_user.findData(curr_id)
            if idx >= 0:
                self.combo_user.setCurrentIndex(idx)
        else:
            username = self._app_state.current_user["username"]
            user_id = self._app_state.current_user["id"]
            self.combo_user.addItem(username, user_id)
            self.combo_user.setEnabled(False)  # Lock operator to current identity context

    def _check_strength(self) -> None:
        """Dynamically evaluate entry mechanics instantly reporting metrics via bar chunks."""
        pwd = self.edit_new.text()
        score = 0
        if len(pwd) >= 8: score += 20
        if len(pwd) >= 12: score += 20
        if any(c.isupper() for c in pwd): score += 20
        if any(c.isdigit() for c in pwd): score += 20
        if any(c in "!@#$%^&*" for c in pwd): score += 20
        
        self.progress_strength.setValue(score)
        
        if score < 40:
            self.progress_strength.setProperty("strength", "weak")
        elif score <= 70:
            self.progress_strength.setProperty("strength", "medium")
        else:
            self.progress_strength.setProperty("strength", "strong")

        self.progress_strength.style().unpolish(self.progress_strength)
        self.progress_strength.style().polish(self.progress_strength)

    def _on_change_clicked(self) -> None:
        user_id = self.combo_user.currentData()
        curr_pwd = self.edit_current.text()
        new_pwd = self.edit_new.text()
        conf_pwd = self.edit_confirm.text()
        
        if not curr_pwd or not new_pwd or not conf_pwd:
            self._show_error("All fields are required.")
            return
            
        if new_pwd == curr_pwd:
            self._show_error("New password cannot be same as current.")
            return
            
        if new_pwd != conf_pwd:
            self._show_error("Confirm password does not match.")
            return
            
        if self.progress_strength.value() < 40:
            self._show_error("Password is too weak.")
            return
            
        # Push into protected hashing logic inside user repository
        success = self._user_repo.change_password(user_id, curr_pwd, new_pwd)
        if success:
            self.lbl_status.setText("Password changed successfully")
            self.lbl_status.setProperty("success", True)
            self.lbl_status.show()
            self.edit_current.clear()
            self.edit_new.clear()
            self.edit_confirm.clear()
        else:
            self._show_error("Current password is incorrect")

    def _show_error(self, msg: str) -> None:
        self.lbl_status.setText(msg)
        self.lbl_status.setProperty("success", False)
        self.lbl_status.show()
