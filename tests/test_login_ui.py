import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

from src.ui.app_state import AppState
from src.ui.login_window import LoginWindow

_TOUCHED = (
    "user_repo", "model_repo", "plc_profile_repo", "connection_manager",
    "write_manager", "is_plc_connected", "current_user", "current_model",
    "current_model_id", "model_push_status", "param_repo",
)

@pytest.fixture
def mock_state(tmp_path):
    state = AppState.get_instance()
    saved = {n: getattr(state, n, None) for n in _TOUCHED}
    state.user_repo = MagicMock()
    state.model_repo = MagicMock()
    state.plc_profile_repo = MagicMock()
    # login_window._on_model_selected validates via the (legacy) param repo
    state.param_repo = MagicMock()
    state.param_repo.validate_model_parameters.return_value = []
    state.connection_manager = MagicMock()
    state.write_manager = MagicMock()
    state.is_plc_connected = True
    
    # Reset some app state to clean up across tests
    state.current_user = None
    state.current_model = None
    state.current_model_id = None
    state.model_push_status = "never"
    yield state
    for name, value in saved.items():
        setattr(state, name, value)

@pytest.fixture
def login_win(qtbot, mock_state):
    win = LoginWindow(mock_state)
    qtbot.addWidget(win)
    win.show()
    return win

class TestLoginWindow:
    def test_window_opens_correct_size(self, login_win):
        # Layout-driven size (content card is 920px wide)
        assert login_win.width() >= 900

    def test_right_panel_hidden_initially(self, login_win):
        assert not login_win.right_panel.isVisible()

    def test_wrong_password_shows_error(self, login_win, qtbot):
        login_win.role_combo.setCurrentText("Admin")
        login_win.password_field.setText("wrong")
        login_win.app_state.user_repo.authenticate.return_value = None
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert login_win.error_label.isVisible()
        assert not login_win.right_panel.isVisible()

    def test_correct_login_shows_right_panel(self, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin_user", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        login_win.role_combo.setCurrentText("Admin")
        login_win.password_field.setText("correct")
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        
        assert login_win.right_panel.isVisible()
        assert not login_win.error_label.isVisible()

    def test_admin_sees_settings_button(self, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert login_win.settings_btn.isVisible()

    def test_operator_no_settings_button(self, login_win, qtbot):
        user_dict = {"id": 2, "username": "op", "role": "Operator"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert not login_win.settings_btn.isVisible()

    def test_operator_no_reports_button(self, login_win, qtbot):
        user_dict = {"id": 2, "username": "op", "role": "Operator"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert not login_win.reports_btn.isVisible()

    def test_supervisor_sees_reports(self, login_win, qtbot):
        user_dict = {"id": 3, "username": "sup", "role": "Supervisor"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert login_win.reports_btn.isVisible()

    def test_model_combo_populated(self, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        models = [
            {"id": 1, "name": "Model 1", "model_number": "M1"},
            {"id": 2, "name": "Model 2", "model_number": "M2"}
        ]
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = models
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert login_win.model_combo.count() == 3

    def test_model_select_starts_push_worker(self, login_win, qtbot):
        # Login
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = [
            {"id": 1, "name": "Model 1", "model_number": "M1"}
        ]
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        
        # Setup config
        config = {
            "model": {"id": 1, "name": "Model 1"},
            "parameters": []
        }
        login_win.app_state.model_repo.get_full_model_config.return_value = config
        
        with patch("src.ui.login_window.ModelPushWorker") as mock_worker_class:
            mock_worker_instance = MagicMock()
            mock_worker_class.return_value = mock_worker_instance
            
            login_win.model_combo.setCurrentIndex(1)
            
            mock_worker_instance.start.assert_called_once()
            assert login_win._push_worker is not None

    def test_push_success_shows_green(self, login_win, qtbot):
        login_win._on_push_success("Model 1")
        assert "1a6b3a" in login_win.push_status_icon.styleSheet()
        assert login_win.app_state.model_push_status == "success"

    def test_push_failed_shows_red(self, login_win, qtbot):
        login_win._on_push_failed("Model 1", "timeout")
        assert "failed" in login_win.push_status_label.text().lower()
        assert login_win.app_state.model_push_status == "failed"
        assert "c0392b" in login_win.push_status_icon.styleSheet()

    @patch("src.ui.login_window.QMessageBox.warning")
    def test_auto_test_blocked_without_model(self, mock_warning, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        
        qtbot.mouseClick(login_win.auto_test_btn, Qt.MouseButton.LeftButton)
        
        mock_warning.assert_called_once()

    @patch("src.ui.login_window.QMessageBox.question")
    def test_auto_test_push_failed_warns(self, mock_question, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = [
            {"id": 1, "name": "Model 1", "model_number": "M1"}
        ]
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        
        # Select model and simulate failure
        config = {
            "model": {"id": 1, "name": "Model 1"},
            "parameters": []
        }
        login_win.app_state.model_repo.get_full_model_config.return_value = config
        login_win.app_state.is_plc_connected = True
        
        # Patch QThread start to do nothing synchronous or just call the signal directly
        with patch("src.ui.login_window.ModelPushWorker"):
            login_win.model_combo.setCurrentIndex(1)
            login_win._on_push_failed("Model 1", "Error")
            
        mock_question.return_value = QMessageBox.StandardButton.No
        qtbot.mouseClick(login_win.auto_test_btn, Qt.MouseButton.LeftButton)
        mock_question.assert_called_once()

    def test_logout_clears_state(self, login_win, qtbot):
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = []
        
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        assert login_win.right_panel.isVisible()
        
        qtbot.mouseClick(login_win.logout_btn, Qt.MouseButton.LeftButton)
        
        assert not login_win.right_panel.isVisible()
        assert login_win.app_state.current_user is None
        assert login_win.model_combo.count() == 0

    def test_enter_key_triggers_login(self, login_win, qtbot):
        login_win.app_state.user_repo.authenticate.return_value = None
        qtbot.keyClick(login_win.password_field, Qt.Key.Key_Return)
        login_win.app_state.user_repo.authenticate.assert_called_once()

    def test_plc_not_connected_skips_push(self, login_win, qtbot):
        login_win.app_state.is_plc_connected = False
        user_dict = {"id": 1, "username": "admin", "role": "Admin"}
        login_win.app_state.user_repo.authenticate.return_value = user_dict
        login_win.app_state.model_repo.get_all_models.return_value = [
            {"id": 1, "name": "Model 1", "model_number": "M1"}
        ]
        qtbot.mouseClick(login_win.login_btn, Qt.MouseButton.LeftButton)
        
        # Select model
        config = {
            "model": {"id": 1, "name": "Model 1"},
            "parameters": []
        }
        login_win.app_state.model_repo.get_full_model_config.return_value = config
        
        with patch("src.ui.login_window.ModelPushWorker") as mock_worker_class:
            login_win.model_combo.setCurrentIndex(1)
            mock_worker_class.assert_not_called()
            
            assert login_win.app_state.model_push_status == "not_required"
            assert "skipped" in login_win.push_status_label.text().lower()
