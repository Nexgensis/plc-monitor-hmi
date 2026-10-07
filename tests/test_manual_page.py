"""
tests/test_manual_page.py
Unit tests for the live ManualPage (manual control panel).

Replaces the legacy test_manual_window.py which targeted the unused
ManualTestWindow/ManualGrid modules (superseded by pages/manual_page.py).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtWidgets import QPushButton, QMessageBox

from src.db.database import Database
from src.db.control_repo import ControlRegisterRepo
from src.db.model_repo import ModelRepository
from src.db.model_map_repo import ModelMapRepo
from src.db.register_library_repo import RegisterLibraryRepo
from src.db.seed import seed_database
from src.ui.app_state import AppState
from src.ui.pages.manual_page import ManualPage
from src.plc.data_model import PLCDataModel, RegisterReading
from src.utils.constants import CTRL_START_TEST, CTRL_STOP_TEST, CTRL_CUSTOM

_STATE_FIELDS = (
    "current_user", "current_model_id", "current_model", "db",
    "connection_manager", "write_manager", "is_plc_connected",
    "profile_repo", "library_repo", "model_repo", "map_repo", "control_repo",
    "io_repo", "msg_repo", "session_repo", "report_repo", "config_repo",
    "user_repo", "block_repo", "poll_registers", "dashboard_registers",
    "message_register", "message_lookup",
)


def _teardown_widget(widget) -> None:
    try:
        for timer in widget.findChildren(QTimer):
            timer.stop()
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    except RuntimeError:
        pass


@pytest.fixture
def env(qtbot, tmp_path):
    """ManualPage wired to a fresh DB and a mock connection manager."""
    db = Database(str(tmp_path / "manual.db"))
    db.initialize()
    seed_database(db)

    s = AppState.get_instance()
    saved = {n: getattr(s, n) for n in _STATE_FIELDS if hasattr(s, n)}

    data_model = PLCDataModel()
    s.current_user = {"id": 1, "username": "admin", "role": "ADMIN"}
    s.current_model_id = None
    s.current_model = None
    s.db = db
    s.profile_repo = None
    s.library_repo = RegisterLibraryRepo(db)
    s.model_repo = ModelRepository(db)
    s.map_repo = ModelMapRepo(db)
    s.control_repo = ControlRegisterRepo(db)
    s.connection_manager = MagicMock(data_model=data_model)
    s.write_manager = MagicMock()
    s.is_plc_connected = True

    page = ManualPage(s)
    qtbot.addWidget(page)
    try:
        yield page, s, data_model
    finally:
        _teardown_widget(page)
        for name, value in saved.items():
            setattr(s, name, value)
        db.close_all()


def _mk_register(s, name, address=100, rtype="HOLDING", unit=""):
    return s.library_repo.create_register(name, address, rtype, "INT16",
                                          unit=unit, access="READ_WRITE")


def _mk_control(s, name, ctype=CTRL_CUSTOM, register_id=None,
                confirm_required=0):
    if register_id is None:
        register_id = _mk_register(s, f"{name} reg")
    return s.control_repo.create_control(name, register_id, ctype,
                                         confirm_required=confirm_required)


def _buttons(page):
    out = []
    for i in range(page.btn_vbox.count()):
        w = page.btn_vbox.itemAt(i).widget()
        if isinstance(w, QPushButton):
            out.append(w)
    return out


class TestControls:

    def test_controls_built_from_repo(self, env):
        page, s, _ = env
        _mk_control(s, "Start Cycle", CTRL_START_TEST)
        _mk_control(s, "Stop Cycle", CTRL_STOP_TEST)
        _mk_control(s, "Custom Thing", CTRL_CUSTOM)
        page._refresh_controls()

        btns = _buttons(page)
        by_name = {b.text(): b for b in btns}
        assert set(by_name) == {"Start Cycle", "Stop Cycle", "Custom Thing"}
        assert by_name["Start Cycle"].objectName() == "btn_success"
        assert by_name["Stop Cycle"].objectName() == "btn_danger"
        assert by_name["Custom Thing"].objectName() == "btn_secondary"

    def test_refresh_controls_replaces_old_buttons(self, env):
        page, s, _ = env
        _mk_control(s, "Only One")
        page._refresh_controls()
        page._refresh_controls()
        assert len(_buttons(page)) == 1

    def test_offline_disables_buttons(self, env):
        page, s, _ = env
        _mk_control(s, "Some Action")
        page._refresh_controls()

        page.on_plc_state_changed(False)
        assert not _buttons(page)[0].isEnabled()
        assert page.plc_status_lbl.text() == "● PLC Offline"

        page.on_plc_state_changed(True)
        assert _buttons(page)[0].isEnabled()
        assert page.plc_status_lbl.text() == "✓ PLC Online"

    def test_execute_control_calls_write_manager(self, env):
        page, s, _ = env
        _mk_control(s, "Fire It")
        control = s.control_repo.get_control_by_type(CTRL_CUSTOM)
        assert control is not None

        with patch.object(QMessageBox, "information") as info:
            page._execute_control(control)

        s.write_manager.execute_control.assert_called_once_with(control, 1)
        info.assert_called_once()

    def test_execute_control_without_user_warns(self, env):
        page, s, _ = env
        s.current_user = None
        control = {"id": 1, "name": "X", "confirm_required": 0}
        with patch.object(QMessageBox, "warning") as warn:
            page._execute_control(control)
        s.write_manager.execute_control.assert_not_called()
        warn.assert_called_once()

    def test_execute_control_without_manager_warns(self, env):
        page, s, _ = env
        s.write_manager = None
        control = {"id": 1, "name": "X", "confirm_required": 0}
        with patch.object(QMessageBox, "warning") as warn:
            page._execute_control(control)
        warn.assert_called_once()

    def test_execute_control_exception_reports_failure(self, env):
        page, s, _ = env
        s.write_manager.execute_control.side_effect = RuntimeError("boom")
        control = {"id": 1, "name": "Bad", "confirm_required": 0}
        with patch.object(QMessageBox, "critical") as crit:
            page._execute_control(control)
        crit.assert_called_once()
        assert "boom" in crit.call_args[0][2]

    def test_confirm_required_can_cancel(self, env):
        page, s, _ = env
        control = {"id": 1, "name": "Danger", "confirm_required": 1}
        with patch("src.ui.pages.manual_page.ConfirmDialog.ask",
                   return_value=False) as ask, \
             patch.object(QMessageBox, "information") as info:
            page._execute_control(control)
        ask.assert_called_once()
        s.write_manager.execute_control.assert_not_called()
        info.assert_not_called()


class TestFilters:

    def test_filters_include_models_and_defaults(self, env):
        page, s, _ = env
        s.model_repo.create_model("MODEL-A")
        s.model_repo.create_model("MODEL-B")
        page._refresh_filters()

        labels = [page.model_filter.itemText(i)
                  for i in range(page.model_filter.count())]
        assert labels[0] == "Current Model Only"
        assert labels[1] == "Show All Mapped"
        assert "MODEL-A" in labels and "MODEL-B" in labels

    def test_current_model_preselected(self, env):
        page, s, _ = env
        mid = s.model_repo.create_model("CURRENT-ONE")
        s.current_model_id = mid
        page._refresh_filters()
        assert page.model_filter.currentData() == mid


class TestLiveTable:

    def test_pending_without_readings(self, env):
        page, s, dm = env
        mid = s.model_repo.create_model("M1")
        rid = _mk_register(s, "LiveReg", address=123)
        s.map_repo.add_mapping(mid, rid, display_name="Live Point")
        s.current_model_id = mid
        page._refresh_filters()
        page._refresh_live_table()

        assert page.live_table.rowCount() == 1
        assert page.live_table.item(0, 0).text() == "Live Point"
        assert page.live_table.item(0, 1).text() == "D123"
        assert page.live_table.item(0, 3).text() == "---"
        assert page.live_table.item(0, 4).text() == "PENDING"

    def test_shows_readings_when_available(self, env):
        page, s, dm = env
        mid = s.model_repo.create_model("M2")
        rid = _mk_register(s, "ReadReg", address=50, unit="V")
        s.map_repo.add_mapping(mid, rid, display_name="Reader")
        s.current_model_id = mid
        page._refresh_filters()

        dm.update_reading(rid, RegisterReading(
            register_id=rid, name="ReadReg", plc_address=50,
            register_type="HOLDING", raw_words=[4321],
            display_value=43.21, display_str="43.21 V", unit="V",
            data_type="INT16",
            timestamp=datetime.now(timezone.utc), read_success=True,
        ))
        page._refresh_live_table()

        assert page.live_table.item(0, 3).text() == "4321"
        assert page.live_table.item(0, 4).text() == "43.21 V"
        assert page.live_table.item(0, 5).text() == "V"

    def test_format_address_prefixes(self, env):
        page, s, _ = env
        cases = [("HOLDING", 10, "D10"), ("COIL", 20, "M20"),
                 ("DISCRETE", 30, "X30"), ("INPUT", 40, "AI40")]
        for rtype, addr, want in cases:
            got = page._format_address({"register_type": rtype,
                                        "register_address": addr})
            assert got == want

    def test_show_all_aggregates_models(self, env):
        page, s, dm = env
        m1 = s.model_repo.create_model("AGG-1")
        m2 = s.model_repo.create_model("AGG-2")
        r1 = _mk_register(s, "AggReg1", address=1)
        r2 = _mk_register(s, "AggReg2", address=2)
        s.map_repo.add_mapping(m1, r1, display_name="A1")
        s.map_repo.add_mapping(m2, r2, display_name="A2")
        s.current_model_id = m1

        page._refresh_filters()
        # Select "Show All Mapped" (data -1)
        idx = page.model_filter.findData(-1)
        page.model_filter.setCurrentIndex(idx)

        assert page.live_table.rowCount() == 2
        names = {page.live_table.item(r, 0).text() for r in range(2)}
        assert names == {"A1", "A2"}

    def test_no_connection_manager_is_noop(self, env):
        page, s, _ = env
        s.connection_manager = None
        page._refresh_live_table()  # must not raise
        assert page.live_table.rowCount() == 0


class TestLifecycle:

    def test_on_page_shown_starts_timer_and_hidden_stops(self, env):
        page, s, _ = env
        page.on_page_shown()
        assert page._live_timer.isActive()
        page.on_page_hidden()
        assert not page._live_timer.isActive()
