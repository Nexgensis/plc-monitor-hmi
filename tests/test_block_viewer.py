"""
Phase 6 — IO List page block viewer merge + bulk write dialog.

Covers:
    - _build_tabs: empty state, IO-only (zero regression), blocks-only,
      mixed order, inactive exclusion, tooltips, poll_info text
    - _refresh_data / _refresh_block_view: dashes, word values, FLOAT32
      stride, bit ON/OFF labels + colors, stale marking, disconnected
    - Write button gating (READ_ONLY / ADMIN / SUPERVISOR / OPERATOR)
    - BlockWriteDialog validation, dispatch, success/failure/busy handling
    - Page-level dispatch and permission warnings

Run: venv\\Scripts\\python.exe -m pytest tests/test_block_viewer.py -q
"""
from __future__ import annotations

import struct
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QMessageBox

from src.db.database import Database
from src.db.block_repo import BlockRepo
from src.db.io_list_repo import IOListRepo
from src.db.register_library_repo import RegisterLibraryRepo
from src.plc.data_model import PLCDataModel, BlockReading, RegisterReading
from src.ui.app_state import AppState
from src.ui.pages.io_list_page import IoListPage
from src.ui.dialogs.block_write_dialog import BlockWriteDialog

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

_STATE_FIELDS = (
    "current_user", "current_model_id", "db", "connection_manager",
    "write_manager", "data_model", "block_repo", "io_repo", "library_repo",
    "is_plc_connected", "message_register", "message_lookup", "poll_blocks",
)


class FakeWriteManager(QObject):
    block_write_success = pyqtSignal(int, str, int)
    block_write_failed = pyqtSignal(int, str, str)
    plc_busy = pyqtSignal(str)
    verify_failed = pyqtSignal(int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []
        self.return_value = True

    def execute_block_write(self, block, values, operator_id) -> bool:
        self.calls.append((block, values, operator_id))
        return self.return_value


def make_reading(block_id=1, count=4, raw=None, elements=None,
                 stale=False, error=""):
    return BlockReading(
        block_id=block_id, name="B", start_address=0,
        register_type="HOLDING", count=count,
        raw_words=list(raw or []),
        elements=list(elements or []),
        read_success=not stale, error=error, stale=stale,
        timestamp=datetime.now(timezone.utc),
    )


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
        pass


@pytest.fixture
def env(qtbot, tmp_path):
    """IoListPage + AppState wired to a fresh DB and a real data model."""
    db = Database(str(tmp_path / "viewer.db"))
    db.initialize()

    s = AppState.get_instance()
    saved = {n: getattr(s, n) for n in _STATE_FIELDS if hasattr(s, n)}

    data_model = PLCDataModel()
    conn = MagicMock(data_model=data_model)

    s.current_user = {"id": 7, "username": "admin", "role": "ADMIN"}
    s.current_model_id = None
    s.db = db
    s.block_repo = BlockRepo(db)
    s.io_repo = IOListRepo(db)
    s.library_repo = RegisterLibraryRepo(db)
    s.connection_manager = conn
    s.write_manager = FakeWriteManager()
    s.data_model = data_model
    s.is_plc_connected = True

    page = IoListPage(s)
    qtbot.addWidget(page)
    try:
        yield page, s, data_model
    finally:
        _teardown_widget(page)
        for name, value in saved.items():
            setattr(s, name, value)
        db.close_all()


def add_block(page_state, name="Blk", **kwargs):
    defaults = dict(register_type="HOLDING", start_address=0, count=4,
                    access="READ_WRITE")
    defaults.update(kwargs)
    return page_state.block_repo.create_block(name, **defaults)


def add_io_entry(page_state, display="IO Point", group="Line 1"):
    reg_id = page_state.library_repo.create_register(
        f"{display} reg", 10, "HOLDING", "UINT16", access="READ_WRITE"
    )
    return page_state.io_repo.create_io_row(
        display_name=display, register_id=reg_id, group_name=group
    )


def write_button(container) -> QPushButton | None:
    for btn in container.findChildren(QPushButton):
        if btn.accessibleName().startswith("Write block "):
            return btn
    return None


# ---------------------------------------------------------------------------
# Tab building
# ---------------------------------------------------------------------------

class TestBuildTabs:

    def test_empty_state_shows_no_config_card(self, env):
        page, _, _ = env
        page._build_tabs()
        assert page.no_io_card.isVisible() or not page.no_io_card.isHidden()
        assert page.tabs.isHidden() or page.tabs.count() == 0
        assert page.tabs.count() == 0

    def test_io_only_tabs_unchanged(self, env):
        page, s, _ = env
        add_io_entry(s, "DI 1", "Sensors")
        add_io_entry(s, "DI 2", "Sensors")
        add_io_entry(s, "DO 1", "Actuators")

        page._build_tabs()

        assert page.tabs.count() == 2
        assert {page.tabs.tabText(0), page.tabs.tabText(1)} == {"Sensors", "Actuators"}
        from src.utils.constants import IO_LIST_REFRESH_MS
        assert page.poll_info.text() == (
            f"Monitoring 3 I/O points | Poll: {IO_LIST_REFRESH_MS}ms"
        )
        assert page._block_view == {}
        assert page.no_io_card.isHidden()

    def test_blocks_only_tab_built(self, env):
        page, s, _ = env
        add_block(s, "Range A", start_address=0, count=10)

        page._build_tabs()

        assert page.tabs.count() == 1
        assert page.tabs.tabText(0) == "Range A"
        assert page.no_io_card.isHidden()
        assert "1 blocks" in page.poll_info.text()

    def test_mixed_io_and_block_tabs_order(self, env):
        page, s, _ = env
        add_io_entry(s, "Point", "GroupX")
        add_block(s, "Range B")

        page._build_tabs()

        assert page.tabs.count() == 2
        assert page.tabs.tabText(0) == "GroupX"       # I/O tabs first
        assert page.tabs.tabText(1) == "Range B"      # block tabs appended

    def test_inactive_block_excluded(self, env):
        page, s, _ = env
        add_block(s, "Live")
        add_block(s, "Disabled", is_active=False)

        page._build_tabs()
        assert page.tabs.count() == 1
        assert page.tabs.tabText(0) == "Live"

    def test_block_tab_tooltip_has_range_and_group(self, env):
        page, s, _ = env
        add_block(s, "Tip", start_address=100, count=51, group_name="Tanks")
        page._build_tabs()
        tip = page.tabs.tabToolTip(0)
        assert "HOLDING 100..150" in tip
        assert "Tanks" in tip


# ---------------------------------------------------------------------------
# Block view refresh
# ---------------------------------------------------------------------------

class TestBlockViewRefresh:

    def _container_for(self, page, name):
        for container, (block, _table) in page._block_view.items():
            if block["name"] == name:
                return container
        raise AssertionError(f"no viewer for {name}")

    def test_dashes_without_reading(self, env):
        page, s, dm = env
        add_block(s, "NoData")
        page._build_tabs()
        page._refresh_data()
        _, table = page._block_view[self._container_for(page, "NoData")]
        assert table.item(0, 2).text() == "---"
        assert table.item(0, 3).text() == "---"

    def test_word_block_values_formatted(self, env):
        page, s, dm = env
        bid = add_block(s, "Pressures", count=4, scale_factor=0.1,
                        decimal_places=1, unit="bar")
        dm.update_block_reading(bid, make_reading(
            block_id=bid, count=4,
            raw=[100, 200, 300, 400],
            elements=[10.0, 20.0, 30.0, 40.0],
        ))
        page._build_tabs()
        page._refresh_data()

        _, table = page._block_view[self._container_for(page, "Pressures")]
        assert table.rowCount() == 4
        assert table.item(0, 1).text() == "0"      # address
        assert table.item(0, 2).text() == "100"    # raw
        assert table.item(0, 3).text() == "10.0 bar"
        assert table.item(3, 1).text() == "3"
        assert table.item(3, 2).text() == "400"
        assert table.item(3, 3).text() == "40.0 bar"

    def test_float32_uses_stride_two(self, env):
        page, s, dm = env
        hi, lo = struct.unpack(">HH", struct.pack(">f", 3.5))
        bid = add_block(s, "Floats", count=4, data_type="FLOAT32",
                        decimal_places=2, unit="")
        dm.update_block_reading(bid, make_reading(
            block_id=bid, count=4,
            raw=[hi, lo, hi, lo],
            elements=[3.5, 3.5],
        ))
        page._build_tabs()
        page._refresh_data()

        _, table = page._block_view[self._container_for(page, "Floats")]
        assert table.rowCount() == 2
        assert table.item(0, 1).text() == "0"
        assert table.item(1, 1).text() == "2"
        assert table.item(0, 2).text() == f"{hi},{lo}"
        assert table.item(0, 3).text() == "3.50"

    def test_bit_block_labels_and_colors(self, env):
        page, s, dm = env
        bid = add_block(s, "Valves", register_type="COIL", count=4,
                        access="READ_WRITE", on_label="Open", off_label="Shut",
                        on_color="#ff0000", off_color="#0000ff")
        dm.update_block_reading(bid, make_reading(
            block_id=bid, count=4, raw=[1, 0, 1, 0], elements=[1, 0, 1, 0],
        ))
        page._build_tabs()
        page._refresh_data()

        _, table = page._block_view[self._block_key(page, "Valves")]
        assert table.item(0, 3).text() == "Open"
        assert table.item(1, 3).text() == "Shut"
        assert table.item(0, 3).foreground().color().name() == "#ff0000"
        assert table.item(1, 3).foreground().color().name() == "#0000ff"
        assert table.item(2, 2).text() == "1"

    def _block_key(self, page, name):
        for container, (block, _t) in page._block_view.items():
            if block["name"] == name:
                return container
        raise AssertionError(name)

    def test_stale_marks_tooltip_and_header(self, env):
        page, s, dm = env
        bid = add_block(s, "StaleOne", count=4)
        dm.update_block_reading(bid, make_reading(
            block_id=bid, count=4, raw=[1, 2, 3, 4], elements=[1, 2, 3, 4],
            stale=True, error="timeout",
        ))
        page._build_tabs()
        page._refresh_data()

        container = self._block_key(page, "StaleOne")
        assert "LAST READ FAILED" in container.toolTip()
        assert "(STALE)" in page.last_refresh_lbl.text()
        # values still shown from last good poll
        _, table = page._block_view[container]
        assert table.item(0, 2).text() == "1"

    def test_disconnected_shows_disconnected(self, env):
        page, s, dm = env
        add_block(s, "Any")
        page._build_tabs()
        s.is_plc_connected = False
        page._refresh_data()
        assert page.last_refresh_lbl.text() == "PLC Disconnected"

    def test_io_group_rows_still_refresh(self, env):
        """Zero-regression: the original IO value path keeps working."""
        page, s, dm = env
        add_io_entry(s, "MyPoint", "G")
        page._build_tabs()

        reg_id = s.io_repo.get_all_entries()[0]["register_id"]
        dm.update_reading(reg_id, RegisterReading(
            register_id=reg_id, name="MyPoint", plc_address=10,
            register_type="HOLDING", raw_words=[1234],
            display_value=1234.0, display_str="1234.00 ",
            unit="", data_type="UINT16",
            timestamp=datetime.now(timezone.utc), read_success=True,
        ))
        page._refresh_data()
        table = page.tabs.currentWidget()
        assert table.item(0, 5).text().strip() == "1234.00"


# ---------------------------------------------------------------------------
# Write gating
# ---------------------------------------------------------------------------

class TestWriteGating:

    def test_read_only_block_has_no_write_button(self, env):
        page, s, _ = env
        add_block(s, "ReadOnly", access="READ_ONLY")
        page._build_tabs()
        container = next(iter(page._block_view))
        assert write_button(container) is None

    def test_admin_gets_enabled_button(self, env):
        page, s, _ = env
        s.current_user = {"id": 1, "role": "ADMIN"}
        add_block(s, "Writable")
        page._build_tabs()
        btn = write_button(next(iter(page._block_view)))
        assert btn is not None and btn.isEnabled()

    def test_supervisor_gets_enabled_button(self, env):
        page, s, _ = env
        s.current_user = {"id": 2, "role": "SUPERVISOR"}
        add_block(s, "Writable")
        page._build_tabs()
        btn = write_button(next(iter(page._block_view)))
        assert btn is not None and btn.isEnabled()

    def test_operator_gets_disabled_button(self, env):
        page, s, _ = env
        s.current_user = {"id": 3, "role": "OPERATOR"}
        add_block(s, "Writable")
        page._build_tabs()
        btn = write_button(next(iter(page._block_view)))
        assert btn is not None and not btn.isEnabled()
        assert "ADMIN" in btn.toolTip()


# ---------------------------------------------------------------------------
# Page dispatch helpers
# ---------------------------------------------------------------------------

class TestPageDispatch:

    def test_dispatch_calls_manager_with_operator_id(self, env):
        page, s, _ = env
        block = {"id": 5, "name": "B", "count": 3}
        ok = page._dispatch_block_write(block, [1, 2, 3])
        assert ok is True
        mgr = s.write_manager
        assert mgr.calls == [(block, [1, 2, 3], 7)]

    def test_dispatch_without_user_returns_false(self, env):
        page, s, _ = env
        s.current_user = None
        assert page._dispatch_block_write({"id": 1, "count": 1}, [0]) is False
        assert s.write_manager.calls == []

    def test_write_block_without_permission_warns(self, env, monkeypatch):
        page, s, _ = env
        s.current_user = {"id": 3, "role": "OPERATOR"}
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **k: warnings.append(str(a[2]) if len(a) > 2 else ""))
        page._on_write_block({"id": 1, "count": 1})
        assert warnings and "ADMIN" in warnings[0]

    def test_write_block_without_manager_warns(self, env, monkeypatch):
        page, s, _ = env
        s.write_manager = None
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **k: warnings.append(str(a[2]) if len(a) > 2 else ""))
        page._on_write_block({"id": 1, "count": 1})
        assert warnings and "Connect" in warnings[0]


# ---------------------------------------------------------------------------
# BlockWriteDialog
# ---------------------------------------------------------------------------

BLOCK = {
    "id": 9, "name": "WriteMe", "register_type": "HOLDING",
    "start_address": 100, "count": 4, "access": "READ_WRITE",
}


def make_dialog(qtbot, block=None, values=None, dispatch=None):
    mgr = FakeWriteManager()
    calls = []

    def default_dispatch(b, v):
        calls.append(list(v))
        return True

    dlg = BlockWriteDialog(
        None,
        block=block or dict(BLOCK),
        values=values,
        dispatch=dispatch or default_dispatch,
        write_manager=mgr,
    )
    qtbot.addWidget(dlg)
    return dlg, mgr, calls


class TestBlockWriteDialog:

    def test_prefills_initial_values(self, qtbot):
        dlg, _, _ = make_dialog(qtbot, values=[7, 8, 9, 10])
        assert [dlg.table.item(r, 2).text() for r in range(4)] == \
            ["7", "8", "9", "10"]
        assert dlg.table.item(0, 1).text() == "100"   # address column

    def test_write_dispatches_parsed_values(self, qtbot):
        dlg, mgr, calls = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        assert calls == [[1, 2, 3, 4]]
        # success completes the dialog
        mgr.block_write_success.emit(9, "WriteMe", 4)
        assert dlg.result() == dlg.DialogCode.Accepted

    def test_non_integer_value_rejected(self, qtbot):
        dlg, mgr, calls = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg.table.item(2, 2).setText("abc")
        dlg._on_write()
        assert calls == []
        assert "not a whole number" in dlg.status_lbl.text()
        assert dlg.status_lbl.isVisibleTo(dlg)
        assert dlg.write_btn.isEnabled()

    def test_word_out_of_range_rejected(self, qtbot):
        dlg, _, calls = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg.table.item(0, 2).setText("65536")
        dlg._on_write()
        assert calls == []
        assert "out of range" in dlg.status_lbl.text()

    def test_coil_rejects_non_binary(self, qtbot):
        block = dict(BLOCK, register_type="COIL", start_address=0)
        dlg, _, calls = make_dialog(qtbot, block=block, values=[0, 1, 0, 1])
        dlg.table.item(1, 2).setText("2")
        dlg._on_write()
        assert calls == []
        assert "0 or 1" in dlg.status_lbl.text()

    def test_failure_keeps_dialog_open_and_reenables(self, qtbot):
        dlg, mgr, calls = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        assert not dlg.write_btn.isEnabled()

        mgr.block_write_failed.emit(9, "WriteMe", "PLC rejected")
        assert dlg.result() != dlg.DialogCode.Accepted
        assert dlg.write_btn.isEnabled()
        assert "PLC rejected" in dlg.status_lbl.text()

        # retry works
        dlg.table.item(0, 2).setText("5")
        dlg._on_write()
        assert calls == [[1, 2, 3, 4], [5, 2, 3, 4]]

    def test_busy_reenables(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.plc_busy.emit("A write operation is already in progress.")
        assert dlg.write_btn.isEnabled()
        assert "already in progress" in dlg.status_lbl.text()

    def test_foreign_block_signal_ignored(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.block_write_success.emit(999, "Other", 1)
        assert dlg.result() != dlg.DialogCode.Accepted
        assert not dlg.write_btn.isEnabled()  # still waiting for ours

    def test_dispatch_exception_releases_ui(self, qtbot):
        def boom(b, v):
            raise RuntimeError("kaput")

        dlg, _, _ = make_dialog(qtbot, values=[1, 2, 3, 4], dispatch=boom)
        dlg._on_write()
        assert dlg.write_btn.isEnabled()
        assert "kaput" in dlg.status_lbl.text()

    def test_signals_disconnected_after_accept(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.block_write_success.emit(9, "WriteMe", 4)
        assert dlg.result() == dlg.DialogCode.Accepted
        # late signals must not crash / re-trigger
        mgr.block_write_success.emit(9, "WriteMe", 4)
        mgr.block_write_failed.emit(9, "WriteMe", "late")
        assert dlg.result() == dlg.DialogCode.Accepted


# ---------------------------------------------------------------------------
# R4 — write dialog UX polish
# ---------------------------------------------------------------------------

class TestBlockWriteDialogPolish:

    def test_enter_cannot_trigger_write(self, qtbot):
        dlg, _, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        assert not dlg.write_btn.isDefault()
        assert not dlg.write_btn.autoDefault()
        for btn in dlg.findChildren(QPushButton):
            if btn.text() == "Cancel":
                assert not btn.autoDefault()
                break
        else:
            raise AssertionError("Cancel button not found")

    def test_table_locked_while_writing_and_released_on_failure(self, qtbot):
        from PyQt6.QtWidgets import QAbstractItemView
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        assert dlg.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers

        mgr.block_write_failed.emit(9, "WriteMe", "PLC rejected")
        assert dlg.table.editTriggers() == dlg._EDIT_TRIGGERS

    def test_verify_mismatch_marks_row_and_status(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.verify_failed.emit(101, 5, 7)          # addr 101 = row 1

        cell = dlg.table.item(1, 2)
        assert cell.foreground().color().name() == "#ef4444"
        assert "Wrote 5, read back 7" in cell.toolTip()
        assert "101" in dlg.status_lbl.text()
        assert "read back 7" in dlg.status_lbl.text()
        assert not dlg.write_btn.isEnabled()       # write still in flight

        # other rows untouched
        assert dlg.table.item(0, 2).foreground().color().name() != "#ef4444"

    def test_verify_mismatch_outside_block_ignored(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.verify_failed.emit(999, 1, 2)          # different write's address
        assert "mismatch" not in dlg.status_lbl.text()
        assert dlg.status_lbl.text().startswith("Writing")

    def test_retry_clears_previous_highlights(self, qtbot):
        dlg, mgr, _ = make_dialog(qtbot, values=[1, 2, 3, 4])
        dlg._on_write()
        mgr.verify_failed.emit(100, 1, 9)
        mgr.block_write_failed.emit(9, "WriteMe", "verify failed")
        assert dlg.table.item(0, 2).foreground().color().name() == "#ef4444"

        dlg._on_write()                           # retry
        assert dlg.table.item(0, 2).toolTip() == ""
        assert dlg.table.item(0, 2).foreground().color().name() != "#ef4444"
