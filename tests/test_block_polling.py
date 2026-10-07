"""
Phase 3 — Register Block polling integration tests.

Covers:
    - BlockReading storage in PLCDataModel
    - ConnectionManager block polling (decode, signal, data model)
    - Stale-last-good behaviour on block read failure
    - comm_error emission for failed blocks
    - update_block_list / update_poll_list thread-safe swaps
    - AppState: block cache, refresh_blocks, refresh_poll_config,
      set_model pushing blocks to the ConnectionManager

Zero-regression focus: the no-blocks path must behave exactly as before
(readings-only, no blocks_updated emissions).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.plc.base_driver import PLCDriver, PLCReadResult, PLCWriteResult
from src.plc.connection_manager import ConnectionManager
from src.plc.data_model import PLCDataModel, BlockReading
from src.ui.app_state import AppState

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------

PROFILE = {
    "protocol": "MODBUS_TCP",
    "host": "127.0.0.1",
    "port": 502,
    "poll_interval_ms": 50,
    "max_retries": 5,
    "reconnect_delay_ms": 50,
}

HOLDING_BLOCK = {
    "block_id": 1,
    "name": "Tank Pressure",
    "group_name": "Tanks",
    "start_address": 100,
    "count": 5,
    "register_type": "HOLDING",
    "data_type": "INT16",
    "scale_factor": 0.1,
    "word_swap": 0,
    "decimal_places": 1,
    "unit": "bar",
    "is_active": 1,
}

COIL_BLOCK = {
    "block_id": 2,
    "name": "Valve Bank",
    "group_name": "Actuators",
    "start_address": 200,
    "count": 4,
    "register_type": "COIL",
    "data_type": "BOOL",
    "scale_factor": 1.0,
    "word_swap": 0,
    "decimal_places": 0,
    "unit": "",
    "is_active": 1,
}


class FakeDriver(PLCDriver):
    """In-memory driver with scripted block responses (no network)."""

    def __init__(self, block_values: list[int] | None = None) -> None:
        super().__init__("mitsubishi", "fake", 502)
        self.block_values: list[int] = list(block_values or [])
        self.fail_block = False
        self.block_calls = 0
        self.reg_calls = 0

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def read_registers(self, plc_address, register_type, count=1) -> PLCReadResult:
        self.reg_calls += 1
        return PLCReadResult(
            success=True, values=[0] * count,
            register_address=plc_address, count=count,
        )

    def read_block(self, start_address, register_type, count) -> PLCReadResult:
        self.block_calls += 1
        if self.fail_block:
            return PLCReadResult(success=False, error="simulated timeout")
        values = self.block_values[:count]
        if len(values) < count:
            values = values + [0] * (count - len(values))
        return PLCReadResult(
            success=True, values=values,
            register_address=start_address, count=count,
        )

    def write_register(self, plc_address, value, register_type="HOLDING") -> PLCWriteResult:
        return PLCWriteResult(success=True, register_address=plc_address, value_written=value)

    def write_coil_pulse(self, plc_address, on_ms=100, off_ms=100) -> PLCWriteResult:
        return PLCWriteResult(success=True, register_address=plc_address)

    def write_block(self, start_address, register_type, values) -> PLCWriteResult:
        return PLCWriteResult(success=True, register_address=start_address, value_written=list(values))


@pytest.fixture
def model():
    return PLCDataModel()


def make_manager(model, driver, blocks=None, registers=None):
    return ConnectionManager(
        dict(PROFILE),
        list(registers or []),
        None,
        {},
        model,
        driver,
        blocks_to_poll=list(blocks or []),
    )


# ---------------------------------------------------------------------------
# BlockReading storage
# ---------------------------------------------------------------------------

class TestBlockReadingStorage:

    def _reading(self) -> BlockReading:
        return BlockReading(
            block_id=1, name="B", start_address=100, register_type="HOLDING",
            count=3, raw_words=[1, 2, 3], elements=[0.1, 0.2, 0.3],
            read_success=True, error="", stale=False, timestamp=None,
        )

    def test_update_and_get(self, model):
        model.update_block_reading(1, self._reading())
        got = model.get_block_reading(1)
        assert got is not None
        assert got.raw_words == [1, 2, 3]

    def test_get_missing_returns_none(self, model):
        assert model.get_block_reading(99) is None

    def test_get_all_returns_copy(self, model):
        model.update_block_reading(1, self._reading())
        snapshot = model.get_all_block_readings()
        snapshot.clear()
        assert model.get_block_reading(1) is not None

    def test_reset_clears_blocks(self, model):
        model.update_block_reading(1, self._reading())
        model.reset()
        assert model.get_block_reading(1) is None
        assert model.get_all_block_readings() == {}


# ---------------------------------------------------------------------------
# Polling loop — block success path
# ---------------------------------------------------------------------------

class TestBlockPolling:

    def test_blocks_updated_emitted_and_decoded(self, qtbot, model):
        driver = FakeDriver(block_values=[100, 200, 300, 400, 500])
        mgr = make_manager(model, driver, blocks=[HOLDING_BLOCK])

        try:
            with qtbot.waitSignal(mgr.blocks_updated, timeout=10000) as blocker:
                mgr.start()
        finally:
            mgr.stop()

        payload = blocker.args[0]
        assert set(payload.keys()) == {1}
        br = payload[1]
        assert br.read_success and not br.stale
        assert br.raw_words == [100, 200, 300, 400, 500]
        # INT16 * scale_factor 0.1
        assert br.elements == pytest.approx([10.0, 20.0, 30.0, 40.0, 50.0])
        assert br.name == "Tank Pressure"

        stored = model.get_block_reading(1)
        assert stored is not None and stored.read_success
        assert driver.block_calls >= 1

    def test_coil_block_elements_are_floats(self, model):
        driver = FakeDriver(block_values=[1, 0, 1, 1])
        mgr = make_manager(model, driver, blocks=[COIL_BLOCK])

        reading = mgr._read_configured_block(COIL_BLOCK)
        assert reading is not None
        assert reading.read_success
        assert reading.raw_words == [1, 0, 1, 1]
        assert reading.elements == [1.0, 0.0, 1.0, 1.0]

    def test_float32_block_uses_stride_2(self, model):
        import struct
        block = dict(HOLDING_BLOCK, block_id=3, data_type="FLOAT32", count=4, scale_factor=1.0)
        hi, lo = struct.unpack(">HH", struct.pack(">f", 3.5))
        driver = FakeDriver(block_values=[hi, lo, hi, lo])
        mgr = make_manager(model, driver, blocks=[block])

        reading = mgr._read_configured_block(block)
        assert reading.elements == pytest.approx([3.5, 3.5])

    def test_no_blocks_emits_no_blocks_updated(self, qtbot, model):
        """Zero-regression: without blocks, only readings flow."""
        driver = FakeDriver()
        reg = {
            "register_id": 11, "display_name": "Temp", "library_name": "Temp",
            "register_address": 10, "register_type": "HOLDING",
            "data_type": "UINT16", "scale_factor": 1.0, "word_swap": 0,
            "decimal_places": 0, "unit": "",
        }
        mgr = make_manager(model, driver, blocks=[], registers=[reg])

        block_payloads: list[dict] = []
        mgr.blocks_updated.connect(block_payloads.append)

        try:
            with qtbot.waitSignal(mgr.readings_updated, timeout=10000):
                mgr.start()
        finally:
            mgr.stop()

        assert block_payloads == []
        assert driver.block_calls == 0


# ---------------------------------------------------------------------------
# Polling loop — block failure path
# ---------------------------------------------------------------------------

class TestBlockFailure:

    def test_failure_keeps_last_good_as_stale(self, qtbot, model):
        driver = FakeDriver(block_values=[1, 2, 3, 4, 5])
        mgr = make_manager(model, driver, blocks=[HOLDING_BLOCK])
        errors: list[str] = []
        mgr.comm_error.connect(errors.append)

        try:
            with qtbot.waitSignal(mgr.blocks_updated, timeout=10000):
                mgr.start()

            driver.fail_block = True
            qtbot.waitUntil(
                lambda: (r := model.get_block_reading(1)) is not None and r.stale,
                timeout=10000,
            )
        finally:
            mgr.stop()

        stale = model.get_block_reading(1)
        assert stale.read_success is False
        assert stale.stale is True
        assert stale.raw_words == [1, 2, 3, 4, 5]
        assert stale.elements == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])
        assert "simulated timeout" in stale.error
        assert errors, "comm_error should be emitted for failed block"

    def test_failure_without_history_returns_none(self, qtbot, model):
        driver = FakeDriver()
        driver.fail_block = True
        mgr = make_manager(model, driver, blocks=[HOLDING_BLOCK])
        errors: list[str] = []
        mgr.comm_error.connect(errors.append)

        try:
            with qtbot.waitSignal(mgr.comm_error, timeout=10000):
                mgr.start()
            # Let a couple more cycles run
            qtbot.wait(150)
        finally:
            mgr.stop()

        assert model.get_block_reading(1) is None
        assert any("Block 'Tank Pressure'" in e for e in errors)


# ---------------------------------------------------------------------------
# List updates (thread-safety surface)
# ---------------------------------------------------------------------------

class TestListUpdates:

    def test_update_block_list_swaps_targets(self, model):
        mgr = make_manager(model, FakeDriver(), blocks=[])
        mgr.update_block_list([COIL_BLOCK])
        assert mgr._blocks == [COIL_BLOCK]

        mgr.update_block_list([])
        assert mgr._blocks == []

    def test_update_poll_list_keeps_blocks(self, model):
        mgr = make_manager(model, FakeDriver(), blocks=[COIL_BLOCK])
        mgr.update_poll_list([], None, {})
        assert mgr._blocks == [COIL_BLOCK]
        assert mgr._registers == []


# ---------------------------------------------------------------------------
# AppState integration
# ---------------------------------------------------------------------------

class TestAppStateBlocks:

    def test_refresh_blocks_reads_repo_and_caches(self, monkeypatch):
        state = AppState.get_instance()
        fake_repo = MagicMock()
        fake_repo.get_poll_blocks.return_value = [HOLDING_BLOCK]
        monkeypatch.setattr(state, "block_repo", fake_repo)
        monkeypatch.setattr(state, "poll_blocks", [])

        got = state.refresh_blocks()
        assert got == [HOLDING_BLOCK]
        assert state.poll_blocks == [HOLDING_BLOCK]

    def test_refresh_blocks_without_repo_returns_empty(self, monkeypatch):
        state = AppState.get_instance()
        monkeypatch.setattr(state, "block_repo", None)
        monkeypatch.setattr(state, "poll_blocks", [HOLDING_BLOCK])

        got = state.refresh_blocks()
        assert got == []
        assert state.poll_blocks == []

    def test_refresh_poll_config_without_model_pushes_blocks(self, monkeypatch):
        state = AppState.get_instance()
        fake_repo = MagicMock()
        fake_repo.get_poll_blocks.return_value = [COIL_BLOCK]
        fake_conn = MagicMock()
        monkeypatch.setattr(state, "block_repo", fake_repo)
        monkeypatch.setattr(state, "connection_manager", fake_conn)
        monkeypatch.setattr(state, "current_model_id", None)
        monkeypatch.setattr(state, "poll_blocks", [])

        state.refresh_poll_config()

        fake_repo.get_poll_blocks.assert_called_once()
        fake_conn.update_block_list.assert_called_once_with([COIL_BLOCK])
        fake_conn.update_poll_list.assert_not_called()

    def test_refresh_poll_config_with_model_pushes_registers_and_blocks(self, monkeypatch):
        state = AppState.get_instance()
        fake_model_repo = MagicMock()
        fake_model_repo.get_model.return_value = {"id": 7, "name": "M7"}
        fake_map_repo = MagicMock()
        fake_map_repo.get_poll_registers.return_value = []
        fake_map_repo.get_dashboard_registers.return_value = []
        fake_io_repo = MagicMock()
        fake_io_repo.get_poll_registers.return_value = []
        fake_block_repo = MagicMock()
        fake_block_repo.get_poll_blocks.return_value = [HOLDING_BLOCK]
        fake_conn = MagicMock()

        monkeypatch.setattr(state, "model_repo", fake_model_repo)
        monkeypatch.setattr(state, "map_repo", fake_map_repo)
        monkeypatch.setattr(state, "io_repo", fake_io_repo)
        monkeypatch.setattr(state, "block_repo", fake_block_repo)
        monkeypatch.setattr(state, "connection_manager", fake_conn)
        monkeypatch.setattr(state, "current_model_id", 7)
        monkeypatch.setattr(state, "message_register", None)
        monkeypatch.setattr(state, "message_lookup", {})
        monkeypatch.setattr(state, "poll_blocks", [])

        state.refresh_poll_config()

        # Register list pushed via existing path (unchanged behaviour)
        fake_conn.update_poll_list.assert_called_once()
        # Block list pushed as an additive second call
        fake_conn.update_block_list.assert_called_once_with([HOLDING_BLOCK])

    def test_poll_blocks_property_roundtrip(self, monkeypatch):
        state = AppState.get_instance()
        monkeypatch.setattr(state, "poll_blocks", [HOLDING_BLOCK])
        assert state.poll_blocks == [HOLDING_BLOCK]
