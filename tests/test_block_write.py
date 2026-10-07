"""
Phase 4 — execute_block_write tests.

Covers:
    - Validation rejections (read-only types, access, count, value ranges)
    - FC16/FC0F dispatch through the driver (normalized raw words/bits)
    - Read-back verification + verify_failed signal
    - Audit rows in plc_write_log carrying block_id / REASON_BLOCK_WRITE
    - Write-lock sharing with single-register writes and lock release
    - Failure paths (PLC reject, missing driver) audited as write_success=0

Run: venv\\Scripts\\python.exe -m pytest tests/test_block_write.py -q
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.db.database import Database
from src.plc.base_driver import PLCDriver, PLCReadResult, PLCWriteResult
from src.plc.write_manager import PLCWriteManager, _summarize_values
from src.utils.constants import REASON_BLOCK_WRITE


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "write.db")
    database = Database(path)
    database.initialize()
    yield database
    database.close_all()


@pytest.fixture
def user_id(db):
    cur = db.execute(
        "INSERT INTO users (username, role, password_hash)"
        " VALUES ('block_writer', 'ADMIN', 'x')"
    )
    return cur.lastrowid


@pytest.fixture
def block_row(db, user_id):
    """Real register_blocks row (HOLDING, 100+5, READ_WRITE) — satisfies the
    plc_write_log.block_id foreign key during audit tests."""
    from src.db.block_repo import BlockRepo
    repo = BlockRepo(db)
    bid = repo.create_block(
        "Write Block", "HOLDING", 100, 5,
        data_type="INT16", access="READ_WRITE", created_by=user_id,
    )
    blk = repo.get_block(bid)
    blk["block_id"] = bid
    return blk


@pytest.fixture
def coil_row(db, user_id):
    """Real register_blocks COIL row (0+3, READ_WRITE)."""
    from src.db.block_repo import BlockRepo
    repo = BlockRepo(db)
    bid = repo.create_block(
        "Coil Block", "COIL", 0, 3,
        data_type="BOOL", access="READ_WRITE", created_by=user_id,
    )
    blk = repo.get_block(bid)
    blk["block_id"] = bid
    return blk


def make_block(**overrides) -> dict:
    blk = {
        "id": 1,
        "block_id": 1,
        "name": "Write Block",
        "register_type": "HOLDING",
        "start_address": 100,
        "count": 5,
        "access": "READ_WRITE",
    }
    blk.update(overrides)
    return blk


class FakeDriver(PLCDriver):
    """In-memory driver that stores block writes and echoes them on read."""

    def __init__(self) -> None:
        super().__init__("mitsubishi", "fake", 502)
        self.memory: list[int] = []
        self.fail_write = False
        self.verify_override: list[int] | None = None
        self.write_calls: list[tuple] = []
        self.read_calls: list[tuple] = []

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def read_registers(self, plc_address, register_type, count=1) -> PLCReadResult:
        return PLCReadResult(success=True, values=[0] * count)

    def read_block(self, start_address, register_type, count) -> PLCReadResult:
        self.read_calls.append((start_address, register_type, count))
        if self.verify_override is not None:
            values = list(self.verify_override)
        else:
            values = list(self.memory)
        values = values[:count] + [0] * max(0, count - len(values))
        return PLCReadResult(success=True, values=values[:count])

    def write_block(self, start_address, register_type, values) -> PLCWriteResult:
        self.write_calls.append((start_address, register_type, list(values)))
        if self.fail_write:
            return PLCWriteResult(success=False, error="simulated PLC reject")
        self.memory = list(values)
        return PLCWriteResult(success=True, register_address=start_address)

    def write_register(self, plc_address, value, register_type="HOLDING") -> PLCWriteResult:
        return PLCWriteResult(success=True)

    def write_coil_pulse(self, plc_address, on_ms=100, off_ms=100) -> PLCWriteResult:
        return PLCWriteResult(success=True)


@pytest.fixture
def driver():
    return FakeDriver()


@pytest.fixture
def mgr(db, driver):
    return PLCWriteManager(driver, db, MagicMock())


def audit_rows(db, block_id=1):
    return db.fetchall(
        "SELECT * FROM plc_write_log WHERE block_id = ? ORDER BY id", (block_id,)
    )


# ---------------------------------------------------------------------------
# Validation — synchronous rejections, nothing dispatched
# ---------------------------------------------------------------------------

class TestValidation:

    def _reject(self, mgr, block, values, user_id=1):
        failures: list[tuple] = []
        mgr.block_write_failed.connect(lambda *a: failures.append(a))
        dispatched = mgr.execute_block_write(block, values, user_id)
        assert dispatched is False
        assert failures, "expected block_write_failed"
        return failures[0][2]  # error text

    def test_discrete_block_rejected(self, mgr):
        reason = self._reject(mgr, make_block(register_type="DISCRETE"), [0] * 5)
        assert "read-only" in reason

    def test_input_block_rejected(self, mgr):
        reason = self._reject(mgr, make_block(register_type="INPUT"), [0] * 5)
        assert "read-only" in reason

    def test_access_read_only_rejected(self, mgr):
        reason = self._reject(mgr, make_block(access="READ_ONLY"), [1] * 5)
        assert "READ_ONLY" in reason

    def test_wrong_value_count_rejected(self, mgr):
        reason = self._reject(mgr, make_block(), [1, 2, 3])
        assert "Expected 5 values, got 3" in reason

    def test_non_integer_rejected(self, mgr):
        reason = self._reject(mgr, make_block(), [1, 2, 3, 4, "x"])
        assert "not an integer" in reason

    def test_word_out_of_range_rejected(self, mgr):
        reason = self._reject(mgr, make_block(), [1, 2, 3, 4, 70000])
        assert "out of range" in reason

    def test_coil_non_binary_rejected(self, mgr):
        reason = self._reject(
            mgr, make_block(register_type="COIL", count=3), [1, 2, 0]
        )
        assert "0 or 1" in reason

    def test_missing_start_address_rejected(self, mgr):
        blk = make_block()
        del blk["start_address"]
        reason = self._reject(mgr, blk, [1] * 5)
        assert "Invalid block definition" in reason

    def test_rejection_writes_no_audit_row(self, mgr, db):
        mgr.execute_block_write(make_block(access="READ_ONLY"), [1] * 5, 1)
        assert audit_rows(db) == []


# ---------------------------------------------------------------------------
# Dispatch, verify, audit
# ---------------------------------------------------------------------------

class TestBlockWriteExecution:

    def test_success_writes_verifies_and_audits(self, qtbot, mgr, driver, db, user_id, block_row):
        blk = block_row
        values = [10, 20, 30, 40, 50]

        with qtbot.waitSignal(mgr.block_write_success, timeout=5000) as blocker:
            assert mgr.execute_block_write(blk, values, user_id) is True

        block_id, name, count = blocker.args
        assert (block_id, name, count) == (blk["id"], "Write Block", 5)

        # Driver got FC16-style bulk write + read-back happened
        assert driver.write_calls == [(100, "HOLDING", values)]
        assert driver.read_calls == [(100, "HOLDING", 5)]

        rows = audit_rows(db, blk["id"])
        assert len(rows) == 1
        row = rows[0]
        assert row["block_id"] == blk["id"]
        assert row["register_id"] is None
        assert row["register_address"] == 100
        assert row["register_name"] == "Write Block"
        assert row["write_success"] == 1
        assert row["error_message"] is None
        assert row["operator_id"] == user_id
        assert row["write_reason"] == REASON_BLOCK_WRITE
        assert row["value_written"] == str(values)
        assert row["value_readback"] == str(values)  # verified echo

    def test_bool_values_normalized_to_ints(self, qtbot, mgr, driver, user_id, coil_row):
        with qtbot.waitSignal(mgr.block_write_success, timeout=5000):
            mgr.execute_block_write(coil_row, [True, False, True], user_id)
        assert driver.write_calls[-1] == (0, "COIL", [1, 0, 1])

    def test_verify_mismatch_emits_verify_failed(
        self, qtbot, mgr, driver, db, user_id, block_row
    ):
        driver.verify_override = [10, 20, 999, 40, 50]
        blk = block_row
        seen: list[tuple] = []
        mgr.verify_failed.connect(lambda *a: seen.append(a))

        with qtbot.waitSignal(mgr.block_write_success, timeout=5000):
            mgr.execute_block_write(blk, [10, 20, 30, 40, 50], user_id)

        assert (102, 30, 999) in seen
        # Write still audited as accepted, with readback recorded for audit
        row = audit_rows(db, blk["id"])[0]
        assert row["write_success"] == 1
        assert "999" in row["value_readback"]

    def test_plc_reject_audits_failure(self, qtbot, mgr, driver, db, user_id, block_row):
        driver.fail_write = True
        blk = block_row

        with qtbot.waitSignal(mgr.block_write_failed, timeout=5000) as blocker:
            mgr.execute_block_write(blk, [1, 2, 3, 4, 5], user_id)

        block_id, name, error = blocker.args
        assert block_id == blk["id"] and name == "Write Block"
        assert "simulated PLC reject" in error
        assert driver.read_calls == []  # no verify after failed write

        row = audit_rows(db, blk["id"])[0]
        assert row["write_success"] == 0
        assert "simulated PLC reject" in row["error_message"]
        assert row["value_readback"] is None

    def test_missing_driver_fails_and_audits(
        self, qtbot, db, user_id, block_row
    ):
        mgr = PLCWriteManager(None, db, MagicMock())
        with qtbot.waitSignal(mgr.block_write_failed, timeout=5000) as blocker:
            mgr.execute_block_write(block_row, [1, 2, 3, 4, 5], user_id)
        assert "No PLC driver" in blocker.args[2]
        row = audit_rows(db, block_row["id"])[0]
        assert row["write_success"] == 0

    def test_lock_released_allows_next_write(
        self, qtbot, mgr, driver, user_id, block_row
    ):
        blk = block_row
        with qtbot.waitSignal(mgr.block_write_success, timeout=5000):
            assert mgr.execute_block_write(blk, [1, 1, 1, 1, 1], user_id) is True
        with qtbot.waitSignal(mgr.block_write_success, timeout=5000):
            assert mgr.execute_block_write(blk, [2, 2, 2, 2, 2], user_id) is True
        assert len(driver.write_calls) == 2

    def test_busy_lock_rejects_with_plc_busy(self, qtbot, mgr, user_id):
        assert mgr._write_lock.acquire(blocking=False)
        busy: list[str] = []
        mgr.plc_busy.connect(busy.append)
        try:
            dispatched = mgr.execute_block_write(make_block(), [1] * 5, user_id)
            assert dispatched is False
            assert mgr._write_lock.locked()
        finally:
            mgr._write_lock.release()
        assert busy and "in progress" in busy[0]

    def test_single_register_write_shares_lock(self, qtbot, mgr, user_id):
        """A block write and a control write must never run concurrently."""
        acquired = mgr._write_lock.acquire(blocking=False)
        assert acquired
        try:
            # While block write lock is held, execute_control must go busy
            busy: list[str] = []
            mgr.plc_busy.connect(busy.append)
            ctrl = {
                "register_id": 1, "register_address": 10, "register_type": "HOLDING",
                "name": "Ctrl", "write_value": 1, "reset_after_ms": 0,
                "control_type": "CUSTOM",
            }
            mgr.execute_control(ctrl, user_id)
            assert busy, "execute_control should be busy while block write holds lock"
        finally:
            mgr._write_lock.release()


# ---------------------------------------------------------------------------
# Audit summary helper
# ---------------------------------------------------------------------------

class TestSummarize:

    def test_short_list_in_full(self):
        assert _summarize_values([1, 2, 3]) == "[1, 2, 3]"

    def test_long_list_truncated(self):
        text = _summarize_values(list(range(100)))
        assert "100 values total" in text
        assert len(text) < 300

    def test_empty_list(self):
        assert _summarize_values([]) == "[]"
