"""
Unit tests for database core and repository layers.
Uses pytest with isolated temporary databases.
"""
import pytest
import sqlite3
import os
import bcrypt
from src.db.database import Database
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.seed import seed_database

@pytest.fixture
def fresh_db(tmp_path):
    """Provides a fresh, initialized but empty database."""
    db_path = str(tmp_path / "test_fresh.db")
    db = Database(db_path)
    db.initialize()
    yield db
    db.close_all()

@pytest.fixture
def repos(tmp_path):
    """Provides a fully seeded database and all repositories."""
    db_path = str(tmp_path / "test_seeded.db")
    db = Database(db_path)
    db.initialize()
    seed_database(db)
    
    yield {
        "db": db,
        "profile": PLCProfileRepository(db),
        "model": ModelRepository(db),
        "param": ParameterRepository(db),
        "session": SessionRepository(db),
        "report": ReportRepository(db),
    }
    db.close_all()

class TestDatabase:
    def test_all_12_tables_created(self, fresh_db):
        """Verify that all tables defined in schema.sql are present."""
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        tables = [row["name"] for row in fresh_db.fetchall(query)]
        expected = [
            "users", "plc_profile", "d21_messages", "models", 
            "model_parameters", "model_settings", "test_sessions", 
            "test_results", "session_alarms", "session_comments", 
            "plc_write_log", "db_migrations"
        ]
        for table in expected:
            assert table in tables

    def test_wal_mode_enabled(self, fresh_db):
        """Verify journal_mode is set to WAL."""
        row = fresh_db.fetchone("PRAGMA journal_mode")
        assert row["journal_mode"].lower() == "wal"

    def test_foreign_keys_on(self, fresh_db):
        """Verify foreign_key enforcement is active."""
        row = fresh_db.fetchone("PRAGMA foreign_keys")
        assert row["foreign_keys"] == 1

    def test_sql_injection_blocked(self, fresh_db):
        """Verify that parameterized queries handle special characters safely."""
        # Insert a user with a malicious name
        malicious_name = "admin'; DROP TABLE users; --"
        fresh_db.execute("INSERT INTO users (username, role, password_hash) VALUES (?, ?, ?)", 
                        (malicious_name, "ADMIN", "hash"))
        
        # Verify the table still exists and the user is there
        user = fresh_db.fetchone("SELECT * FROM users WHERE username = ?", (malicious_name,))
        assert user is not None
        assert user["username"] == malicious_name

class TestPLCProfileRepo:
    def test_seed_creates_id_1(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["id"] == 1

    def test_host_is_empty_string(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["host"] == ""

    def test_is_configured_false_when_empty(self, repos):
        assert repos["profile"].is_configured() is False

    def test_is_configured_true_after_set(self, repos):
        repos["profile"].update_profile(host="192.168.1.30")
        assert repos["profile"].is_configured() is True

    def test_ok_count_register_is_300(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["ok_count_register"] == 300

    def test_ng_count_register_is_320(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["ng_count_register"] == 320

    def test_start_coil_is_10(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["start_coil"] == 10

    def test_update_host_validates_ip(self, repos):
        with pytest.raises(ValueError, match="Invalid host IP"):
            repos["profile"].update_profile(host="invalid-ip")

    def test_empty_host_allowed(self, repos):
        # Set first
        repos["profile"].update_profile(host="1.1.1.1")
        # Clear
        success = repos["profile"].update_profile(host="")
        assert success is True
        assert repos["profile"].get_profile()["host"] == ""

    def test_get_d21_messages_returns_dict(self, repos):
        msgs = repos["profile"].get_d21_messages()
        assert isinstance(msgs, dict)
        assert len(msgs) >= 15
        assert msgs[0][0] == "MACHINE READY"

class TestModelRepo:
    def test_seed_creates_4_models(self, repos):
        models = repos["model"].get_all_models()
        assert len(models) == 4

    def test_models_sorted_by_sort_order(self, repos):
        models = repos["model"].get_all_models()
        assert models[0]["name"] == "SW-0256"
        assert models[-1]["name"] == "SW-0256U"

    def test_sw0256u_has_4_params(self, repos):
        model = repos["model"].get_model_by_name("SW-0256U")
        params = repos["param"].get_model_parameters(model["id"])
        assert len(params) == 4

    def test_sw0256_has_6_params(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        params = repos["param"].get_model_parameters(model["id"])
        assert len(params) == 6

    def test_full_config_has_module_groups(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        config = repos["model"].get_full_model_config(model["id"])
        groups = config["module_groups"]
        assert "DIPPER MODULE" in groups
        assert "BLINKER MODULE" in groups
        assert "HORN MODULE" in groups

    def test_register_map_uses_d_numbers(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        config = repos["model"].get_full_model_config(model["id"])
        reg_map = config["register_map"]
        # Dipper LOW measured register is D100
        assert reg_map["Dipper LOW"]["measured"] == 100
        # Dipper LOW result register is D30
        assert reg_map["Dipper LOW"]["result"] == 30

    def test_create_delete_model(self, repos):
        mid = repos["model"].create_model("TEMP-MODEL")
        assert repos["model"].get_model(mid) is not None
        repos["model"].delete_model(mid)
        assert repos["model"].get_model(mid) is None

    def test_duplicate_name_raises(self, repos):
        with pytest.raises(ValueError, match="already exists"):
            repos["model"].create_model("SW-0256")

class TestParameterRepo:
    def test_add_parameter(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        pid = repos["param"].add_parameter(
            model["id"], "NEW_PARAM", "New Display", "TEST", 99, 
            measured_register=500
        )
        assert pid > 0

    def test_duplicate_name_raises(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        with pytest.raises(ValueError, match="already exists"):
            repos["param"].add_parameter(model["id"], "Dipper LOW", "x", "x", 10)

    def test_get_by_module(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        modules = repos["param"].get_parameters_by_module(model["id"])
        assert len(modules["DIPPER MODULE"]) == 2

    def test_update_registers(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        params = repos["param"].get_model_parameters(model["id"])
        p0 = params[0]
        repos["param"].update_parameter_registers(p0["id"], measured_register=999)
        updated = repos["param"].get_model_parameters(model["id"])[0]
        assert updated["measured_register"] == 999

    def test_update_limits_validates_range(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        params = repos["param"].get_model_parameters(model["id"])
        with pytest.raises(ValueError, match="less than"):
            repos["param"].update_parameter_limits(params[0]["id"], 100, 50)

    def test_replace_all_atomic_rollback(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        original_count = len(repos["param"].get_model_parameters(model["id"]))
        
        # Attempt replacement with one invalid param (missing required field or logic error)
        invalid_params = [
            {"param_name": "GOOD", "display_name": "G", "module_name": "M", "param_order": 1},
            {"param_name": "BAD", "display_name": "B", "module_name": "M", "param_order": 1} # Duplicate order
        ]
        
        try:
            repos["param"].replace_all_parameters(model["id"], invalid_params)
        except Exception:
            pass # Expected failure
        
        # Verify original parameters are still there
        final_params = repos["param"].get_model_parameters(model["id"])
        assert len(final_params) == original_count
        assert any(p["param_name"] == "Dipper LOW" for p in final_params)

    def test_validate_detects_duplicate_registers(self, repos):
        model = repos["model"].get_model_by_name("SW-0256")
        # Add a param with a conflicting register
        repos["param"].add_parameter(model["id"], "CONFLICT", "C", "M", 99, measured_register=100) # 100 is Dipper LOW
        warnings = repos["param"].validate_model_parameters(model["id"])
        assert any("conflict" in w.lower() for w in warnings)

    def test_model_settings_created_for_all_models(self, repos):
        models = repos["model"].get_all_models()
        for m in models:
            settings = repos["param"].get_model_settings(m["id"])
            assert settings is not None
            assert settings["model_id"] == m["id"]

class TestSessionRepo:
    def test_open_close_session(self, repos):
        model = repos["model"].get_all_models()[0]
        sid = repos["session"].open_session(model["id"], 1)
        assert sid > 0
        repos["session"].close_session(sid, 10, 2, 1, "Notes")
        session = repos["db"].fetchone("SELECT * FROM test_sessions WHERE id = ?", (sid,))
        assert session["ended_at"] is not None
        assert session["ok_count"] == 10

    def test_record_result_with_module_name(self, repos):
        model = repos["model"].get_all_models()[0]
        sid = repos["session"].open_session(model["id"], 1)
        res_id = repos["session"].record_result(sid, 1, "P1", "MOD-A", 1.23, 1.0, 2.0, "PASS")
        result = repos["db"].fetchone("SELECT * FROM test_results WHERE id = ?", (res_id,))
        assert result["module_name"] == "MOD-A"

    def test_increment_ok_ng(self, repos):
        sid = repos["session"].open_session(1, 1)
        repos["session"].increment_ok(sid)
        repos["session"].increment_ng(sid)
        session = repos["db"].fetchone("SELECT * FROM test_sessions WHERE id = ?", (sid,))
        assert session["ok_count"] == 1
        assert session["ng_count"] == 1

class TestSeed:
    def test_host_empty_after_seed(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["host"] == ""

    def test_4_models_seeded(self, repos):
        models = repos["model"].get_all_models()
        assert len(models) == 4

    def test_d21_messages_present(self, repos):
        msgs = repos["profile"].get_d21_messages()
        assert len(msgs) >= 15

    def test_seed_idempotent(self, repos):
        # Seed again
        seed_database(repos["db"])
        users = repos["db"].fetchall("SELECT * FROM users")
        assert len(users) == 2 # Still 2, not 4
