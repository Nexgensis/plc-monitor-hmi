"""
Unit tests for Phase 1 — register_blocks table, BlockRepo CRUD/validation,
and the v4.3 migrations on legacy databases.

Run: venv\\Scripts\\python.exe -m pytest tests/test_block_repo.py -q
"""
import sqlite3

import pytest

from src.db.database import Database
from src.db.block_repo import BlockRepo


@pytest.fixture
def db(tmp_path):
    """Fresh, initialized but empty database."""
    path = str(tmp_path / "blocks.db")
    database = Database(path)
    database.initialize()
    yield database
    database.close_all()


@pytest.fixture
def repo(db):
    return BlockRepo(db)


# ----------------------------------------------------------------------
# Schema (fresh install path — schema.sql)
# ----------------------------------------------------------------------
class TestFreshSchema:
    def test_register_blocks_table_created(self, db):
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='register_blocks'"
        )
        assert row is not None

    def test_write_log_has_block_id_column(self, db):
        cols = [r["name"] for r in db.fetchall("PRAGMA table_info(plc_write_log)")]
        assert "block_id" in cols

    def test_block_id_is_nullable(self, db):
        cols = {r["name"]: r for r in db.fetchall("PRAGMA table_info(plc_write_log)")}
        assert cols["block_id"]["notnull"] == 0

    def test_indexes_created(self, db):
        names = [
            r["name"]
            for r in db.fetchall("SELECT name FROM sqlite_master WHERE type='index'")
        ]
        assert "idx_register_blocks_order" in names
        assert "idx_write_log_block" in names

    def test_v43_migrations_recorded(self, db):
        names = [r["name"] for r in db.fetchall("SELECT name FROM db_migrations")]
        assert "v4.3_register_blocks" in names
        assert "v4.3_write_log_block_id" in names
        assert "v4.3_write_log_block_index" in names


# ----------------------------------------------------------------------
# Migration (existing-DB path — no block_id, no register_blocks)
# ----------------------------------------------------------------------
class TestLegacyMigration:
    @pytest.fixture
    def legacy_db_path(self, tmp_path):
        """
        Simulates a production DB created before Phase 1: full old schema
        except plc_write_log lacks block_id, and v4.1/v4.2 already recorded
        (mirrors the real plc_monitor.db state).
        """
        path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE plc_write_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now','utc')),
                register_id INTEGER REFERENCES register_library(id) ON DELETE CASCADE,
                register_address INTEGER NOT NULL,
                register_name TEXT NOT NULL,
                value_written TEXT NOT NULL,
                value_readback TEXT DEFAULT NULL,
                write_success INTEGER DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                operator_id INTEGER REFERENCES users(id),
                write_reason TEXT NOT NULL
            );
            CREATE TABLE db_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT DEFAULT (datetime('now','utc'))
            );
            INSERT INTO db_migrations (name) VALUES
                ('v4.1_limit_columns'), ('v4.2_mapping_limit_columns');
            """
        )
        conn.commit()
        conn.close()
        return path

    def test_migration_adds_column_and_table(self, legacy_db_path):
        db = Database(legacy_db_path)
        try:
            db.initialize()
            cols = [
                r["name"]
                for r in db.fetchall("PRAGMA table_info(plc_write_log)")
            ]
            assert "block_id" in cols
            row = db.fetchone(
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name='register_blocks'"
            )
            assert row is not None
            names = [r["name"] for r in db.fetchall("SELECT name FROM db_migrations")]
            assert "v4.3_write_log_block_id" in names
        finally:
            db.close_all()

    def test_migration_preserves_existing_audit_rows(self, legacy_db_path):
        conn = sqlite3.connect(legacy_db_path)
        conn.execute(
            "INSERT INTO plc_write_log (register_address, register_name,"
            " value_written, write_success, write_reason)"
            " VALUES (100, 'D100', '5', 1, 'Manual click')"
        )
        conn.commit()
        conn.close()

        db = Database(legacy_db_path)
        try:
            db.initialize()
            rows = db.fetchall("SELECT * FROM plc_write_log")
            assert len(rows) == 1
            assert rows[0]["register_name"] == "D100"
            assert rows[0]["block_id"] is None
        finally:
            db.close_all()

    def test_migration_is_idempotent(self, legacy_db_path):
        db = Database(legacy_db_path)
        try:
            db.initialize()
            db.initialize()  # second startup must not fail or duplicate
            names = [
                r["name"]
                for r in db.fetchall(
                    "SELECT name FROM db_migrations WHERE name LIKE 'v4.3%'"
                )
            ]
            assert len(names) == 3
        finally:
            db.close_all()


# ----------------------------------------------------------------------
# CRUD + validation
# ----------------------------------------------------------------------
class TestBlockCreate:
    def test_create_minimal_block(self, repo):
        bid = repo.create_block("Coils 0-99", "COIL", 0, 100)
        block = repo.get_block(bid)
        assert block is not None
        assert block["name"] == "Coils 0-99"
        assert block["register_type"] == "COIL"
        assert block["start_address"] == 0
        assert block["count"] == 100
        assert block["data_type"] == "BOOL"       # forced for bit blocks
        assert block["access"] == "READ_ONLY"
        assert block["is_active"] == 1

    def test_create_holding_range_100_200(self, repo):
        # 100..200 inclusive = 101 words
        bid = repo.create_block("HR 100-200", "HOLDING", 100, 101,
                                data_type="INT16", access="READ_WRITE")
        block = repo.get_block(bid)
        assert block["start_address"] == 100
        assert block["count"] == 101
        assert block["data_type"] == "INT16"
        assert block["access"] == "READ_WRITE"

    def test_coil_data_type_forced_bool(self, repo):
        bid = repo.create_block("Bits", "COIL", 0, 10, data_type="FLOAT32")
        assert repo.get_block(bid)["data_type"] == "BOOL"

    def test_duplicate_name_rejected(self, repo):
        repo.create_block("Dup", "COIL", 0, 8)
        with pytest.raises(ValueError, match="already exists"):
            repo.create_block("Dup", "COIL", 8, 8)

    def test_invalid_register_type_rejected(self, repo):
        with pytest.raises(ValueError, match="register type"):
            repo.create_block("Bad", "MEMORY", 0, 10)

    def test_empty_name_rejected(self, repo):
        with pytest.raises(ValueError, match="name"):
            repo.create_block("   ", "COIL", 0, 10)

    def test_zero_count_rejected(self, repo):
        with pytest.raises(ValueError, match="greater than zero"):
            repo.create_block("Zero", "COIL", 0, 0)

    def test_negative_count_rejected(self, repo):
        with pytest.raises(ValueError, match="greater than zero"):
            repo.create_block("Neg", "HOLDING", 0, -5)

    def test_bit_count_over_limit_rejected(self, repo):
        from src.utils.constants import MAX_BLOCK_COUNT_BITS
        with pytest.raises(ValueError, match=str(MAX_BLOCK_COUNT_BITS)):
            repo.create_block("TooBig", "COIL", 0, MAX_BLOCK_COUNT_BITS + 1)

    def test_reg_count_over_limit_rejected(self, repo):
        from src.utils.constants import MAX_BLOCK_COUNT_REGS
        with pytest.raises(ValueError, match=str(MAX_BLOCK_COUNT_REGS)):
            repo.create_block("TooBig", "HOLDING", 0, MAX_BLOCK_COUNT_REGS + 1,
                              data_type="INT16")

    def test_start_address_over_65535_rejected(self, repo):
        with pytest.raises(ValueError, match="0-65535"):
            repo.create_block("OOR", "HOLDING", 65536, 1)

    def test_range_overflow_rejected(self, repo):
        with pytest.raises(ValueError, match="65535"):
            repo.create_block("Edge", "HOLDING", 65535, 2)

    def test_float32_stride_validated(self, repo):
        with pytest.raises(ValueError, match="multiple of 2"):
            repo.create_block("OddFloats", "HOLDING", 0, 3, data_type="FLOAT32")
        bid = repo.create_block("EvenFloats", "HOLDING", 0, 4, data_type="FLOAT32")
        assert repo.get_block(bid)["count"] == 4

    def test_bool_data_type_rejected_for_holding(self, repo):
        with pytest.raises(ValueError, match="BOOL"):
            repo.create_block("NotBits", "HOLDING", 0, 4, data_type="BOOL")

    def test_discrete_write_access_rejected(self, repo):
        with pytest.raises(ValueError, match="read-only"):
            repo.create_block("XBlock", "DISCRETE", 0, 10, access="READ_WRITE")

    def test_input_write_access_rejected(self, repo):
        with pytest.raises(ValueError, match="read-only"):
            repo.create_block("Analog", "INPUT", 0, 10, access="READ_WRITE")

    def test_zero_scale_rejected(self, repo):
        with pytest.raises(ValueError, match="Scale"):
            repo.create_block("Scaled", "HOLDING", 0, 2, scale_factor=0)

    def test_decimal_places_bounds(self, repo):
        with pytest.raises(ValueError, match="0-6"):
            repo.create_block("Dp", "HOLDING", 0, 2, decimal_places=7)

    def test_word_count_must_match_max_boundary(self, repo):
        # exactly at limits must pass
        from src.utils.constants import MAX_BLOCK_COUNT_BITS, MAX_BLOCK_COUNT_REGS
        b1 = repo.create_block("MaxBits", "COIL", 0, MAX_BLOCK_COUNT_BITS)
        b2 = repo.create_block("MaxRegs", "HOLDING", 0, MAX_BLOCK_COUNT_REGS,
                               data_type="INT16")
        assert repo.get_block(b1) is not None
        assert repo.get_block(b2) is not None

    def test_created_by_foreign_key(self, db, repo):
        cur = db.execute(
            "INSERT INTO users (username, role, password_hash)"
            " VALUES ('blocks_admin', 'ADMIN', 'x')"
        )
        uid = cur.lastrowid
        bid = repo.create_block("Owned", "COIL", 0, 4, created_by=uid)
        assert repo.get_block(bid)["created_by"] == uid


class TestBlockUpdate:
    @pytest.fixture
    def sample(self, repo):
        bid = repo.create_block("Sample", "HOLDING", 100, 101,
                                data_type="INT16", access="READ_WRITE",
                                group_name="Process", row_order=2)
        return bid

    def test_update_count_revalidates(self, db, repo, sample):
        repo.update_block(sample, count=50)
        block = repo.get_block(sample)
        assert block["count"] == 50
        assert block["start_address"] == 100  # untouched

    def test_update_overflow_rolls_back(self, db, repo, sample):
        # 65000 + 1000 - 1 exceeds 65535 while count stays within its own cap
        with pytest.raises(ValueError, match="65535"):
            repo.update_block(sample, start_address=65000, count=1000)
        assert repo.get_block(sample)["count"] == 101  # unchanged
        assert repo.get_block(sample)["start_address"] == 100

    def test_update_unknown_field_rejected(self, repo, sample):
        with pytest.raises(ValueError, match="Unknown"):
            repo.update_block(sample, evil_column="x")

    def test_update_name_collision_rejected(self, repo):
        repo.create_block("Taken", "COIL", 0, 4)
        bid = repo.create_block("Mine", "COIL", 10, 4)
        with pytest.raises(ValueError, match="already exists"):
            repo.update_block(bid, name="Taken")

    def test_update_type_change_requires_compatible_data_type(self, repo, sample):
        # HOLDING row carries INT16; switching to COIL forces BOOL internally —
        # but switching a BOOL-forced row back to HOLDING with BOOL must fail.
        repo.update_block(sample, register_type="COIL", count=10,
                          data_type="INT16")  # coerced to BOOL
        assert repo.get_block(sample)["data_type"] == "BOOL"
        with pytest.raises(ValueError, match="BOOL"):
            repo.update_block(sample, register_type="HOLDING", count=10)

    def test_delete_block(self, repo, sample):
        repo.delete_block(sample)
        assert repo.get_block(sample) is None


class TestBlockQueries:
    @pytest.fixture
    def seeded(self, repo):
        repo.create_block("A Bits", "COIL", 0, 10, group_name="Inputs",
                          row_order=2)
        repo.create_block("B Bits", "COIL", 20, 10, group_name="Inputs",
                          row_order=1)
        repo.create_block("C Regs", "HOLDING", 100, 101, group_name="Process",
                          row_order=0, access="READ_WRITE")
        off = repo.create_block("Disabled", "COIL", 100, 5, group_name="Inputs")
        repo.update_block(off, is_active=False)
        repo.create_block("Ungrouped", "COIL", 200, 4, group_name="")
        return repo

    def test_get_poll_blocks_active_only(self, seeded):
        blocks = seeded.get_poll_blocks()
        names = {b["name"] for b in blocks}
        assert "Disabled" not in names
        assert len(blocks) == 4

    def test_poll_blocks_have_block_id(self, seeded):
        for b in seeded.get_poll_blocks():
            assert b["block_id"] == b["id"]

    def test_poll_blocks_ordering(self, seeded):
        blocks = seeded.get_poll_blocks()
        groups = [(b["group_name"], b["row_order"]) for b in blocks]
        assert groups == sorted(groups)

    def test_get_all_blocks_includes_inactive(self, seeded):
        all_blocks = seeded.get_all_blocks()
        assert len(all_blocks) == 5
        active = seeded.get_all_blocks(active_only=True)
        assert len(active) == 4

    def test_group_filter(self, seeded):
        inputs = seeded.get_all_blocks(group_name="Inputs")
        assert {b["name"] for b in inputs} == {"A Bits", "B Bits", "Disabled"}
        active_inputs = seeded.get_all_blocks(group_name="Inputs", active_only=True)
        assert {b["name"] for b in active_inputs} == {"A Bits", "B Bits"}

    def test_get_groups_excludes_empty(self, seeded):
        assert seeded.get_groups() == ["Inputs", "Process"]


# ----------------------------------------------------------------------
# Audit-log interplay (schema smoke — full write flow is Phase 4)
# ----------------------------------------------------------------------
class TestAuditSmoke:
    def test_write_log_row_with_block_id_and_null_register(self, db, repo):
        bid = repo.create_block("Audited", "HOLDING", 100, 10,
                                access="READ_WRITE")
        db.execute(
            "INSERT INTO plc_write_log (register_id, block_id,"
            " register_address, register_name, value_written,"
            " write_success, write_reason)"
            " VALUES (NULL, ?, 100, 'Audited [100..109]', '10 values', 1,"
            " 'Block write')",
            (bid,),
        )
        row = db.fetchone("SELECT * FROM plc_write_log")
        assert row["block_id"] == bid
        assert row["register_id"] is None

    def test_delete_block_keeps_audit_history(self, db, repo):
        bid = repo.create_block("Temp", "COIL", 0, 4, access="READ_WRITE")
        db.execute(
            "INSERT INTO plc_write_log (register_id, block_id,"
            " register_address, register_name, value_written,"
            " write_success, write_reason)"
            " VALUES (NULL, ?, 0, 'Temp [0..3]', '1,0,1,0', 1, 'Block write')",
            (bid,),
        )
        repo.delete_block(bid)
        row = db.fetchone("SELECT * FROM plc_write_log")
        assert row is not None
        assert row["block_id"] is None  # ON DELETE SET NULL preserves history
