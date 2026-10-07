"""
Regression tests for the critical bug fixes:

1. RESULT_PENDING import in SessionController (PENDING/BYPASS cycles were
   force-closed as FAIL via NameError swallowed by the broad except).
2. SettingsPage theme / high-contrast crash (ThemeManager.instance() does
   not exist on the static ThemeManager).
3. ReportsPage export_bar / export_status widgets were never constructed
   (every Excel/PDF export raised AttributeError).
4. navigate_to access gate: runs before on_page_hidden side effects and
   enforces NAV_ITEMS roles for every page (Ctrl+7 role bypass).
5. user_repo.delete_user guard against ON DELETE CASCADE wiping registers.
6. PLCDriverFactory create(cached=False) for throwaway drivers.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer

from src.db.database import Database
from src.db.user_repo import UserRepository
from src.db.register_library_repo import RegisterLibraryRepo
from src.logic.pass_fail_evaluator import EvalResult
from src.logic.session_controller import SessionController
from src.plc.driver_factory import PLCDriverFactory
from src.ui.app_state import AppState
from src.ui.main_window import MainWindow
from src.ui.pages.reports_page import ReportsPage
from src.ui.pages.settings_page import SettingsPage
from src.utils.constants import (
    PAGE_MANUAL, PAGE_MODEL, PAGE_SETTINGS, RESULT_BYPASS, ROLE_ADMIN,
    ROLE_OPERATOR,
)


def _stop_descendant_timers(widget) -> None:
    """Stop every QTimer owned by widget's QObject tree."""
    for timer in widget.findChildren(QTimer):
        timer.stop()


def _teardown_widget(widget) -> None:
    """Stop descendant timers and destroy the widget, tolerating pre-deletion.

    Two hazards for later test files:

    1. ConfigPage.quality_timer (5s, started in its constructor) formats
       MagicMock stats and raises inside later tests' Qt event loops, which
       pytest-qt reports as SETUP ERRORs for unrelated files.
    2. close() alone does not delete the C++ object, so signal connections
       to the session-long AppState singleton would survive and cross-talk
       with later tests.

    pytest-qt's _close_widgets() may already have destroyed the widget
    before fixture teardown runs, so a RuntimeError from a dead wrapper is
    expected and ignored.
    """
    try:
        _stop_descendant_timers(widget)
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    except RuntimeError:
        pass  # already destroyed by pytest-qt's _close_widgets


# ---------------------------------------------------------------------------
# 1. SessionController — PENDING/BYPASS completion path
# ---------------------------------------------------------------------------

class TestSessionControllerPendingPath:
    @pytest.fixture
    def controller(self):
        app_state = MagicMock()
        app_state.current_model_id = 1
        app_state.current_user = {"id": 7, "username": "op", "role": "OPERATOR"}
        app_state.session_repo.open_session.return_value = 42
        app_state.report_repo.get_sessions_summary.return_value = [{"id": 42}]

        evaluator = MagicMock()
        evaluator.evaluate_all.return_value = [
            EvalResult(
                register_id=10, mapping_id=1, display_name="Param A",
                group_name="Group", measured_value=5.0, display_str="5.00",
                result=RESULT_BYPASS, pass_value=1, fail_value=2,
                timestamp=datetime.now(timezone.utc),
            )
        ]
        evaluator.get_overall_result.return_value = RESULT_BYPASS
        return SessionController(app_state, evaluator)

    def test_bypass_cycle_closes_as_pending_not_fail(self, qtbot, controller):
        completed, errors, overalls = [], [], []
        controller.test_completed.connect(completed.append)
        controller.error_occurred.connect(errors.append)
        controller.overall_result.connect(overalls.append)

        controller.on_test_started()
        assert controller.active_session_id == 42

        controller.on_test_completed(None)

        # No NameError path taken
        assert errors == []
        # Session closed as PENDING, not force-closed as FAIL
        controller._app_state.session_repo.close_session.assert_called_once()
        kwargs = controller._app_state.session_repo.close_session.call_args.kwargs
        assert kwargs["overall_result"] == "PENDING"
        assert kwargs["ok_count"] == 0 and kwargs["ng_count"] == 0
        # Signal reports PENDING
        assert overalls == ["PENDING"]
        # Session released
        assert controller.active_session_id is None

    def test_no_active_session_is_noop(self, qtbot, controller):
        errors = []
        controller.error_occurred.connect(errors.append)
        controller.on_test_completed(None)
        assert errors == []


# ---------------------------------------------------------------------------
# 2. SettingsPage — theme / high contrast application
# ---------------------------------------------------------------------------

class TestSettingsPageThemeApply:
    @pytest.fixture
    def page(self, qtbot):
        from src.ui.theme_manager import ThemeManager
        state = MagicMock()
        state.current_theme = "dark"
        state.config_repo.get_high_contrast.return_value = False
        widget = SettingsPage(state, on_plc_reconnect=lambda: None)
        qtbot.addWidget(widget)
        yield widget
        _teardown_widget(widget)
        # Restore global stylesheet mutated by the theme tests
        ThemeManager.apply("dark")

    def test_apply_theme_does_not_raise(self, page):
        page._apply_theme("light")   # previously: ThemeManager.instance() AttributeError
        assert page.app_state.config_repo.set_theme.called

    def test_toggle_high_contrast_does_not_raise(self, page):
        page.high_contrast_btn.setChecked(True)
        page._toggle_high_contrast()  # previously: AttributeError
        page.app_state.config_repo.set_high_contrast.assert_called_with(True)

    def test_contrast_button_restored_from_config(self, page):
        page.app_state.config_repo.get_high_contrast.return_value = True
        page._refresh_contrast_button()
        assert page.high_contrast_btn.isChecked()
        assert "ON" in page.high_contrast_btn.text()


# ---------------------------------------------------------------------------
# 3. ReportsPage — export status widgets exist
# ---------------------------------------------------------------------------

class TestReportsPageExportWidgets:
    def test_export_widgets_constructed(self, qtbot):
        page = ReportsPage(MagicMock())
        qtbot.addWidget(page)
        assert hasattr(page, "export_bar")
        assert hasattr(page, "export_status")
        assert page.export_bar.objectName() == "reports_export_card"
        assert page.export_status.objectName() == "reports_export_status"
        assert not page.export_bar.isVisible()

    def test_on_export_finished_success(self, qtbot):
        page = ReportsPage(MagicMock())
        qtbot.addWidget(page)
        page._on_export_finished("Success: wrote file.xlsx")
        assert page.export_status.text() == "Success: wrote file.xlsx"
        assert page.export_status.property("status") == "success"

    def test_on_export_finished_error(self, qtbot):
        page = ReportsPage(MagicMock())
        qtbot.addWidget(page)
        page._on_export_finished("Error: boom")
        assert page.export_status.property("status") == "error"


# ---------------------------------------------------------------------------
# 4. MainWindow — navigation access gate
# ---------------------------------------------------------------------------

_STATE_FIELDS = (
    "current_user", "db", "connection_manager", "write_manager", "data_model",
    "config_repo", "profile_repo", "library_repo", "user_repo", "model_repo",
    "map_repo", "control_repo", "io_repo", "msg_repo", "session_repo",
    "report_repo", "plc_profile", "is_plc_configured",
)


@pytest.fixture
def window(qtbot, tmp_path):
    db = Database(str(tmp_path / "nav_fixes.db"))
    db.initialize()

    from src.db.seed import seed_database
    seed_database(db)

    # AppState is a session-wide singleton: snapshot the fields we overwrite
    # so later test files do not inherit our real Database.
    s = AppState.get_instance()
    saved = {n: getattr(s, n) for n in _STATE_FIELDS if hasattr(s, n)}

    s.current_user = None
    s.db = db
    s.connection_manager = MagicMock()
    s.write_manager = MagicMock()
    s.data_model = None

    from src.db.app_config_repo import AppConfigRepo
    from src.db.plc_profile_repo import PLCProfileRepository
    s.config_repo = AppConfigRepo(db)
    s.profile_repo = PLCProfileRepository(db)
    s.library_repo = RegisterLibraryRepo(db)
    s.user_repo = UserRepository(db)

    from src.db.model_repo import ModelRepository
    from src.db.model_map_repo import ModelMapRepo
    from src.db.control_repo import ControlRegisterRepo
    from src.db.io_list_repo import IOListRepo
    from src.db.message_repo import MessageRegisterRepo
    from src.db.session_repo import SessionRepository
    from src.db.report_repo import ReportRepository
    s.model_repo = ModelRepository(db)
    s.map_repo = ModelMapRepo(db)
    s.control_repo = ControlRegisterRepo(db)
    s.io_repo = IOListRepo(db)
    s.msg_repo = MessageRegisterRepo(db)
    s.session_repo = SessionRepository(db)
    s.report_repo = ReportRepository(db)
    s.plc_profile = s.profile_repo.get_profile()
    s.is_plc_configured = False

    win = MainWindow(s)
    # ConfigPage starts quality_timer in its constructor: stop it now so it
    # can never fire (with MagicMock stats) in a later test's event loop.
    _stop_descendant_timers(win)
    qtbot.addWidget(win)
    try:
        yield win, s
    finally:
        _teardown_widget(win)
        for name, value in saved.items():
            setattr(s, name, value)
        db.close_all()


class TestNavigateAccessGate:
    def test_settings_denied_for_operator(self, window):
        win, state = window
        state.set_user({"id": 99, "username": "op", "role": ROLE_OPERATOR})
        win.navigate_to(PAGE_MODEL)
        assert win.page_stack.currentWidget() is win.model_page

        win.navigate_to(PAGE_SETTINGS)
        # Denied: stack unchanged
        assert win.page_stack.currentWidget() is win.model_page

    def test_denied_navigation_has_no_side_effects(self, window):
        """on_page_hidden must NOT run when the access gate rejects."""
        win, state = window
        state.set_user({"id": 99, "username": "op", "role": ROLE_OPERATOR})
        win.navigate_to(PAGE_MANUAL)
        assert win.page_stack.currentWidget() is win.manual_page

        calls = []
        original = win.manual_page.on_page_hidden
        win.manual_page.on_page_hidden = lambda: (calls.append(1), original())

        win.navigate_to(PAGE_SETTINGS)  # denied for operator

        assert win.page_stack.currentWidget() is win.manual_page
        assert calls == []

    def test_settings_allowed_for_admin(self, window):
        win, state = window
        state.set_user({"id": 1, "username": "admin", "role": ROLE_ADMIN})
        win.navigate_to(PAGE_SETTINGS)
        assert win.page_stack.currentWidget() is win.settings_page


# ---------------------------------------------------------------------------
# 5. delete_user cascade guard
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "user_guard.db"))
    database.initialize()
    yield database
    database.close_all()


class TestDeleteUserGuard:
    def test_delete_blocked_when_user_owns_registers(self, db):
        users = UserRepository(db)
        lib = RegisterLibraryRepo(db)
        uid = users.create_user("creator", "hash", "OPERATOR")
        lib.create_register(
            name="REG_OWNED", register_address=10,
            register_type="HOLDING", data_type="INT16",
            access="READ_ONLY", created_by=uid,
        )

        with pytest.raises(ValueError, match="register"):
            users.delete_user(uid)

        assert users.get_user_by_username("creator") is not None

    def test_delete_allowed_without_owned_registers(self, db):
        users = UserRepository(db)
        uid = users.create_user("ghost", "hash", "OPERATOR")

        assert users.delete_user(uid) is True
        assert users.get_user_by_username("ghost") is None


# ---------------------------------------------------------------------------
# 6. Driver factory caching
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_factory_cache():
    PLCDriverFactory._cache.clear()
    yield
    PLCDriverFactory._cache.clear()


class TestDriverFactoryCaching:
    PROFILE = {
        "brand": "mitsubishi", "protocol": "TCP",
        "host": "127.0.0.1", "port": 5020,
        "slave_id": 1, "timeout_ms": 500,
    }

    def test_cached_create_reuses_instance(self):
        a = PLCDriverFactory.create(dict(self.PROFILE))
        b = PLCDriverFactory.create(dict(self.PROFILE))
        assert a is b
        assert len(PLCDriverFactory._cache) == 1

    def test_uncached_create_returns_distinct_driver(self):
        a = PLCDriverFactory.create(dict(self.PROFILE), cached=False)
        b = PLCDriverFactory.create(dict(self.PROFILE), cached=False)
        assert a is not b
        # Throwaway drivers never enter the shared cache
        assert len(PLCDriverFactory._cache) == 0

    def test_uncached_does_not_evict_cached_entry(self):
        live = PLCDriverFactory.create(dict(self.PROFILE))
        throwaway = PLCDriverFactory.create(dict(self.PROFILE), cached=False)
        assert throwaway is not live
        assert PLCDriverFactory.create(dict(self.PROFILE)) is live


# ---------------------------------------------------------------------------
# 7. ConfigPage quality timer slot must never raise
# ---------------------------------------------------------------------------

class TestUpdateLiveQualityRobust:
    def test_malformed_stats_do_not_raise(self, window):
        win, state = window
        page = win.config_page

        # Non-dict stats are ignored instead of crashing the event loop
        state.connection_manager.get_quality_stats.return_value = MagicMock()
        page._update_live_quality()

        # Valid dict updates the labels
        state.connection_manager.get_quality_stats.return_value = {
            "total_requests": 100,
            "avg_response_ms": 12.34,
            "success_rate_pct": 99.5,
        }
        page._update_live_quality()
        assert "Total Requests: 100" in page.quality_stats_lbl.text()
        assert "12.3" in page.quality_stats_lbl.text()
