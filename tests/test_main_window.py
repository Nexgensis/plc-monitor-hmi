import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QLineEdit, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPoint

from src.ui.main_window import MainWindow
from src.ui.app_state import AppState
from src.db.database import Database
from src.db.seed import seed_database
from src.db.user_repo import UserRepository
from src.db.model_repo import ModelRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.register_library_repo import RegisterLibraryRepo
from src.db.model_map_repo import ModelMapRepo
from src.db.control_repo import ControlRegisterRepo
from src.db.io_list_repo import IOListRepo
from src.db.message_repo import MessageRegisterRepo
from src.db.app_config_repo import AppConfigRepo
from src.utils.constants import (
    PAGE_MODEL, PAGE_SETTINGS, ROLE_ADMIN, ROLE_OPERATOR
)

_STATE_FIELDS = (
    "current_user", "current_model", "current_model_id", "db",
    "user_repo", "model_repo", "session_repo", "report_repo",
    "plc_profile_repo", "profile_repo", "library_repo", "map_repo",
    "control_repo", "io_repo", "msg_repo", "config_repo", "block_repo",
    "plc_profile", "is_plc_configured", "is_plc_connected",
    "connection_manager", "write_manager", "message_register",
    "message_lookup", "poll_registers", "dashboard_registers",
)

@pytest.fixture
def state(tmp_path):
    """Provides a seeded database and app state with mocks for hardware managers."""
    db_path = tmp_path / "test_ui.db"
    db = Database(str(db_path))
    db.initialize()
    seed_database(db)
    
    s = AppState.get_instance()
    saved = {n: getattr(s, n) for n in _STATE_FIELDS if hasattr(s, n)}

    # Manually reset singleton fields for test isolation
    s.current_user = None
    s.current_model = None
    s.current_model_id = None
    s.db = db
    s.user_repo = UserRepository(db)
    s.model_repo = ModelRepository(db)
    s.session_repo = SessionRepository(db)
    s.report_repo = ReportRepository(db)
    s.plc_profile_repo = PLCProfileRepository(db)
    s.profile_repo = s.plc_profile_repo
    s.library_repo = RegisterLibraryRepo(db)
    s.map_repo = ModelMapRepo(db)
    s.control_repo = ControlRegisterRepo(db)
    s.io_repo = IOListRepo(db)
    s.msg_repo = MessageRegisterRepo(db)
    s.config_repo = AppConfigRepo(db)
    s.block_repo = None
    s.message_register = None
    s.message_lookup = {}

    # Seed no longer creates models — recreate the historical 4-model set
    s.model_repo.create_model("SW-0256", sort_order=10)
    s.model_repo.create_model("SW-0256A", sort_order=20)
    s.model_repo.create_model("SW-0256C", sort_order=30)
    s.model_repo.create_model("SW-0256U", sort_order=40)
    
    s.plc_profile = s.plc_profile_repo.get_profile()
    s.is_plc_configured = False
    
    s.connection_manager = MagicMock()
    s.write_manager = MagicMock()
    
    yield s
    for name, value in saved.items():
        setattr(s, name, value)

@pytest.fixture
def window(qtbot, state):
    """A constructed (not yet shown) MainWindow."""
    win = MainWindow(state)
    qtbot.addWidget(win)
    return win

@pytest.fixture
def overlay(qtbot, state, window):
    """MainWindow started up past the setup wizard, shown, login overlay visible."""
    state.config_repo.mark_setup_complete()
    window.on_startup()
    window.show()
    QApplication.processEvents()
    return window.login_overlay

class TestLoginOverlay:
    def test_overlay_visible_on_startup(self, overlay, window):
        assert window.page_stack.currentWidget() is overlay
        assert overlay.isVisible()

    def test_wrong_password_shows_error(self, overlay):
        overlay.role_combo.setCurrentText("ADMIN")
        overlay.password_input.setText("wrong_pass")
        overlay.login_btn.click()
        
        assert overlay.error_lbl.isVisible()
        assert "Invalid" in overlay.error_lbl.text()

    def test_empty_password_shows_error(self, overlay):
        overlay.password_input.setText("")
        overlay.login_btn.click()
        
        assert overlay.error_lbl.isVisible()
        assert "enter your password" in overlay.error_lbl.text().lower()

    def test_correct_login_calls_callback(self, overlay, window, state):
        overlay.role_combo.setCurrentText("ADMIN")
        overlay.password_input.setText("Admin@1234")
        overlay.login_btn.click()
        
        assert state.current_user is not None
        assert window.page_stack.currentWidget() is window.model_page

    def test_enter_key_triggers_login(self, overlay):
        overlay.password_input.setText("wrong")
        overlay.password_input.setFocus()
        from PyQt6.QtTest import QTest
        QTest.keyClick(overlay.password_input, Qt.Key.Key_Return)
        assert overlay.error_lbl.isVisible()

    def test_eye_toggle_changes_echo_mode(self, overlay):
        assert overlay.password_input.echoMode() == QLineEdit.EchoMode.Password
        overlay.eye_btn.click()
        assert overlay.password_input.echoMode() == QLineEdit.EchoMode.Normal
        overlay.eye_btn.click()
        assert overlay.password_input.echoMode() == QLineEdit.EchoMode.Password

    def test_reset_clears_fields(self, overlay):
        overlay.password_input.setText("some_text")
        overlay.reset()
        assert overlay.password_input.text() == ""
        assert not overlay.error_lbl.isVisible()

    def test_plc_notice_shown_when_unconfigured(self, overlay, state):
        state.is_plc_configured = False
        overlay.reset()
        assert overlay.plc_notice.isVisible()

class TestMainWindow:
    def test_window_shows_login_first(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert window.page_stack.currentIndex() == 0

    def test_sidebar_hidden_before_login(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        assert not window.sidebar.theme_btn.isVisible()

    def test_navigate_to_model_page(self, window, state):
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        assert window.page_stack.currentWidget() is window.model_page

    def test_navigate_settings_blocked_for_operator(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "op", "role": "OPERATOR"})
        
        window.navigate_to(PAGE_SETTINGS)
        assert window.page_stack.indexOf(window.settings_page) != \
            window.page_stack.currentIndex()

    def test_on_logout_shows_login_overlay(self, window, state):
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        window.on_logout()
        assert window.page_stack.currentWidget() is window.login_overlay

    def test_theme_toggle_calls_theme_manager(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        with patch("src.ui.theme_manager.ThemeManager.apply") as mock_apply:
            window.on_theme_toggle()
            mock_apply.assert_called()

class TestModelPage:
    def _login(self, window, state, role="ADMIN", username="admin"):
        window.on_login_success({"username": username, "role": role})

    def _first_card(self, window):
        return window.model_page.grid.itemAt(0).widget()

    def test_4_model_buttons_created(self, window, state):
        self._login(window, state)
        # 4 models created in fixture: SW-0256, SW-0256A, SW-0256C, SW-0256U
        assert window.model_page.grid.count() == 4

    def test_model_buttons_in_sort_order(self, window, state):
        self._login(window, state)
        first_btn = self._first_card(window)
        assert isinstance(first_btn, QPushButton)
        assert first_btn.accessibleName() == "SW-0256"

    def test_select_model_sets_app_state(self, window, state):
        self._login(window, state)
        
        first_btn = self._first_card(window)
        first_btn.click()
        assert state.current_model is not None
        assert state.current_model["name"] == "SW-0256"
        assert state.current_model_id is not None

    def test_select_model_updates_connection_manager(self, window, state):
        self._login(window, state)
        
        first_btn = self._first_card(window)
        first_btn.click()
        state.connection_manager.update_poll_list.assert_called()

    def test_model_selection_completes_when_disconnected(self, qtbot, state):
        state.is_plc_connected = False
        window = MainWindow(state)
        qtbot.addWidget(window)
        self._login(window, state)

        first_btn = self._first_card(window)
        first_btn.click()
        # Push-to-PLC worker retired (cleanup D9): model selection still
        # completes local sync regardless of connection state.
        assert state.current_model is not None

    def test_start_test_btn_disabled_initially(self, window, state):
        self._login(window, state)
        assert not window.model_page.btn_start.isEnabled()

    def test_start_test_btn_enabled_after_select(self, window, state):
        self._login(window, state)
        
        first_btn = self._first_card(window)
        first_btn.click()
        assert window.model_page.btn_start.isEnabled()

    def test_unconfigured_shows_settings_prompt(self, window, state):
        state.is_plc_configured = False
        self._login(window, state)
        assert "not configured" in window.model_page.plc_status_lbl.text()

class TestSidebar:
    def test_nav_items_created(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        assert len(window.sidebar._rows) == 7

    def test_active_item_has_active_property(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        row = window.sidebar._rows[PAGE_MODEL]
        assert row.property("active") is True

    def test_settings_hidden_for_operator(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "op", "role": "OPERATOR"})
        assert not window.sidebar._rows[PAGE_SETTINGS].isVisible()

    def test_connection_status_dot(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.on_login_success({"username": "admin", "role": "ADMIN"})
        window.sidebar.set_connection_status(True)
        assert window.sidebar.status_dot.property("online") is True
        window.sidebar.set_connection_status(False)
        assert window.sidebar.status_dot.property("online") is False

class TestStatusBar:
    def test_message_shown(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_message(1, "TEST MSG", "green")
        assert "TEST MSG" in window.status_bar.message_lbl.text()

    def test_zero_shows_ready(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_message(0, "", "green")
        assert "[READY]" in window.status_bar.message_lbl.text()

    def test_message_includes_timestamp(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_message(1, "TICK", "green")
        text = window.status_bar.message_lbl.text()
        # "[HH:MM:SS] TICK"
        assert text.endswith("] TICK")
        time_part = text[1:9]
        assert len(time_part) == 8 and time_part[2] == ":" and time_part[5] == ":"

    def test_empty_text_shows_ready(self, qtbot, state):
        window = MainWindow(state)
        qtbot.addWidget(window)
        window.status_bar.show_message(1, "", "red")
        assert "[READY]" in window.status_bar.message_lbl.text()
