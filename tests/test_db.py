"""
Unit tests for database core and repository layers.
Uses pytest with isolated temporary databases.

Updated for schema v4.3: seed_database creates users only (models and
registers are user-created via CONFIG), parameters live in
register_library + model_register_map, and messages live in
message_register (d21_messages was removed).
"""
import pytest
import sqlite3
import os
import bcrypt
from src.db.database import Database
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.model_repo import ModelRepository
from src.db.model_map_repo import ModelMapRepo
from src.db.register_library_repo import RegisterLibraryRepo
from src.db.message_repo import MessageRegisterRepo
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.seed import seed_database
from src.db.user_repo import UserRepository

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
        "map": ModelMapRepo(db),
        "lib": RegisterLibraryRepo(db),
        "msg": MessageRegisterRepo(db),
        "session": SessionRepository(db),
        "report": ReportRepository(db),
    }
    db.close_all()

def _mk_model(repos, name="TEST-MODEL", sort_order=0):
    return repos["model"].create_model(name, sort_order=sort_order)

def _mk_register(repos, name, address=100, rtype="HOLDING", dtype="INT16"):
    return repos["lib"].create_register(name, address, rtype, dtype)

class TestDatabase:
    def test_all_tables_created(self, fresh_db):
        """Verify that all tables defined in schema.sql are present."""
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        tables = [row["name"] for row in fresh_db.fetchall(query)]
        expected = [
            "users", "plc_profile", "register_library", "models",
            "model_register_map", "control_registers", "io_list_config",
            "register_blocks", "message_register", "test_sessions",
            "test_results", "plc_write_log", "session_comments",
            "app_config", "db_migrations"
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

class TestUserRepo:
    def test_authenticate_with_seeded_admin_password(self, repos):
        repo = UserRepository(repos["db"])
        user = repo.authenticate("admin", "Admin@1234")
        assert user is not None
        assert user["username"] == "admin"
        assert user["role"] == "ADMIN"

    def test_authenticate_rejects_wrong_password(self, repos):
        repo = UserRepository(repos["db"])
        assert repo.authenticate("admin", "wrong-password") is None

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

    def test_defaults_match_schema(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["brand"] == "mitsubishi"
        assert profile["protocol"] == "TCP"
        assert profile["port"] == 502
        assert profile["poll_interval_ms"] == 500

    def test_update_profile_rejects_unknown_keys(self, repos):
        assert repos["profile"].update_profile(bogus_key=1) is False
        assert repos["profile"].update_profile(host="10.0.0.5", bogus_key=1) is True

    def test_update_persists_settings(self, repos):
        repos["profile"].update_profile(port=1502, poll_interval_ms=250)
        profile = repos["profile"].get_profile()
        assert profile["port"] == 1502
        assert profile["poll_interval_ms"] == 250

    def test_empty_host_allowed(self, repos):
        # Set first
        repos["profile"].update_profile(host="1.1.1.1")
        # Clear
        success = repos["profile"].update_profile(host="")
        assert success is True
        assert repos["profile"].get_profile()["host"] == ""

    def test_message_mappings_roundtrip(self, repos):
        """Message mappings live in message_register (was d21_messages)."""
        reg_id = _mk_register(repos, "STATUS_REG", address=900)
        repos["msg"].add_message_mapping(reg_id, 0, "MACHINE READY", color="green")
        repos["msg"].add_message_mapping(reg_id, 1, "TRIP", color="red")
        msgs = repos["msg"].get_messages_for_register(reg_id)
        assert msgs[0] == ("MACHINE READY", "green")
        assert msgs[1] == ("TRIP", "red")
        assert len(msgs) == 2

class TestModelRepo:
    def test_seed_creates_no_models(self, repos):
        """Seed creates users only; models are user-created via CONFIG."""
        assert len(repos["model"].get_all_models()) == 0

    def test_models_sorted_by_sort_order(self, repos):
        _mk_model(repos, "B-MODEL", sort_order=2)
        _mk_model(repos, "A-MODEL", sort_order=1)
        _mk_model(repos, "C-MODEL", sort_order=3)
        names = [m["name"] for m in repos["model"].get_all_models()]
        assert names == ["A-MODEL", "B-MODEL", "C-MODEL"]

    def test_full_config_lists_parameters(self, repos):
        mid = _mk_model(repos, "FULL-CFG")
        r1 = _mk_register(repos, "P1_REG", address=100)
        r2 = _mk_register(repos, "P2_REG", address=102)
        repos["map"].add_mapping(mid, r1, role="MEASURED",
                                 display_name="P1", group_name="MOD-A")
        repos["map"].add_mapping(mid, r2, role="RESULT",
                                 display_name="P2", group_name="MOD-B")
        config = repos["model"].get_full_model_config(mid)
        assert len(config["parameters"]) == 2
        names = {p["param_name"] for p in config["parameters"]}
        assert names == {"P1", "P2"}

    def test_disabled_mappings_excluded(self, repos):
        mid = _mk_model(repos, "DIS-CFG")
        r1 = _mk_register(repos, "ON_REG", address=110)
        r2 = _mk_register(repos, "OFF_REG", address=112)
        repos["map"].add_mapping(mid, r1, enabled=True)
        repos["map"].add_mapping(mid, r2, enabled=False)
        config = repos["model"].get_full_model_config(mid)
        assert len(config["parameters"]) == 1
        assert config["parameters"][0]["register_id"] == r1

    def test_full_config_has_module_groups(self, repos):
        mid = _mk_model(repos, "GROUPED")
        r1 = _mk_register(repos, "G1_REG", address=120)
        r2 = _mk_register(repos, "G2_REG", address=122)
        repos["map"].add_mapping(mid, r1, display_name="X",
                                 group_name="DIPPER MODULE")
        repos["map"].add_mapping(mid, r2, display_name="Y",
                                 group_name="BLINKER MODULE")
        config = repos["model"].get_full_model_config(mid)
        groups = config["module_groups"]
        assert "DIPPER MODULE" in groups
        assert "BLINKER MODULE" in groups

    def test_full_config_parameters_carry_register_details(self, repos):
        mid = _mk_model(repos, "ADDR-CFG")
        r1 = _mk_register(repos, "ADDR_REG", address=150, rtype="COIL",
                          dtype="BOOL")
        repos["map"].add_mapping(mid, r1, display_name="CoilX")
        config = repos["model"].get_full_model_config(mid)
        p = config["parameters"][0]
        assert p["address"] == 150
        assert p["type"] == "COIL"
        assert p["data_type"] == "BOOL"

    def test_create_delete_model(self, repos):
        mid = repos["model"].create_model("TEMP-MODEL")
        assert repos["model"].get_model(mid) is not None
        repos["model"].delete_model(mid)
        assert repos["model"].get_model(mid) is None

    def test_duplicate_name_raises(self, repos):
        repos["model"].create_model("TAKEN-NAME")
        with pytest.raises(ValueError, match="already exists"):
            repos["model"].create_model("TAKEN-NAME")

class TestModelMapRepo:
    def test_add_mapping(self, repos):
        mid = _mk_model(repos, "MAP-MODEL")
        rid = _mk_register(repos, "MAP_REG")
        map_id = repos["map"].add_mapping(mid, rid, display_name="Mapped")
        assert map_id > 0
        mappings = repos["map"].get_model_mappings(mid)
        assert len(mappings) == 1
        assert mappings[0]["register_id"] == rid

    def test_duplicate_mapping_rejected(self, repos):
        mid = _mk_model(repos, "DUP-MODEL")
        rid = _mk_register(repos, "DUP_REG")
        repos["map"].add_mapping(mid, rid)
        with pytest.raises(ValueError, match="already mapped"):
            repos["map"].add_mapping(mid, rid)

    def test_get_by_module(self, repos):
        mid = _mk_model(repos, "MOD-MODEL")
        r1 = _mk_register(repos, "M1_REG", address=130)
        r2 = _mk_register(repos, "M2_REG", address=131)
        r3 = _mk_register(repos, "M3_REG", address=132)
        repos["map"].add_mapping(mid, r1, group_name="DIPPER MODULE")
        repos["map"].add_mapping(mid, r2, group_name="DIPPER MODULE")
        repos["map"].add_mapping(mid, r3, group_name="HORN MODULE")
        config = repos["model"].get_full_model_config(mid)
        assert len(config["module_groups"]["DIPPER MODULE"]) == 2
        assert len(config["module_groups"]["HORN MODULE"]) == 1

    def test_update_mapping_fields(self, repos):
        mid = _mk_model(repos, "UPD-MODEL")
        rid = _mk_register(repos, "UPD_REG")
        map_id = repos["map"].add_mapping(mid, rid)
        repos["map"].update_mapping(map_id, display_name="Renamed",
                                    limit_min=5.0, limit_max=50.0)
        m = repos["map"].get_model_mappings(mid)[0]
        assert m["display_name"] == "Renamed"
        assert m["limit_min"] == 5.0
        assert m["limit_max"] == 50.0

    def test_remove_all_and_copy_mappings(self, repos):
        src = _mk_model(repos, "SRC-MODEL")
        dst = _mk_model(repos, "DST-MODEL")
        r1 = _mk_register(repos, "COPY_REG", address=140)
        r2 = _mk_register(repos, "COPY_REG2", address=141)
        repos["map"].add_mapping(src, r1)
        repos["map"].add_mapping(src, r2)

        copied = repos["map"].copy_mappings(src, dst)
        assert copied == 2
        assert len(repos["map"].get_model_mappings(dst)) == 2

        repos["map"].remove_all_mappings(src)
        assert len(repos["map"].get_model_mappings(src)) == 0
        assert len(repos["map"].get_model_mappings(dst)) == 2

    def test_validate_warns_without_mappings(self, repos):
        mid = _mk_model(repos, "EMPTY-MODEL")
        warnings = repos["map"].validate_model_mappings(mid)
        assert any("no enabled register mappings" in w.lower() for w in warnings)

    def test_validate_detects_duplicate_positions(self, repos):
        mid = _mk_model(repos, "POS-MODEL")
        r1 = _mk_register(repos, "P1_REG", address=160)
        r2 = _mk_register(repos, "P2_REG", address=161)
        repos["map"].add_mapping(mid, r1, card_position=1)
        repos["map"].add_mapping(mid, r2, card_position=1)
        warnings = repos["map"].validate_model_mappings(mid)
        assert any("duplicate" in w.lower() for w in warnings)

class TestSessionRepo:
    def test_open_close_session(self, repos):
        mid = _mk_model(repos, "SESS-MODEL")
        sid = repos["session"].open_session(mid, 1)
        assert sid > 0
        repos["session"].close_session(sid, 10, 2, 1, "Notes")
        session = repos["db"].fetchone("SELECT * FROM test_sessions WHERE id = ?", (sid,))
        assert session["ended_at"] is not None
        assert session["ok_count"] == 10

    def test_record_result_with_module_name(self, repos):
        mid = _mk_model(repos, "RES-MODEL")
        rid = _mk_register(repos, "RES_REG", address=170)
        sid = repos["session"].open_session(mid, 1)
        res_id = repos["session"].record_result(
            sid, rid, "P1", "MOD-A", 1.23, 1.0, 2.0, "PASS")
        result = repos["db"].fetchone("SELECT * FROM test_results WHERE id = ?", (res_id,))
        assert result["group_name"] == "MOD-A"
        assert result["measured_value"] == 1.23
        assert result["result"] == "PASS"

    def test_increment_ok_ng(self, repos):
        mid = _mk_model(repos, "INC-MODEL")
        sid = repos["session"].open_session(mid, 1)
        repos["session"].increment_ok(sid)
        repos["session"].increment_ng(sid)
        session = repos["db"].fetchone("SELECT * FROM test_sessions WHERE id = ?", (sid,))
        assert session["ok_count"] == 1
        assert session["ng_count"] == 1

class TestSeed:
    def test_host_empty_after_seed(self, repos):
        profile = repos["profile"].get_profile()
        assert profile["host"] == ""

    def test_no_models_or_registers_preset(self, repos):
        """v4.3 seed policy: users only — CONFIG is used for the rest."""
        assert len(repos["model"].get_all_models()) == 0
        assert len(repos["lib"].get_all_registers()) == 0

    def test_message_register_empty_after_seed(self, repos):
        assert repos["db"].fetchall("SELECT * FROM message_register") == []

    def test_seed_idempotent(self, repos):
        # Seed again
        seed_database(repos["db"])
        users = repos["db"].fetchall("SELECT * FROM users")
        assert len(users) == 2 # Still 2, not 4
