import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QFrame, QHBoxLayout, QVBoxLayout, QLabel, 
    QComboBox, QLineEdit, QPushButton, QGridLayout, 
    QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from src.ui.app_state import AppState
from src.plc.model_push_worker import ModelPushWorker

logger = logging.getLogger(__name__)

APP_NAME = "PLC Monitor"
APP_VERSION = "1.0.0"

class LoginWindow(QMainWindow):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self._push_worker = None

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setStyleSheet("background-color: #f0f2f5;")

        self._init_ui()
        self._init_timers()

    def _init_ui(self):
        central_widget = QFrame(self)
        self.setCentralWidget(central_widget)
        
        # Outer layout to center the content
        outer_layout = QHBoxLayout(central_widget)
        outer_layout.addStretch()
        
        content_widget = QFrame()
        content_widget.setFixedWidth(920) # Keeping a reasonable width for the card content
        main_layout = QHBoxLayout(content_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(20)
        
        outer_layout.addWidget(content_widget)
        outer_layout.addStretch()

        # LEFT PANEL
        left_panel = QFrame(self)
        left_panel.setObjectName("card")
        left_panel.setFixedWidth(380)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)

        # Logo Area
        app_name_lbl = QLabel(APP_NAME)
        app_name_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #1e2d4a;")
        app_name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle_lbl = QLabel("Switch Test Station")
        subtitle_lbl.setStyleSheet("color: #6c757d; font-size: 14px;")
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background-color: #d0d8e8;")

        left_layout.addWidget(app_name_lbl)
        left_layout.addWidget(subtitle_lbl)
        left_layout.addWidget(divider)
        left_layout.addSpacing(20)

        # Login Form
        label_style = "color: #1a1a2e; font-weight: bold; font-size: 14px;"
        
        role_lbl = QLabel("Select Role:")
        role_lbl.setStyleSheet(label_style)
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Admin", "Operator", "Supervisor"])

        password_lbl = QLabel("Password:")
        password_lbl.setStyleSheet(label_style)
        password_row = QHBoxLayout()
        self.password_field = QLineEdit()
        self.password_field.setPlaceholderText("Enter password...")
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.returnPressed.connect(self._on_login_clicked)
        
        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFlat(True)
        self.eye_btn.setFixedWidth(40)
        self.eye_btn.setStyleSheet("background: transparent; color: #1e2d4a; font-size: 18px;")
        self.eye_btn.clicked.connect(self._toggle_password_visibility)
        
        password_row.addWidget(self.password_field)
        password_row.addWidget(self.eye_btn)

        self.error_label = QLabel("Invalid credentials. Please try again.")
        self.error_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        self.error_label.hide()

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("Login")
        self.login_btn.setObjectName("btn_success")
        self.login_btn.clicked.connect(self._on_login_clicked)
        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setObjectName("btn_secondary")
        self.exit_btn.clicked.connect(self.close)
        
        btn_row.addWidget(self.login_btn, stretch=1)
        btn_row.addWidget(self.exit_btn)

        left_layout.addWidget(role_lbl)
        left_layout.addWidget(self.role_combo)
        left_layout.addSpacing(15)
        left_layout.addWidget(password_lbl)
        left_layout.addLayout(password_row)
        left_layout.addWidget(self.error_label)
        left_layout.addStretch()
        left_layout.addLayout(btn_row)

        # Bottom Bar
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("status_bar_frame")
        self.bottom_bar.setFixedHeight(36)
        # Deep navy background for high contrast with white status text
        self.bottom_bar.setStyleSheet("background-color: #0f1624; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(15, 0, 15, 0)
        
        clock_style = "color: #dce4f0; font-family: 'Consolas', monospace; font-size: 12px; font-weight: bold;"
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(clock_style)
        
        db_path = self.app_state.db._db_path if self.app_state.db else "None"
        db_label = QLabel(f"DATABASE: {db_path}")
        db_label.setStyleSheet(clock_style)
        
        bottom_layout.addWidget(self.clock_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(db_label)
        
        left_layout.addWidget(self.bottom_bar)

        # RIGHT PANEL
        self.right_panel = QFrame(self)
        self.right_panel.setFixedWidth(520)
        self.right_panel.hide()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.welcome_label = QLabel()
        self.welcome_label.setStyleSheet("color: #1e2d4a; font-size: 15px; font-weight: bold;")
        self.role_label = QLabel()
        self.role_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        
        right_layout.addWidget(self.welcome_label)
        right_layout.addWidget(self.role_label)
        right_layout.addSpacing(20)

        # Button Grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        self.pw_utility_btn = QPushButton("Password Utility")
        self.pw_utility_btn.clicked.connect(self._on_password_utility_clicked)
        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("btn_secondary")
        self.logout_btn.clicked.connect(self._on_logout_clicked)

        self.auto_test_btn = QPushButton("Auto Test")
        self.auto_test_btn.clicked.connect(self._on_auto_test_clicked)
        self.manual_test_btn = QPushButton("Manual Test")
        self.manual_test_btn.clicked.connect(self._on_manual_test_clicked)
        self.comments_btn = QPushButton("Comments")
        
        self.reports_btn = QPushButton("Reports")
        self.reports_btn.setObjectName("btn_primary")
        self.reports_btn.clicked.connect(self._on_reports_clicked)

        for btn in [self.settings_btn, self.pw_utility_btn, self.logout_btn, 
                    self.auto_test_btn, self.manual_test_btn, self.comments_btn, self.reports_btn]:
            btn.setMinimumHeight(48)

        grid_layout.addWidget(self.settings_btn, 0, 0)
        grid_layout.addWidget(self.pw_utility_btn, 0, 1)
        grid_layout.addWidget(self.logout_btn, 0, 2)
        grid_layout.addWidget(self.auto_test_btn, 1, 0)
        grid_layout.addWidget(self.manual_test_btn, 1, 1)
        grid_layout.addWidget(self.comments_btn, 1, 2)
        grid_layout.addWidget(self.reports_btn, 2, 0, 1, 3)

        right_layout.addLayout(grid_layout)
        right_layout.addSpacing(30)

        # Model Selector
        model_lbl = QLabel("Select Model for Testing:")
        model_lbl.setStyleSheet("color: #1e2d4a; font-weight: bold;")
        self.model_combo = QComboBox()
        self.model_combo.setPlaceholderText("-- Select Model --")
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        
        right_layout.addWidget(model_lbl)
        right_layout.addWidget(self.model_combo)
        right_layout.addSpacing(20)

        # Push Status Panel
        self.push_status_panel = QFrame()
        self.push_status_panel.setObjectName("push_status_ok")
        push_layout = QVBoxLayout(self.push_status_panel)
        
        status_row = QHBoxLayout()
        self.push_status_icon = QLabel("○")
        self.push_status_icon.setStyleSheet("color: #6c757d; font-size: 16px;")
        self.push_status_label = QLabel("Model not yet pushed to PLC")
        status_row.addWidget(self.push_status_icon)
        status_row.addWidget(self.push_status_label)
        status_row.addStretch()

        self.last_pushed_label = QLabel("Last pushed: never")
        self.last_pushed_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        
        self.push_progress = QProgressBar()
        self.push_progress.hide()

        push_layout.addLayout(status_row)
        push_layout.addWidget(self.last_pushed_label)
        push_layout.addWidget(self.push_progress)

        right_layout.addWidget(self.push_status_panel)
        right_layout.addStretch()

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.right_panel)
        main_layout.addStretch()

    def _init_timers(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

    def _toggle_password_visibility(self):
        if self.password_field.echoMode() == QLineEdit.EchoMode.Password:
            self.password_field.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_btn.setText("🔒")
        else:
            self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_btn.setText("👁")

    def _on_login_clicked(self) -> None:
        role = self.role_combo.currentText().upper()
        pw = self.password_field.text()
        user = self.app_state.user_repo.authenticate(role.lower(), pw)
        if user:
            self.app_state.set_user(user)
            self._show_right_panel()
            self.password_field.clear()
            self.error_label.hide()
        else:
            self.error_label.show()
            self.password_field.clear()
            self.password_field.setFocus()

    def _show_right_panel(self) -> None:
        self.right_panel.show()
        user = self.app_state.current_user
        if user:
            self.welcome_label.setText(f"Welcome, {user.get('username', '')}")
            self.role_label.setText(f"Role: {user.get('role', '').title()}")
        
        self.settings_btn.setVisible(self.app_state.can_edit_settings())
        # Visible: Admin + Supervisor only
        self.reports_btn.setVisible(not self.app_state.is_operator())
        
        self._populate_models()
        self.model_combo.setFocus()

    def _populate_models(self) -> None:
        models = self.app_state.model_repo.get_all_models()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("-- Select Model --", userData=-1)
        for m in models:
            label = f"{m['name']}"
            if m.get('model_number'):
                label += f"  ({m['model_number']})"
            self.model_combo.addItem(label, userData=m['id'])
        
        if self.app_state.current_model_id:
            idx = self.model_combo.findData(self.app_state.current_model_id)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _on_model_combo_changed(self, index: int) -> None:
        self._on_model_selected(index)

    def _on_model_selected(self, index: int) -> None:
        model_id = self.model_combo.currentData()
        if not model_id or model_id == -1: return
        
        config = self.app_state.model_repo.get_full_model_config(model_id)
        if not config: return
        
        self.app_state.set_model(config)
        
        warnings = self.app_state.param_repo.validate_model_parameters(model_id)
        if warnings:
            self._show_push_status("warning", f"{len(warnings)} config warnings")
            logger.warning(f"Model warnings: {warnings}")
            
        self._start_model_push(config)
        if self.app_state.connection_manager:
            self.app_state.connection_manager.update_parameters(config.get("parameters", []))

    def _start_model_push(self, model_config: dict) -> None:
        if not self.app_state.is_plc_connected:
            self._show_push_status("failed", "PLC not connected — push skipped")
            self.app_state.model_push_status = "not_required"
            # Keep test buttons enabled so users can choose what to do 
            self.auto_test_btn.setEnabled(True)
            self.manual_test_btn.setEnabled(True)
            return

        user_id = self.app_state.current_user.get("id") if self.app_state.current_user else 0
        self._push_worker = ModelPushWorker(
            model_config,
            self.app_state.write_manager,
            user_id
        )
        self._push_worker.push_started.connect(
            lambda n: self._show_push_status("pending", f"Pushing {n} to PLC...")
        )
        self._push_worker.push_progress.connect(self._on_push_progress)
        self._push_worker.push_success.connect(self._on_push_success)
        self._push_worker.push_failed.connect(self._on_push_failed)
        self._push_worker.start()

    def _on_push_progress(self, pct: int, msg: str) -> None:
        self.push_progress.setValue(pct)
        self.push_status_label.setText(msg)

    def _on_push_success(self, model_name: str) -> None:
        self.app_state.model_push_status = "success"
        self.push_progress.hide()
        self._show_push_status("success", f"{model_name} active in PLC")
        self.last_pushed_label.setText(f"Last pushed: {datetime.now():%H:%M:%S}")
        self.auto_test_btn.setEnabled(True)
        self.manual_test_btn.setEnabled(True)

    def _on_push_failed(self, name: str, error: str) -> None:
        self.app_state.model_push_status = "failed"
        self.push_progress.hide()
        self._show_push_status("failed", f"Push failed — {error}")
        self.auto_test_btn.setEnabled(True)
        self.manual_test_btn.setEnabled(True)

    def _show_push_status(self, state: str, message: str) -> None:
        colors = {
            "success": ("#1a6b3a", "●"),
            "failed":  ("#c0392b", "●"),
            "pending": ("#d4890a", "●"),
            "warning": ("#d4890a", "⚠"),
            "never":   ("#6c757d", "○"),
        }
        color, icon = colors.get(state, ("#6c757d", "○"))
        self.push_status_icon.setText(icon)
        self.push_status_icon.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.push_status_label.setText(message)
        
        status_obj_name = {
            "success": "push_status_ok",
            "failed": "push_status_fail",
            "pending": "push_status_pending",
            "warning": "push_status_pending",
            "never": "push_status_ok"
        }.get(state, "push_status_ok")
        
        self.push_status_panel.setObjectName(status_obj_name)
        self.push_status_panel.style().unpolish(self.push_status_panel)
        self.push_status_panel.style().polish(self.push_status_panel)

        if state == "pending":
            self.push_progress.show()
            self.push_progress.setValue(0)

    def _on_auto_test_clicked(self) -> None:
        if self.model_combo.currentData() in (-1, None, ""):
            QMessageBox.warning(self, "No Model", "Please select a model before starting.")
            return

        if self.app_state.model_push_status == "failed":
            reply = QMessageBox.question(
                self,
                "Push Failed",
                "Model config was not pushed to PLC.\n"
                "PLC may use previous settings.\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        from src.ui.main_window import MainWindow
        self._main_window = MainWindow(self.app_state)
        self._main_window.show()
        self.hide()

    def _on_manual_test_clicked(self) -> None:
        if self.model_combo.currentData() in (-1, None, ""):
            QMessageBox.warning(self, "No Model", "Please select a model before starting.")
            return

        if self.app_state.model_push_status == "failed":
            reply = QMessageBox.question(
                self,
                "Push Failed",
                "Model config was not pushed to PLC.\n"
                "PLC may use previous settings.\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        from src.ui.manual_test_window import ManualTestWindow
        # Arguments: db, app_state, connection_manager, router=None, parent=None
        self._manual_window = ManualTestWindow(
            self.app_state.db, 
            self.app_state, 
            self.app_state.connection_manager
        )
        self._manual_window.show()
        self.hide()

    def _on_logout_clicked(self) -> None:
        self.app_state.clear_user()
        self.right_panel.hide()
        self.password_field.clear()
        self.role_combo.setCurrentIndex(0)
        self.model_combo.clear()
        self._show_push_status("never", "No model selected")

    def _on_settings_clicked(self) -> None:
        from src.ui.settings_window import SettingsWindow
        dlg = SettingsWindow(self.app_state, parent=self)
        dlg.exec()

    def _on_reports_clicked(self) -> None:
        from src.ui.dialogs.reports_dialog import ReportsDialog
        dlg = ReportsDialog(self.app_state, parent=self)
        dlg.exec()

    def _on_password_utility_clicked(self) -> None:
        from src.ui.dialogs.password_utility import PasswordUtilityDialog
        dlg = PasswordUtilityDialog(self.app_state.db, self.app_state, parent=self)
        # PasswordUtilityDialog is a QWidget; wrap show/hide locally
        dlg.setWindowTitle("Password Utility")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.Window)
        dlg.show()

    def _update_clock(self) -> None:
        self.clock_label.setText(datetime.now().strftime("%d-%b-%Y  %H:%M:%S"))

    def closeEvent(self, event) -> None:
        if hasattr(self.app_state, 'connection_manager') and self.app_state.connection_manager:
            self.app_state.connection_manager.stop()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
        event.accept()
