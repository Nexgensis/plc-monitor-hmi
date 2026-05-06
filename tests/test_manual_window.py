"""
tests/test_manual_window.py
Unit tests for ManualGrid and ManualTestWindow using pytest-qt.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from src.ui.components.manual_grid import ManualGrid
from src.ui.manual_test_window import ManualTestWindow
from src.ui.app_state import AppState
from src.plc.data_model import ParameterReading
from src.utils.constants import WRITE_MANUAL

@pytest.fixture
def mock_params():
    return [
        {"id": 1, "param_name": "P1", "display_name": "Param 1", "unit": "V", "param_order": 0},
        {"id": 2, "param_name": "P2", "display_name": "Param 2", "unit": "A", "param_order": 1},
        {"id": 3, "param_name": "P3", "display_name": "Param 3", "unit": "W", "param_order": 2},
    ]

@pytest.fixture
def mock_state(mock_params):
    state = MagicMock(spec=AppState)
    state.get_current_parameters.return_value = mock_params
    state.is_plc_connected = True
    state.current_user = {"id": 1, "username": "admin"}
    state.plc_profile = {"start_coil": 400}
    state.current_model = {"model": {"name": "Test Model"}}
    return state

class TestManualGrid:
    def test_column_count_matches_params(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        # 1 label col + 3 param cols = 4
        assert grid.columnCount() == 4

    def test_button_rows_have_cell_widgets(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        # Rows 1, 2, 3 should have QPushButtons in col 1, 2, 3
        for r in range(1, 4):
            for c in range(1, 4):
                btn = grid.cellWidget(r, c)
                assert isinstance(btn, QPushButton)

    def test_value_rows_are_read_only(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        # Rows 4, 5, 6 are values
        for r in range(4, 7):
            for c in range(1, 4):
                item = grid.item(r, c)
                assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_update_readings_changes_text(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        # Mock readings
        readings = {
            "P1": ParameterReading(scaled_value=5.123),
            "P2": ParameterReading(scaled_value=10.456),
            "P3": ParameterReading(scaled_value=1.234)
        }
        grid.update_readings(readings)
        
        # Row 4 is Output Current (assuming index matches update_readings logic)
        # Wait, in my ManualGrid implementation:
        # P1 -> Col 1
        # Row 4: Output Current
        assert grid.item(4, 1).text() == "5.123"
        assert grid.item(4, 2).text() == "10.456"

    def test_no_setitem_after_init(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        # Monkeypatch setItem to catch calls during update
        with patch.object(grid, 'setItem') as mock_set:
            grid.update_readings({"P1": ParameterReading(scaled_value=1.0)})
            mock_set.assert_not_called()

    def test_reset_all_zeros_cells(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        # Set some values first
        grid.update_readings({"P1": ParameterReading(scaled_value=5.0)})
        grid.reset_all()
        
        assert grid.item(4, 1).text() == "0.000"
        assert grid.item(5, 1).text() == "0.000"

    def test_trigger_calls_driver_write_coil(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        mock_driver = MagicMock()
        mock_state.connection_manager.get_driver.return_value = mock_driver
        
        # Click "Supply ON" for P1 (Row 1, Col 1)
        btn = grid.cellWidget(1, 1)
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        
        # Coil for P1 (order 0) Action 0 (OK Polarity) = 400 + 0*3 + 0 = 400
        mock_driver.write_coil.assert_called_with(400, True)
        # Also check write manager call
        mock_state.write_manager.write_and_verify.assert_called()

    def test_button_flash_amber_on_click(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        btn = grid.cellWidget(1, 1)
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        
        assert "#d4890a" in btn.styleSheet()

    def test_set_buttons_enabled_false(self, qtbot, mock_params, mock_state):
        grid = ManualGrid(mock_params, mock_state)
        qtbot.addWidget(grid)
        
        grid.set_buttons_enabled(False)
        btn = grid.cellWidget(1, 1)
        assert not btn.isEnabled()

class TestManualTestWindow:
    def test_title_contains_model_name(self, qtbot, mock_state):
        # ManualTestWindow(db, app_state, connection_manager, parent=None)
        win = ManualTestWindow(None, mock_state, mock_state.connection_manager)
        qtbot.addWidget(win)
        assert "Test Model" in win.windowTitle()

    def test_disconnect_disables_buttons(self, qtbot, mock_state):
        win = ManualTestWindow(None, mock_state, mock_state.connection_manager)
        qtbot.addWidget(win)
        
        # Emit signal from mock connection manager
        mock_state.connection_manager.connection_state_changed.emit(False)
        
        btn = win.manual_grid.cellWidget(1, 1)
        assert not btn.isEnabled()

    def test_close_writes_reset_coil(self, qtbot, mock_state):
        win = ManualTestWindow(None, mock_state, mock_state.connection_manager)
        qtbot.addWidget(win)
        
        mock_driver = MagicMock()
        mock_state.connection_manager.get_driver.return_value = mock_driver
        
        # Call close logic (or trigger close event)
        win._on_close()
        
        # Reset coil = 400 + 2 = 402
        mock_driver.write_coil.assert_called_with(402, True)

    def test_voltage_submit_writes_register(self, qtbot, mock_state):
        win = ManualTestWindow(None, mock_state, mock_state.connection_manager)
        qtbot.addWidget(win)
        
        mock_driver = MagicMock()
        mock_state.connection_manager.get_driver.return_value = mock_driver
        
        win.input_voltage.setValue(14.5)
        qtbot.mouseClick(win.btn_submit_voltage, Qt.MouseButton.LeftButton)
        
        # 14.5 * 10 = 145. Register 50.
        mock_driver.write_holding_register.assert_called_with(50, 145)
