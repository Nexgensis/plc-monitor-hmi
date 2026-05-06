# tests/test_settings_window.py
"""
Unit tests for SettingsWindow and its components using pytest-qt.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QInputDialog

from src.db.database import Database
from src.db.seed import seed_database
from src.db.user_repo import UserRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.plc_profile_repo import PLCProfileRepository
from src.ui.app_state import AppState
from src.ui.settings_window import SettingsWindow
from src.ui.components.param_editor import ParamEditor
from src.ui.components.register_mapper import RegisterMapper
from src.ui.components.limits_editor import LimitsEditor, LimitsPushWorker
from src.ui.components.plc_block_editor import PLCBlockEditor
from src.ui.dialogs.confirm_dialog import ConfirmDialog


@pytest.fixture
def state_with_db(tmp_path):
    """Fixture to provide a clean AppState with a seeded in-memory-like DB."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    db.initialize()
    seed_database(db)
    
    state = AppState.get_instance()
    # Reset singleton state for testing
    state.db = db
    state.user_repo = UserRepository(db)
    state.model_repo = ModelRepository(db)
    state.param_repo = ParameterRepository(db)
    state.session_repo = SessionRepository(db)
    state.report_repo = ReportRepository(db)
    state.plc_profile_repo = PLCProfileRepository(db)
    
    state.current_user = {"id": 1, "username": "admin", "role": "ADMIN"}
    state.plc_profile = state.plc_profile_repo.get_profile()
    
    state.connection_manager = MagicMock()
    state.write_manager = MagicMock()
    state.is_plc_connected = False
    
    return state


class TestParamEditor:
    def test_loads_parameters_into_table(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        
        # Load MI-7646AZ (id=1 from seed)
        editor.load_model(1)
        
        assert editor.param_table.rowCount() == 3
        assert editor.param_table.item(0, 1).text() == "Horn Voltage"

    def test_add_parameter_inserts_row(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        qtbot.mouseClick(editor.btn_add, Qt.MouseButton.LeftButton)
        assert editor.param_table.rowCount() == 4
        assert editor.is_dirty() is True

    def test_delete_param_requires_confirm(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        editor.param_table.selectRow(0)
        
        with patch.object(ConfirmDialog, 'ask', return_value=False) as mock_ask:
            qtbot.mouseClick(editor.btn_delete, Qt.MouseButton.LeftButton)
            mock_ask.assert_called()
            assert editor.param_table.rowCount() == 3

    def test_move_up_swaps_rows(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        # Select row 1 (High Beam)
        editor.param_table.selectRow(1)
        qtbot.mouseClick(editor.btn_up, Qt.MouseButton.LeftButton)
        
        assert editor.param_table.item(0, 1).text() == "High Beam Voltage"
        assert editor.is_dirty() is True

    def test_apply_changes_updates_cache(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        editor.param_table.selectRow(0)
        editor.name_field.setText("New Horn Name")
        qtbot.mouseClick(editor.btn_apply, Qt.MouseButton.LeftButton)
        
        assert editor.param_table.item(0, 1).text() == "New Horn Name"
        assert editor.is_dirty() is True

    def test_save_calls_replace_all(self, qtbot, state_with_db):
        editor = ParamEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        # Modify something to make it dirty
        editor.param_table.selectRow(0)
        editor.name_field.setText("Modified")
        editor._on_apply_changes()
        
        with patch.object(state_with_db.param_repo, 'replace_all_parameters') as mock_save:
            qtbot.mouseClick(editor.btn_save, Qt.MouseButton.LeftButton)
            mock_save.assert_called_once()
            assert editor.is_dirty() is False


class TestRegisterMapper:
    def test_loads_spinboxes_with_current_values(self, qtbot, state_with_db):
        mapper = RegisterMapper(state_with_db)
        qtbot.addWidget(mapper)
        mapper.load_model(1)
        
        # Horn measured_register = 100
        spin = mapper.reg_table.cellWidget(0, 1) # _COL_MEAS is 1
        assert spin.value() == 100

    def test_duplicate_detection_shows_banner(self, qtbot, state_with_db):
        mapper = RegisterMapper(state_with_db)
        qtbot.addWidget(mapper)
        mapper.show()
        mapper.load_model(1)
    
        # Set Horn to 101 (same as High Beam)
        spin0 = mapper.reg_table.cellWidget(0, 1)
        spin0.setValue(101)
        
        # Ensure signals are processed
        qtbot.wait(100)
        
        assert mapper.dup_banner.isVisible() is True
        assert "Duplicate" in mapper.dup_banner.text()

    def test_modbus_calc_updates_on_change(self, qtbot, state_with_db):
        mapper = RegisterMapper(state_with_db)
        qtbot.addWidget(mapper)
        mapper.load_model(1)
        
        spin = mapper.reg_table.cellWidget(0, 1)
        spin.setValue(200) # D200
        
        # Delta modbus for D200 depends on logic in d_register_to_modbus
        # For Delta, D0 is 4096 (0x1000). D200 is 4096 + 200 = 4296.
        # But our mapper shows it in text.
        item = mapper.reg_table.item(0, 5) # _COL_MODBUS is 5
        assert item.text() != "—"

    def test_save_calls_update_registers(self, qtbot, state_with_db):
        mapper = RegisterMapper(state_with_db)
        qtbot.addWidget(mapper)
        mapper.load_model(1)
        
        with patch.object(state_with_db.param_repo, 'update_parameter_registers') as mock_update:
            qtbot.mouseClick(mapper.btn_save, Qt.MouseButton.LeftButton)
            assert mock_update.call_count == 3


class TestLimitsEditor:
    def test_loads_spinboxes_with_limit_values(self, qtbot, state_with_db):
        editor = LimitsEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        # Horn limit_min_value = 4000.0
        spin = editor.limits_table.cellWidget(0, 3) # _COL_MIN is 3
        assert spin.value() == 4000.0

    def test_min_greater_than_max_invalid(self, qtbot, state_with_db):
        editor = LimitsEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        spin_min = editor.limits_table.cellWidget(0, 3)
        spin_max = editor.limits_table.cellWidget(0, 4)
        
        spin_min.setValue(5000)
        spin_max.setValue(4000)
        
        # Should have a red border (stylesheet set)
        assert "border" in spin_min.styleSheet()

    def test_push_blocked_when_plc_disconnected(self, qtbot, state_with_db):
        editor = LimitsEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        state_with_db.is_plc_connected = False
        
        with patch.object(QMessageBox, 'warning') as mock_warn:
            qtbot.mouseClick(editor.btn_save_push, Qt.MouseButton.LeftButton)
            mock_warn.assert_called()


class TestPLCBlockEditor:
    def test_loads_block_values_into_table(self, qtbot, state_with_db):
        editor = PLCBlockEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        assert editor.values_table.rowCount() == 6
        spin = editor.values_table.cellWidget(0, 1)
        assert spin.value() == 37

    def test_save_to_db_updates_model(self, qtbot, state_with_db):
        editor = PLCBlockEditor(state_with_db)
        qtbot.addWidget(editor)
        editor.load_model(1)
        
        with patch.object(state_with_db.model_repo, 'update_model') as mock_update:
            qtbot.mouseClick(editor.btn_save_db, Qt.MouseButton.LeftButton)
            mock_update.assert_called_once()


class TestSettingsWindow:
    def test_model_list_shows_all_models(self, qtbot, state_with_db):
        win = SettingsWindow(state_with_db)
        qtbot.addWidget(win)
        
        assert win.model_list.count() >= 1
        assert "MI-7646AZ" in win.model_list.item(0).text()

    def test_select_model_loads_all_tabs(self, qtbot, state_with_db):
        win = SettingsWindow(state_with_db)
        qtbot.addWidget(win)
        
        with patch.object(win.param_editor, 'load_model') as m1, \
             patch.object(win.register_mapper, 'load_model') as m2, \
             patch.object(win.limits_editor, 'load_model') as m3, \
             patch.object(win.block_editor, 'load_model') as m4:
            
            win.model_list.setCurrentRow(0)
            m1.assert_called_with(1)
            m2.assert_called_with(1)
            m3.assert_called_with(1)
            m4.assert_called_with(1)

    def test_add_model_dialog_opens(self, qtbot, state_with_db):
        win = SettingsWindow(state_with_db)
        qtbot.addWidget(win)
        
        with patch('src.ui.settings_window.ModelDialog') as MockDlg:
            MockDlg.return_value.exec.return_value = 0 # Reject
            qtbot.mouseClick(win.btn_add_model, Qt.MouseButton.LeftButton)
            assert MockDlg.called

    def test_dirty_close_shows_confirm(self, qtbot, state_with_db):
        win = SettingsWindow(state_with_db)
        qtbot.addWidget(win)
        win.model_list.setCurrentRow(0)
        
        # Make dirty
        win.param_editor._set_dirty(True)
        
        with patch.object(ConfirmDialog, 'ask', return_value=False) as mock_ask:
            win.close()
            mock_ask.assert_called()
