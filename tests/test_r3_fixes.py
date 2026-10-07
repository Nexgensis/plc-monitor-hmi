"""
R3 — functional bug-fix regression tests.

Covers:
    - Model page: selected card stays checked (selection is visible)
    - Login overlay: empty password shows a distinct message (not "Invalid")
    - F2: model mappings exported by name and re-imported onto new model ids
    - F4: message-tab source combo picks up registers added in other tabs
    - F5: imported library rows stamp the acting user, not always id 1
    - F6: write-log list live-refreshes on write_log_updated (tab visible)
    - F8: label-clear timer tolerates firing after widget destruction
    - F1: AppState.refresh_poll_config exists (spurious import error gone)

Run: venv\\Scripts\\python.exe -m pytest tests/test_r3_fixes.py -q
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel

from src.db.database import Database
from src.db.block_repo import BlockRepo
from src.ui.app_state import AppState
from src.ui.pages import config_page as config_page_mod
from src.ui.pages.config_page import ConfigPage

_STATE_FIELDS = (
    "current_user", "current_model_id", "db", "connection_manager",
    "write_manager", "data_model", "config_repo", "profile_repo",
    "library_repo", "user_repo", "model_repo", "map_repo", "control_repo",
    "io_repo", "msg_repo", "session_repo", "report_repo", "block_repo",
    "plc_profile", "is_plc_configured", "is_plc_connected",
    "message_register", "message_lookup", "poll_blocks", "poll_registers",
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
    """Fresh DB wired into the AppState singleton (no ConfigPage yet)."""
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

    db = Database(str(tmp_path / "r3.db"))
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
    s.is_plc_connected = False
    s.message_register = None
    s.message_lookup = {}

    try:
        yield s, db
    finally:
        for name, value in saved.items():
            setattr(s, name, value)
        db.close_all()


@pytest.fixture
def page(env, qtbot):
    s, _ = env
    cfg = ConfigPage(s, on_plc_reconnect=lambda: None)
    qtbot.addWidget(cfg)
    try:
        yield cfg
    finally:
        _teardown_widget(cfg)


@pytest.fixture
def dialogs(monkeypatch):
    """Neutralize file dialogs / message boxes; capture what _on_import says."""
    captured = {"info": [], "critical": [], "open": None, "save": None,
                "confirm": True, "import_args": None, "export_args": None}

    class _FileDialog:
        @staticmethod
        def getOpenFileName(*args, **kwargs):
            return captured["open"] or ("", "")

        @staticmethod
        def getSaveFileName(*args, **kwargs):
            return captured["save"] or ("", "")

    class _MessageBox:
        @staticmethod
        def information(*args):
            captured["info"].append(args[-1])

        @staticmethod
        def critical(*args):
            captured["critical"].append(args[-1])

    class _Confirm:
        @staticmethod
        def ask(*args, **kwargs):
            return captured["confirm"]

    monkeypatch.setattr(config_page_mod, "QFileDialog", _FileDialog)
    monkeypatch.setattr(config_page_mod, "QMessageBox", _MessageBox)
    monkeypatch.setattr(config_page_mod, "ConfirmDialog", _Confirm)
    return captured


def _insert_audit_row(db, address: int = 100, name: str = "D100") -> None:
    db.execute(
        "INSERT INTO plc_write_log (register_address, register_name,"
        " value_written, write_success, write_reason)"
        " VALUES (?, ?, '5', 1, 'Manual click')",
        (address, name),
    )


# ---------------------------------------------------------------------------
# Model page — visible selection
# ---------------------------------------------------------------------------

class TestModelCardSelection:
    def test_selected_card_stays_checked(self, env, qtbot):
        from src.ui.pages.model_page import ModelPage

        s, _ = env
        mid1 = s.model_repo.create_model(name="M-A", model_number="A-1")
        mid2 = s.model_repo.create_model(name="M-B", model_number="B-1")

        mp = ModelPage(s, on_model_confirmed=lambda *_: None)
        qtbot.addWidget(mp)
        try:
            mp._refresh_models()
            assert mp.grid.count() == 2

            mp._on_model_selected(mid2)
            cards = {mp.grid.itemAt(i).widget().property("model_id"):
                     mp.grid.itemAt(i).widget() for i in range(mp.grid.count())}
            assert cards[mid2].isChecked()
            assert not cards[mid1].isChecked()
            assert mp.btn_start.isEnabled()

            mp._on_model_selected(mid1)
            assert cards[mid1].isChecked()
            assert not cards[mid2].isChecked()
        finally:
            _teardown_widget(mp)


# ---------------------------------------------------------------------------
# Login overlay — empty password message
# ---------------------------------------------------------------------------

class TestEmptyPassword:
    def test_empty_password_message_distinct_from_invalid(self, env):
        s, _ = env
        from src.ui.login_overlay import LoginOverlay

        ov = LoginOverlay(s, on_success=None)
        try:
            ov.password_input.setText("")
            ov._on_login()
            assert not ov.error_lbl.isHidden()
            assert "enter your password" in ov.error_lbl.text().lower()

            ov.password_input.setText("wrong")
            ov._on_login()
            assert "Invalid" in ov.error_lbl.text()
        finally:
            anim = getattr(ov, "animation", None)
            if anim is not None:
                anim.stop()
            _teardown_widget(ov)


# ---------------------------------------------------------------------------
# F4 — message tab combo refresh
# ---------------------------------------------------------------------------

class TestMessageComboRefresh:
    def test_combo_picks_up_new_registers(self, page, env):
        s, _ = env
        page.tabs.setCurrentIndex(6)  # message tab refresh
        rid = s.library_repo.create_register(
            name="MSG_SRC", register_address=999,
            register_type="HOLDING", data_type="INT16",
        )
        page._refresh_message_tab()
        texts = [page.msg_reg_combo.itemText(i)
                 for i in range(page.msg_reg_combo.count())]
        assert any("MSG_SRC" in t for t in texts)
        assert page.msg_reg_combo.findData(rid) >= 0


# ---------------------------------------------------------------------------
# F6 — live write-log refresh
# ---------------------------------------------------------------------------

class _StubWriter(QObject):
    write_log_updated = pyqtSignal()


class TestWriteLogLiveRefresh:
    def test_refreshes_only_when_control_tab_visible(self, page, env, monkeypatch):
        s, _ = env
        stub = _StubWriter()
        monkeypatch.setattr(s, "write_manager", stub, raising=False)

        page.on_page_shown()                      # ensures connection
        page.tabs.setCurrentIndex(5)              # control tab
        assert page.ctrl_log_list.count() == 0

        _insert_audit_row(s.db, 100, "D100")
        assert page.ctrl_log_list.count() == 0    # signal not yet emitted
        stub.write_log_updated.emit()
        assert page.ctrl_log_list.count() == 1
        assert "Addr:100" in page.ctrl_log_list.item(0).text()

        # Not on the control tab → no rebuild
        page.tabs.setCurrentIndex(4)              # blocks tab
        _insert_audit_row(s.db, 200, "D200")
        stub.write_log_updated.emit()
        assert page.ctrl_log_list.count() == 1

        # Back on control tab → refresh shows both rows
        page.tabs.setCurrentIndex(5)
        assert page.ctrl_log_list.count() == 2

    def test_connected_once_per_manager(self, page, env, monkeypatch):
        s, _ = env
        stub = _StubWriter()
        monkeypatch.setattr(s, "write_manager", stub, raising=False)

        page.on_page_shown()
        page.on_page_shown()
        assert page._wm_log_for is stub

        _insert_audit_row(s.db, 7, "D7")
        page.tabs.setCurrentIndex(5)
        page.ctrl_log_list.clear()
        stub.write_log_updated.emit()
        assert page.ctrl_log_list.count() == 1


# ---------------------------------------------------------------------------
# F8 — label-clear timer after destroy
# ---------------------------------------------------------------------------

class TestSafeLabelClear:
    def test_clear_after_delete_tolerated(self):
        lbl = QLabel("temp")
        lbl.deleteLater()
        QCoreApplication.sendPostedEvents(lbl, QEvent.Type.DeferredDelete)
        ConfigPage._safe_clear_label(lbl)          # must not raise

    def test_clear_normal(self):
        lbl = QLabel("temp")
        ConfigPage._safe_clear_label(lbl)
        assert lbl.text() == ""


# ---------------------------------------------------------------------------
# F1 — refresh_poll_config present
# ---------------------------------------------------------------------------

class TestRefreshPollConfig:
    def test_refresh_poll_config_callable(self, env):
        s, _ = env
        assert callable(s.refresh_poll_config)
        s.refresh_poll_config()                    # must not raise


# ---------------------------------------------------------------------------
# F2 / F5 — export/import round trip
# ---------------------------------------------------------------------------

def _register(s, name, address):
    return s.library_repo.create_register(
        name=name, register_address=address,
        register_type="HOLDING", data_type="INT16",
    )


class TestExportImportMappings:
    def _setup_model_with_mapping(self, s):
        rid = _register(s, "REG_A", 10)
        mid = s.model_repo.create_model(name="M1", model_number="MX-1")
        s.map_repo.add_mapping(
            mid, rid, role="RESULT", group_name="Group 1",
            card_position=1, pass_value=5, fail_value=6,
            limit_min=1.5, limit_max=9.5,
        )
        return rid, mid

    def test_export_keys_mappings_by_model_name(self, page, env, dialogs, tmp_path):
        s, _ = env
        self._setup_model_with_mapping(s)
        out = tmp_path / "cfg.json"
        dialogs["save"] = (str(out), "JSON (*.json)")

        page._on_export()
        assert out.exists()
        data = json.loads(out.read_text())
        assert "M1" in data["mappings"]
        rows = data["mappings"]["M1"]
        assert len(rows) == 1
        assert rows[0]["library_name"] == "REG_A"
        assert rows[0]["role"] == "RESULT"

    def test_roundtrip_restores_mappings_after_model_deleted(
        self, page, env, dialogs, tmp_path
    ):
        s, _ = env
        rid, mid = self._setup_model_with_mapping(s)
        out = tmp_path / "cfg.json"
        dialogs["save"] = (str(out), "JSON (*.json)")
        page._on_export()

        # Destroy the model (and its mappings) — import must restore both
        s.model_repo.delete_model(mid)
        assert s.model_repo.get_model(mid) is None
        assert s.model_repo.get_all_models() == []

        dialogs["open"] = (str(out), "JSON (*.json)")
        page._on_import()

        restored = s.model_repo.get_model_by_name("M1")
        assert restored is not None
        rows = s.map_repo.get_model_mappings(restored["id"])
        assert len(rows) == 1
        assert rows[0]["library_name"] == "REG_A"
        assert rows[0]["role"] == "RESULT"
        assert rows[0]["group_name"] == "Group 1"
        assert rows[0]["pass_value"] == 5
        assert rows[0]["fail_value"] == 6
        assert rows[0]["limit_min"] == pytest.approx(1.5)
        assert rows[0]["limit_max"] == pytest.approx(9.5)
        assert any("Mappings" in m for m in dialogs["info"])
        assert dialogs["critical"] == []

    def test_import_skips_unresolvable_model_keys_gracefully(
        self, page, env, dialogs, tmp_path
    ):
        # Old-format export keyed by model id strings must not crash
        s, _ = env
        _register(s, "REG_Z", 42)
        payload = {
            "models": [{"name": "Fresh"}],
            "mappings": {"1": [{"library_name": "REG_Z"}]},
        }
        path = tmp_path / "old.json"
        path.write_text(json.dumps(payload))

        dialogs["open"] = (str(path), "JSON (*.json)")
        page._on_import()
        assert dialogs["critical"] == []
        assert s.model_repo.get_model_by_name("Fresh") is not None
        # Unresolvable key → skipped, model has no mappings
        fresh = s.model_repo.get_model_by_name("Fresh")
        assert s.map_repo.get_model_mappings(fresh["id"]) == []

    def test_import_stamps_acting_user(self, page, env, dialogs, tmp_path):
        s, _ = env
        operator = s.db.fetchone(
            "SELECT id FROM users WHERE UPPER(username) = 'OPERATOR'"
        )
        assert operator is not None
        s.current_user = {"id": operator["id"]}

        payload = {
            "library": [{
                "name": "REG_X", "register_address": 55,
                "register_type": "HOLDING", "data_type": "INT16",
            }],
        }
        path = tmp_path / "lib.json"
        path.write_text(json.dumps(payload))
        dialogs["open"] = (str(path), "JSON (*.json)")

        page._on_import()
        reg = s.library_repo.get_register_by_name("REG_X")
        assert reg is not None
        assert reg["created_by"] == operator["id"]


# ---------------------------------------------------------------------------
# F3 — atomic import (all sections or nothing)
# ---------------------------------------------------------------------------

class TestAtomicImport:
    def test_mid_import_failure_rolls_back_everything(
        self, page, env, dialogs, tmp_path
    ):
        s, _ = env
        payload = {
            # Library section imports first and succeeds...
            "library": [{
                "name": "REG_ROLLBACK", "register_address": 88,
                "register_type": "HOLDING", "data_type": "INT16",
            }],
            # ...then a malformed model section aborts the import (KeyError).
            "models": [{"description": "missing name key"}],
        }
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload))
        dialogs["open"] = (str(path), "JSON (*.json)")

        page._on_import()

        assert dialogs["critical"], "error dialog expected"
        assert "Failed to import" in dialogs["critical"][0]
        # Nothing from the failed import survives
        assert s.library_repo.get_register_by_name("REG_ROLLBACK") is None
        assert s.model_repo.get_all_models() == []
        # Existing data untouched
        assert s.library_repo.get_all_registers() == []

    def test_transaction_commits_on_success(self, env):
        s, db = env
        with db.transaction():
            db.execute(
                "INSERT INTO register_library (name, register_address,"
                " register_type, data_type) VALUES ('TX_OK', 5, 'HOLDING', 'INT16')"
            )
        row = db.fetchone("SELECT * FROM register_library WHERE name = 'TX_OK'")
        assert row is not None

    def test_transaction_rolls_back_on_exception(self, env):
        s, db = env
        with pytest.raises(RuntimeError, match="boom"):
            with db.transaction():
                db.execute(
                    "INSERT INTO register_library (name, register_address,"
                    " register_type, data_type) VALUES ('TX_BAD', 6, 'HOLDING', 'INT16')"
                )
                raise RuntimeError("boom")
        assert db.fetchone(
            "SELECT * FROM register_library WHERE name = 'TX_BAD'"
        ) is None

    def test_execute_commits_outside_transaction(self, env):
        s, db = env
        db.execute(
            "INSERT INTO register_library (name, register_address,"
            " register_type, data_type) VALUES ('TX_SOLO', 7, 'HOLDING', 'INT16')"
        )
        assert db.fetchone(
            "SELECT * FROM register_library WHERE name = 'TX_SOLO'"
        ) is not None
