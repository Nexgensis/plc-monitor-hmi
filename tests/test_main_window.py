import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QLineEdit, QLabel
from PyQt6.QtCore import Qt, QPoint

from src.ui.main_window import MainWindow
from src.ui.app_state import AppState
from src.db.database import Database
from src.db.seed import seed_database
from src.db.user_repo import UserRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.plc_profile_repo import PLCProfileRepository
from src.utils.constants import (
    PAGE_MODEL, PAGE_SETTINGS, ROLE_ADMIN, ROLE_OPERATOR
)

@pytest.fixture
def state(tmp_path):
    """Provides a seeded database and app state with mocks for hardware managers."""
    db_path = tmp_path / "test_ui.db"
    db = Database(str(db_path))
    db.initialize()
    seed_database(db)
    
    s = AppState.get_instance()
    # Manually reset singleton fields for test isolation
    s.current_user = None
    s.current_model = None
    s.db = db
    s.user_repo = UserRepository(db)
    s.model_repo = ModelRepository(db)
    s.param_repo = ParameterRepository(db)
    s.session_repo = SessionRepository(db)
    s.report_repo = ReportRepository(db)
    s.plc_profile_repo = PLCProfileRepository(db)
    
    s.plc_profile = s.plc_profile_repo.get_profile()
    s.is_plc_configured = False
    s.d21_messages = s.plc_profile_repo.get_d21_messages()
    
    s.connection_manager = MagicMock()
    s.write_manager = MagicMock()
    
    return s

class TestLoginOverlay:
    def test_overlay_visible_on_startup(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert window.page_stack.currentIndex() == 0
        assert window.login_overlay.isVisible()

    def test_wrong_password_shows_error(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        overlay.role_combo.setCurrentText("Admin")
        overlay.password_field.setText("wrong_pass")
        qtbot.mouseClick(overlay.login_btn, Qt.MouseButton.LeftButton)
        
        assert overlay.error_lbl.isVisible()
        assert "Invalid" in overlay.error_lbl.text()

    def test_empty_password_shows_error(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        overlay.password_field.setText("")
        qtbot.mouseClick(overlay.login_btn, Qt.MouseButton.LeftButton)
        
        assert overlay.error_lbl.isVisible()
        assert "Enter password" in overlay.error_lbl.text()

    def test_correct_login_calls_callback(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        overlay.role_combo.setCurrentText("Admin")
        overlay.password_field.setText("Admin@1234")
        qtbot.mouseClick(overlay.login_btn, Qt.MouseButton.LeftButton)
        
        assert state.current_user is not None
        assert window.page_stack.currentIndex() == 1 # Model Page

    def test_enter_key_triggers_login(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        overlay.password_field.setText("wrong")
        qtbot.keyClick(overlay.password_field, Qt.Key.Key_Enter)
        assert overlay.error_lbl.isVisible()

    def test_eye_toggle_changes_echo_mode(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        assert overlay.password_field.echoMode() == QLineEdit.EchoMode.Password
        qtbot.mouseClick(overlay.eye_btn, Qt.MouseButton.LeftButton)
        assert overlay.password_field.echoMode() == QLineEdit.EchoMode.Normal
        qtbot.mouseClick(overlay.eye_btn, Qt.MouseButton.LeftButton)
        assert overlay.password_field.echoMode() == QLineEdit.EchoMode.Password

    def test_reset_clears_fields(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        overlay = window.login_overlay
        
        overlay.password_field.setText("some_text")
        overlay.reset()
        assert overlay.password_field.text() == ""

    def test_plc_notice_shown_when_unconfigured(self, qtbot, state):
        state.is_plc_configured = False
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert window.login_overlay.notice_frame.isVisible()

class TestMainWindow:
    def test_window_shows_login_first(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert window.page_stack.currentIndex() == 0

    def test_sidebar_hidden_before_login(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert not window.sidebar.theme_btn.isVisible()

    def test_navigate_to_model_page(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        assert window.page_stack.currentIndex() == 1

    def test_navigate_settings_blocked_for_operator(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "op", "role": "OPERATOR"})
        
        window.navigate_to(PAGE_SETTINGS)
        assert window.page_stack.currentIndex() != 4 # Settings index is 4

    def test_on_logout_shows_login_overlay(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        window.on_logout()
        assert window.page_stack.currentIndex() == 0

    def test_theme_toggle_calls_theme_manager(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        with patch("src.ui.theme_manager.ThemeManager.apply") as mock_apply:
            window.on_theme_toggle()
            mock_apply.assert_called()

class TestModelPage:
    def test_4_model_buttons_created(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        # 4 models in seed: SW-0256, SW-0256A, SW-0256C, SW-0256U
        assert len(window.model_page._model_buttons) == 4

    def test_model_buttons_in_sort_order(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        # Grid layout items are ordered. SW-0256 has sort_order 10.
        first_btn = window.model_page.model_grid.itemAt(0).widget()
        assert "SW-0256" in first_btn.findChild(QLabel).text()

    def test_select_model_sets_app_state(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        
        first_btn = window.model_page.model_grid.itemAt(0).widget()
        qtbot.mouseClick(first_btn, Qt.MouseButton.LeftButton)
        assert state.current_model is not None
        assert state.current_model["model"]["name"] == "SW-0256"

    def test_select_model_updates_connection_manager(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        
        first_btn = window.model_page.model_grid.itemAt(0).widget()
        qtbot.mouseClick(first_btn, Qt.MouseButton.LeftButton)
        state.connection_manager.update_parameters.assert_called()

    def test_push_not_started_when_disconnected(self, qtbot, state):
        state.is_plc_connected = False
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        
        with patch("src.plc.model_push_worker.ModelPushWorker.start") as mock_start:
            first_btn = window.model_page.model_grid.itemAt(0).widget()
            qtbot.mouseClick(first_btn, Qt.MouseButton.LeftButton)
            mock_start.assert_not_called()

    def test_start_test_btn_hidden_initially(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        assert not window.model_page.start_test_btn.isVisible()

    def test_start_test_btn_shown_after_select(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        
        first_btn = window.model_page.model_grid.itemAt(0).widget()
        qtbot.mouseClick(first_btn, Qt.MouseButton.LeftButton)
        assert window.model_page.start_test_btn.isVisible()

    def test_unconfigured_shows_settings_prompt(self, qtbot, state):
        state.is_plc_configured = False
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        # The prompt frame is dynamic
        assert window.model_page.push_status_frame.isVisible()

class TestSidebar:
    def test_nav_items_created(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        assert len(window.sidebar._nav_buttons) == 6

    def test_active_item_has_active_property(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        btn = window.sidebar._nav_buttons[PAGE_MODEL]
        assert btn.property("active") is True

    def test_settings_hidden_for_operator(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "op", "role": "OPERATOR"})
        assert not window.sidebar._nav_buttons[PAGE_SETTINGS].isVisible()

    def test_theme_icon_changes_on_toggle(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        
        initial_icon = window.sidebar.theme_btn.findChildren(QLabel)[0].text()
        window.on_theme_toggle()
        new_icon = window.sidebar.theme_btn.findChildren(QLabel)[0].text()
        assert initial_icon != new_icon

class TestStatusBar:
    def test_d21_message_shown(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_d21_message(1, "TEST MSG", "green")
        assert "TEST MSG" in window.status_bar.d21_lbl.text()

    def test_d21_zero_shows_ready(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_d21_message(0, "", "green")
        assert "[READY]" in window.status_bar.d21_lbl.text()

    def test_green_color_for_message_1(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_d21_message(1, "G", "green")
        assert "color: #22c55e" in window.status_bar.d21_lbl.styleSheet()

    def test_red_color_for_message_2(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_d21_message(2, "R", "red")
        assert "color: #ef4444" in window.status_bar.d21_lbl.styleSheet()
