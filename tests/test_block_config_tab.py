"""
Phase 5 — CONFIG Register Blocks tab + BlockDialog tests.

Covers:
    - BlockDialog dynamic rules (bit tables, read-only tables, word swap,
      whole-element count) and result validation/coercion
    - ConfigPage tab registration (index 4, tooltip, refresh dispatch)
    - Block table refresh + filtering
    - Add / Edit / Delete flows incl. repo ValueError → error dialog
    - Changes pushed to the poller via refresh_poll_config()

Run: venv\\Scripts\\python.exe -m pytest tests/test_block_config_tab.py -q
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtWidgets import QDialog

from src.db.database import Database
from src.db.block_repo import BlockRepo
from src.ui.app_state import AppState
from src.ui.dialogs import block_dialog as block_dialog_mod
from src.ui.pages import config_page as config_page_mod
from src.ui.pages.config_page import ConfigPage
from src.ui.dialogs.block_dialog import BlockDialog

# ---------------------------------------------------------------------------
# AppState singleton hygiene — snapshot/restore session-wide fields
# ---------------------------------------------------------------------------

_STATE_FIELDS = (
    "current_user", "current_model_id", "db", "connection_manager",
    "write_manager", "data_model", "config_repo", "profile_repo",
    "library_repo", "user_repo", "model_repo", "map_repo", "control_repo",
    "io_repo", "msg_repo", "session_repo", "report_repo", "block_repo",
    "plc_profile", "is_plc_configured", "message_register", "message_lookup",
    "poll_blocks", "poll_registers",
)

DEFAULT_RESULT = {
    "name": "New Block",
    "description": "",
    "register_type": "HOLDING",
    "start_address": 10,
    "count": 4,
    "data_type": "INT16",
    "scale_factor": 1.0,
    "decimal_places": 2,
    "unit": "",
    "word_swap": False,
    "access": "READ_WRITE",
    "group_name": "",
    "row_order": 0,
    "show_value": True,
    "on_label": "ON",
    "off_label": "OFF",
    "is_active": True,
}
_RESULT_FIELDS = tuple(DEFAULT_RESULT)


def _stop_descendant_timers(widget) -> None:
    for timer in widget.findChildren(QTimer):
        timer.stop()


def _teardown_widget(widget) -> None:
    try:
        _stop_descendant_timers(widget)
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    except RuntimeError:
        pass  # already destroyed by pytest-qt


def make_fake_dialog(overlay: dict):
    """BlockDialog stand-in: returns block_data overlaid with `overlay`."""

    class FakeBlockDialog:
        instances: list = []

        def __init__(self, parent=None, block_data=None, is_edit=False):
            self._block_data = dict(block_data or {})
            self._is_edit = is_edit
            FakeBlockDialog.instances.append(self)

        def exec(self) -> bool:
            return True

        def get_result(self) -> dict:
            result = dict(DEFAULT_RESULT)
            for key in _RESULT_FIELDS:
                if key in self._block_data:
                    result[key] = self._block_data[key]
            result.update(overlay)
            return result

    return FakeBlockDialog


@pytest.fixture
def page(qtbot, tmp_path):
    """ConfigPage wired to a fresh DB through the AppState singleton."""
    from src.db.seed import seed_database
    from src.db.app_config_repo import AppConfigRepo
    from src.db.plc_profile_repo import PLCProfileRepository
    from src.db.register_library_repo import RegisterLibraryRepo
    from src.db.user_repo import UserRepository
    from src.db.model_repo import ModelRepository
    from src.db.model_map_repo import ModelMapRepo
    from src.db.control_repo import ControlRegisterRepo
    from src.db.io_list_repo import IOListRepo
    from src.db.message_repo import MessageRegisterRepo
    from src.db.session_repo import SessionRepository
    from src.db.report_repo import ReportRepository

    db = Database(str(tmp_path / "blocks_tab.db"))
    db.initialize()
    seed_database(db)

    s = AppState.get_instance()
    saved = {n: getattr(s, n) for n in _STATE_FIELDS if hasattr(s, n)}

    s.current_user = None
    s.current_model_id = None
    s.db = db
    s.connection_manager = MagicMock()
    s.write_manager = MagicMock()
    s.data_model = None
    s.block_repo = BlockRepo(db)
    s.config_repo = AppConfigRepo(db)
    s.profile_repo = PLCProfileRepository(db)
    s.library_repo = RegisterLibraryRepo(db)
    s.user_repo = UserRepository(db)
    s.model_repo = ModelRepository(db)
    s.map_repo = ModelMapRepo(db)
    s.control_repo = ControlRegisterRepo(db)
    s.io_repo = IOListRepo(db)
    s.msg_repo = MessageRegisterRepo(db)
    s.session_repo = SessionRepository(db)
    s.report_repo = ReportRepository(db)
    s.plc_profile = s.profile_repo.get_profile()
    s.is_plc_configured = False
    s.message_register = None
    s.message_lookup = {}

    cfg = ConfigPage(s, on_plc_reconnect=lambda: None)
    qtbot.addWidget(cfg)
    try:
        yield cfg, s
    finally:
        _teardown_widget(cfg)
        for name, value in saved.items():
            setattr(s, name, value)
        db.close_all()


# ---------------------------------------------------------------------------
# BlockDialog — construction and dynamic rules
# ---------------------------------------------------------------------------

class TestBlockDialogRules:

    @pytest.fixture
    def dlg(self, qtbot):
        d = BlockDialog(None, is_edit=False)
        qtbot.addWidget(d)
        return d

    def _select(self, dlg, reg_type: str) -> None:
        idx = dlg.type_combo.findData(reg_type)
        assert idx >= 0
        dlg.type_combo.setCurrentIndex(idx)

    def test_defaults(self, dlg):
        assert dlg.type_combo.currentData() == "HOLDING"
        assert dlg.access_combo.currentData() == "READ_WRITE"
        assert dlg.active_cb.isChecked()
        assert dlg.count_spin.maximum() == 1000
        assert not dlg.val_cb.isVisibleTo(dlg)

    def test_coil_forces_bool_and_bit_limits(self, dlg):
        self._select(dlg, "COIL")
        assert not dlg.dtype_combo.isEnabled()
        assert dlg.dtype_combo.currentData() == "BOOL"
        assert dlg.count_spin.maximum() == 2000
        assert dlg.val_cb.isVisibleTo(dlg)

    def test_discrete_forces_read_only(self, dlg):
        self._select(dlg, "DISCRETE")
        assert not dlg.access_combo.isEnabled()
        assert dlg.access_combo.currentData() == "READ_ONLY"

    def test_input_forces_read_only(self, dlg):
        self._select(dlg, "INPUT")
        assert not dlg.access_combo.isEnabled()
        assert dlg.access_combo.currentData() == "READ_ONLY"

    def test_holding_restores_editable_access(self, dlg):
        self._select(dlg, "DISCRETE")
        self._select(dlg, "HOLDING")
        assert dlg.access_combo.isEnabled()
        assert dlg.dtype_combo.isEnabled()

    def test_word_swap_only_for_32bit(self, dlg):
        idx = dlg.dtype_combo.findData("FLOAT32")
        dlg.dtype_combo.setCurrentIndex(idx)
        assert dlg.swap_cb.isEnabled()

        idx = dlg.dtype_combo.findData("INT16")
        dlg.dtype_combo.setCurrentIndex(idx)
        assert not dlg.swap_cb.isEnabled()
        assert not dlg.swap_cb.isChecked()

    def test_save_requires_name(self, dlg):
        dlg.name_edit.setText("   ")
        dlg._on_save()
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_save_rejects_zero_scale(self, dlg, monkeypatch):
        monkeypatch.setattr(
            block_dialog_mod.QMessageBox, "warning", lambda *a, **k: None
        )
        dlg.name_edit.setText("Zero Scale")
        dlg.scale_spin.setValue(0.0)
        dlg._on_save()
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_save_rejects_partial_element_count(self, dlg, monkeypatch):
        monkeypatch.setattr(
            block_dialog_mod.QMessageBox, "warning", lambda *a, **k: None
        )
        idx = dlg.dtype_combo.findData("INT32")
        dlg.dtype_combo.setCurrentIndex(idx)
        dlg.name_edit.setText("Odd Count")
        dlg.count_spin.setValue(3)
        dlg._on_save()
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_valid_save_returns_typed_result(self, dlg):
        dlg.name_edit.setText("Tank Row")
        dlg.start_spin.setValue(100)
        dlg.count_spin.setValue(10)
        dlg.scale_spin.setValue(0.1)
        dlg.unit_edit.setText("bar")
        dlg.group_edit.setText("Tanks")
        dlg._on_save()
        assert dlg.result() == QDialog.DialogCode.Accepted
        r = dlg.get_result()
        assert r["name"] == "Tank Row"
        assert r["start_address"] == 100 and isinstance(r["start_address"], int)
        assert r["count"] == 10
        assert r["scale_factor"] == pytest.approx(0.1)
        assert r["register_type"] == "HOLDING"
        assert r["access"] == "READ_WRITE"
        assert r["is_active"] is True

    def test_discrete_save_coerces_type_and_access(self, dlg):
        self._select(dlg, "DISCRETE")
        dlg.name_edit.setText("Inputs")
        dlg._on_save()
        assert dlg.result() == QDialog.DialogCode.Accepted
        r = dlg.get_result()
        assert r["data_type"] == "BOOL"
        assert r["access"] == "READ_ONLY"

    def test_edit_prefills_existing_block(self, qtbot):
        data = dict(DEFAULT_RESULT, name="Existing", start_address=300,
                    count=20, group_name="G1", access="READ_ONLY")
        d = BlockDialog(None, block_data=data, is_edit=True)
        qtbot.addWidget(d)
        assert d.name_edit.text() == "Existing"
        assert d.start_spin.value() == 300
        assert d.count_spin.value() == 20
        assert d.group_edit.text() == "G1"
        assert d.access_combo.currentData() == "READ_ONLY"


# ---------------------------------------------------------------------------
# ConfigPage — tab structure and refresh dispatch
# ---------------------------------------------------------------------------

class TestBlockTabStructure:

    def test_tab_registered_at_index_4(self, page):
        cfg, _ = page
        assert cfg.tabs.count() == 8
        assert "Register Blocks" in cfg.tabs.tabText(4)
        assert "bulk" in cfg.tabs.tabToolTip(4).lower()

    def test_refresh_dispatch_reaches_block_table(self, page):
        cfg, s = page
        s.block_repo.create_block("A", "HOLDING", 0, 4)
        cfg._refresh_tab_data(4)
        assert cfg.block_table.rowCount() == 1

    def test_later_tabs_still_dispatch(self, page):
        cfg, _ = page
        cfg._refresh_tab_data(3)   # I/O
        cfg._refresh_tab_data(5)   # Control
        cfg._refresh_tab_data(6)   # Message
        # no exception = pass


# ---------------------------------------------------------------------------
# ConfigPage — table refresh and filtering
# ---------------------------------------------------------------------------

class TestBlockTableRefresh:

    def test_lists_all_blocks_including_inactive(self, page):
        cfg, s = page
        s.block_repo.create_block("Alpha", "HOLDING", 0, 10, group_name="G1")
        s.block_repo.create_block("Beta", "COIL", 0, 100,
                                  access="READ_WRITE", group_name="G2")
        s.block_repo.create_block("Gamma", "HOLDING", 50, 5, is_active=False)

        cfg._refresh_block_table()
        assert cfg.block_table.rowCount() == 3

        names = {cfg.block_table.item(r, 1).text() for r in range(3)}
        assert names == {"Alpha", "Beta", "Gamma"}

    def test_row_carries_id_and_range(self, page):
        cfg, s = page
        from PyQt6.QtCore import Qt
        bid = s.block_repo.create_block("Range", "HOLDING", 100, 51)
        cfg._refresh_block_table()
        assert cfg.block_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == bid
        assert cfg.block_table.item(0, 5).text() == "100..150"

    def test_filter_by_name(self, page):
        cfg, s = page
        s.block_repo.create_block("Pressure", "HOLDING", 0, 4)
        s.block_repo.create_block("Temperature", "HOLDING", 10, 4)
        cfg.block_filter.setText("press")
        cfg._refresh_block_table()
        assert cfg.block_table.rowCount() == 1
        assert cfg.block_table.item(0, 1).text() == "Pressure"

    def test_filter_by_group(self, page):
        cfg, s = page
        s.block_repo.create_block("One", "HOLDING", 0, 4, group_name="LineA")
        s.block_repo.create_block("Two", "HOLDING", 10, 4, group_name="LineB")
        cfg.block_filter.setText("lineb")
        cfg._refresh_block_table()
        assert cfg.block_table.rowCount() == 1
        assert cfg.block_table.item(0, 1).text() == "Two"

    def test_empty_repo_gives_empty_table(self, page):
        cfg, _ = page
        cfg._refresh_block_table()
        assert cfg.block_table.rowCount() == 0


# ---------------------------------------------------------------------------
# ConfigPage — add / edit / delete flows
# ---------------------------------------------------------------------------

class TestBlockCrud:

    def test_add_block_creates_row_and_pushes_poller(self, page, monkeypatch):
        cfg, s = page
        monkeypatch.setattr(config_page_mod, "BlockDialog",
                            make_fake_dialog({"name": "Added", "count": 20}))

        cfg._on_block_add()

        row = s.block_repo.get_block_by_name("Added")
        assert row is not None
        assert row["count"] == 20
        assert cfg.block_table.rowCount() == 1
        s.connection_manager.update_block_list.assert_called()

    def test_add_duplicate_shows_error_and_creates_nothing(self, page, monkeypatch):
        cfg, s = page
        s.block_repo.create_block("Dupe", "HOLDING", 0, 4)
        cfg._refresh_block_table()
        errors: list[str] = []
        monkeypatch.setattr(config_page_mod.QMessageBox, "critical",
                            lambda *a, **k: errors.append(str(a[2]) if len(a) > 2 else ""))
        monkeypatch.setattr(config_page_mod, "BlockDialog",
                            make_fake_dialog({"name": "Dupe"}))

        cfg._on_block_add()

        assert errors and "already exists" in errors[0]
        assert s.block_repo.get_block_by_name("Dupe") is not None
        assert cfg.block_table.rowCount() == 1  # only the original

    def test_edit_updates_selected_block(self, page, monkeypatch):
        cfg, s = page
        bid = s.block_repo.create_block("Old Name", "HOLDING", 0, 4)
        cfg._refresh_block_table()
        cfg.block_table.selectRow(0)

        monkeypatch.setattr(config_page_mod, "BlockDialog",
                            make_fake_dialog({"name": "New Name", "count": 8}))
        cfg._on_block_edit()

        updated = s.block_repo.get_block(bid)
        assert updated["name"] == "New Name"
        assert updated["count"] == 8
        assert cfg.block_table.item(0, 1).text() == "New Name"

    def test_delete_confirmed_removes_block(self, page, monkeypatch):
        cfg, s = page
        s.block_repo.create_block("Doomed", "HOLDING", 0, 4)
        cfg._refresh_block_table()
        cfg.block_table.selectRow(0)

        monkeypatch.setattr(config_page_mod.ConfirmDialog, "ask",
                            lambda *a, **k: True)
        cfg._on_block_delete()

        assert s.block_repo.get_block_by_name("Doomed") is None
        assert cfg.block_table.rowCount() == 0
        s.connection_manager.update_block_list.assert_called()

    def test_delete_declined_keeps_block(self, page, monkeypatch):
        cfg, s = page
        s.block_repo.create_block("Kept", "HOLDING", 0, 4)
        cfg._refresh_block_table()
        cfg.block_table.selectRow(0)

        monkeypatch.setattr(config_page_mod.ConfirmDialog, "ask",
                            lambda *a, **k: False)
        cfg._on_block_delete()

        assert s.block_repo.get_block_by_name("Kept") is not None
        assert cfg.block_table.rowCount() == 1

    def test_selection_toggles_buttons(self, page):
        cfg, _ = page
        cfg.block_table.clearSelection()
        cfg._on_block_selection_changed()
        assert not cfg.block_edit_btn.isEnabled()
        assert not cfg.block_rem_btn.isEnabled()

    def test_refresh_poll_config_pushes_block_list(self, page):
        cfg, s = page
        s.block_repo.create_block("Pushed", "HOLDING", 0, 4)
        s.connection_manager.reset_mock()
        s.refresh_poll_config()
        s.connection_manager.update_block_list.assert_called_once()
        pushed = s.connection_manager.update_block_list.call_args[0][0]
        assert any(b["name"] == "Pushed" for b in pushed)
