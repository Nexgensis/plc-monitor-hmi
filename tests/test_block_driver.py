"""
Phase 2 — bulk block driver tests: PLCDriver.read_block chunking and
MitsubishiDriver.write_block (FC16/FC0F), including an in-process
pymodbus server roundtrip.

Run: venv\\Scripts\\python.exe -m pytest tests/test_block_driver.py -q
"""
import socket
import threading
import time
from unittest.mock import MagicMock

import pytest

from src.plc.base_driver import PLCDriver
from src.plc.mitsubishi_driver import MitsubishiDriver
from src.plc.delta_driver import DeltaDriver
from src.plc.mitsubishi_rtu_driver import MitsubishiRTUDriver
from src.plc.delta_rtu_driver import DeltaRTUDriver
from src.utils.constants import (
    MODBUS_MAX_READ_REGS,
    MODBUS_MAX_READ_BITS,
    MODBUS_MAX_WRITE_REGS,
    MODBUS_MAX_WRITE_BITS,
)


# ----------------------------------------------------------------------
# Mock response helpers
# ----------------------------------------------------------------------
def _ok_regs(values):
    r = MagicMock()
    r.isError.return_value = False
    r.registers = list(values)
    return r


def _ok_bits(bits):
    r = MagicMock()
    r.isError.return_value = False
    r.bits = list(bits)
    return r


def _fail():
    r = MagicMock()
    r.isError.return_value = True
    return r


def _ok():
    r = MagicMock()
    r.isError.return_value = False
    return r


def _mock_driver(cls=MitsubishiDriver, **kwargs):
    driver = cls("127.0.0.1", 502, **kwargs)
    driver._client = MagicMock()
    return driver


def _hr_response(address, count, slave):
    return _ok_regs(range(address, address + count))


def _coil_response(address, count, slave):
    return _ok_bits([(address + i) % 2 for i in range(count)])


# ----------------------------------------------------------------------
# read_block — chunking
# ----------------------------------------------------------------------
class TestReadBlockChunking:
    def test_holding_101_is_single_request(self):
        d = _mock_driver()
        d._client.read_holding_registers.side_effect = _hr_response
        res = d.read_block(100, "HOLDING", 101)
        assert res.success
        assert len(res.values) == 101
        assert res.values == list(range(100, 201))
        d._client.read_holding_registers.assert_called_once_with(
            address=100, count=101, slave=1
        )

    def test_holding_300_chunks_at_125(self):
        d = _mock_driver()
        d._client.read_holding_registers.side_effect = _hr_response
        res = d.read_block(100, "HOLDING", 300)
        assert res.success
        assert len(res.values) == 300
        calls = d._client.read_holding_registers.call_args_list
        assert [c.kwargs["address"] for c in calls] == [100, 225, 350]
        assert [c.kwargs["count"] for c in calls] == [
            MODBUS_MAX_READ_REGS, MODBUS_MAX_READ_REGS, 50
        ]
        # each chunk is tracked as one quality request
        assert d.get_quality_stats()["total_requests"] == 3

    def test_holding_at_exact_chunk_limit_single_request(self):
        d = _mock_driver()
        d._client.read_holding_registers.side_effect = _hr_response
        res = d.read_block(0, "HOLDING", MODBUS_MAX_READ_REGS)
        assert res.success
        assert d._client.read_holding_registers.call_count == 1

    def test_coils_2000_single_request(self):
        d = _mock_driver()
        d._client.read_coils.side_effect = _coil_response
        res = d.read_block(0, "COIL", MODBUS_MAX_READ_BITS)
        assert res.success
        assert len(res.values) == 2000
        d._client.read_coils.assert_called_once_with(
            address=1, count=2000, slave=1
        )  # Mitsubishi M0 → coil 1

    def test_coils_2001_two_requests(self):
        d = _mock_driver()
        d._client.read_coils.side_effect = _coil_response
        res = d.read_block(0, "COIL", MODBUS_MAX_READ_BITS + 1)
        assert res.success
        assert len(res.values) == 2001
        calls = d._client.read_coils.call_args_list
        assert [c.kwargs["count"] for c in calls] == [2000, 1]

    def test_discrete_uses_bit_chunking(self):
        d = _mock_driver()
        d._client.read_discrete_inputs.side_effect = _coil_response
        res = d.read_block(0, "DISCRETE", 2001)
        assert res.success
        assert d._client.read_discrete_inputs.call_count == 2

    def test_input_registers_chunk_at_125(self):
        d = _mock_driver()
        d._client.read_input_registers.side_effect = _hr_response
        res = d.read_block(0, "INPUT", 126)
        assert res.success
        assert d._client.read_input_registers.call_count == 2


class TestReadBlockFailures:
    def test_partial_chunk_failure_returns_gathered_values(self):
        d = _mock_driver()
        d._client.read_holding_registers.side_effect = [
            _ok_regs(range(100, 225)),  # chunk 1: 125 values
            _fail(),                    # chunk 2 fails
        ]
        res = d.read_block(100, "HOLDING", 300)
        assert not res.success
        assert len(res.values) == 125
        assert "225" in res.error              # failing chunk address
        assert "125 of 300" in res.error       # partial progress
        assert d.get_quality_stats()["failed_requests"] == 1

    def test_zero_count_rejected_without_client_calls(self):
        d = _mock_driver()
        res = d.read_block(100, "HOLDING", 0)
        assert not res.success
        assert "must be > 0" in res.error
        d._client.read_holding_registers.assert_not_called()

    def test_negative_count_rejected(self):
        d = _mock_driver()
        assert not d.read_block(100, "COIL", -5).success

    def test_unknown_type_fails_cleanly(self):
        d = _mock_driver()
        res = d.read_block(100, "MEMORY", 5)
        assert not res.success
        assert "Unknown register_type" in res.error
        d._client.read_holding_registers.assert_not_called()

    def test_not_connected_fails_cleanly(self):
        d = MitsubishiDriver("127.0.0.1", 502)
        assert d._client is None
        res = d.read_block(100, "HOLDING", 10)
        assert not res.success
        assert "Not connected" in res.error


# ----------------------------------------------------------------------
# write_block — FC16 (HOLDING)
# ----------------------------------------------------------------------
class TestWriteBlockHolding:
    def test_single_chunk_101_words(self):
        d = _mock_driver()
        d._client.write_registers.return_value = _ok()
        values = [(i * 7) % 65536 for i in range(101)]
        res = d.write_block(100, "HOLDING", values)
        assert res.success
        assert res.value_written == values
        d._client.write_registers.assert_called_once_with(
            address=100, values=values, slave=1
        )
        assert d.is_connected()

    def test_chunks_at_123(self):
        d = _mock_driver()
        d._client.write_registers.return_value = _ok()
        values = list(range(300))
        res = d.write_block(100, "HOLDING", values)
        assert res.success
        calls = d._client.write_registers.call_args_list
        assert [c.kwargs["address"] for c in calls] == [100, 223, 346]
        assert [len(c.kwargs["values"]) for c in calls] == [123, 123, 54]
        assert d.get_quality_stats()["total_requests"] == 3

    def test_value_above_65535_rejected_before_send(self):
        d = _mock_driver()
        res = d.write_block(100, "HOLDING", [1, 70000])
        assert not res.success
        assert "out of range" in res.error
        d._client.write_registers.assert_not_called()

    def test_negative_value_rejected(self):
        d = _mock_driver()
        res = d.write_block(100, "HOLDING", [-1])
        assert not res.success
        d._client.write_registers.assert_not_called()

    def test_non_integer_rejected(self):
        d = _mock_driver()
        res = d.write_block(100, "HOLDING", ["abc"])
        assert not res.success
        assert "not an integer" in res.error
        d._client.write_registers.assert_not_called()

    def test_empty_list_rejected(self):
        d = _mock_driver()
        res = d.write_block(100, "HOLDING", [])
        assert not res.success
        assert "Empty" in res.error

    @pytest.mark.parametrize("rtype", ["DISCRETE", "INPUT", "MEMORY"])
    def test_read_only_types_rejected(self, rtype):
        d = _mock_driver()
        res = d.write_block(100, rtype, [1])
        assert not res.success
        assert "not writable" in res.error
        d._client.write_registers.assert_not_called()
        d._client.write_coils.assert_not_called()

    def test_mid_write_chunk_failure_reports_partial(self):
        d = _mock_driver()
        d._client.write_registers.side_effect = [_ok(), _fail()]
        res = d.write_block(100, "HOLDING", list(range(300)))
        assert not res.success
        assert "123 of 300" in res.error
        assert d._client.write_registers.call_count == 2
        assert not d.is_connected()
        assert d.get_quality_stats()["failed_requests"] == 1

    def test_client_exception_returned_as_failure(self):
        d = _mock_driver()
        d._client.write_registers.side_effect = ConnectionError("cable pulled")
        res = d.write_block(100, "HOLDING", [1, 2, 3])
        assert not res.success
        assert "cable pulled" in res.error
        assert not d.is_connected()

    def test_not_connected_fails_cleanly(self):
        d = MitsubishiDriver("127.0.0.1", 502)
        res = d.write_block(100, "HOLDING", [1])
        assert not res.success
        assert "Not connected" in res.error


# ----------------------------------------------------------------------
# write_block — FC0F (COIL)
# ----------------------------------------------------------------------
class TestWriteBlockCoils:
    def test_single_chunk_translates_mitsubishi_offset(self):
        d = _mock_driver()
        d._client.write_coils.return_value = _ok()
        values = [i % 2 for i in range(100)]
        res = d.write_block(0, "COIL", values)
        assert res.success
        assert res.value_written == values
        # M0 → Modbus coil 1
        d._client.write_coils.assert_called_once_with(
            address=1, values=[bool(v) for v in values], slave=1
        )

    def test_non_bit_value_rejected(self):
        d = _mock_driver()
        res = d.write_block(0, "COIL", [0, 1, 2])
        assert not res.success
        assert "expected 0 or 1" in res.error
        d._client.write_coils.assert_not_called()

    def test_bool_values_accepted(self):
        d = _mock_driver()
        d._client.write_coils.return_value = _ok()
        res = d.write_block(0, "COIL", [True, False, True])
        assert res.success
        assert res.value_written == [1, 0, 1]

    def test_chunks_at_1968(self):
        d = _mock_driver()
        d._client.write_coils.return_value = _ok()
        values = [1] * (MODBUS_MAX_WRITE_BITS + 10)
        res = d.write_block(0, "COIL", values)
        assert res.success
        calls = d._client.write_coils.call_args_list
        assert [len(c.kwargs["values"]) for c in calls] == [
            MODBUS_MAX_WRITE_BITS, 10
        ]


# ----------------------------------------------------------------------
# Brand translation & inheritance
# ----------------------------------------------------------------------
class TestBrandAndInheritance:
    def test_delta_coil_write_uses_2048_base(self):
        d = _mock_driver(cls=DeltaDriver)
        d._client.write_coils.return_value = _ok()
        res = d.write_block(10, "COIL", [1, 0, 1])
        assert res.success
        # Delta M10 → coil 2058
        d._client.write_coils.assert_called_once_with(
            address=2058, values=[True, False, True], slave=1
        )

    def test_delta_coil_read_uses_2048_base(self):
        d = _mock_driver(cls=DeltaDriver)
        d._client.read_coils.side_effect = _coil_response
        res = d.read_block(10, "COIL", 3)
        assert res.success
        d._client.read_coils.assert_called_once_with(
            address=2058, count=3, slave=1
        )

    @pytest.mark.parametrize("cls", [MitsubishiRTUDriver, DeltaRTUDriver])
    def test_rtu_drivers_inherit_write_block(self, cls):
        d = cls("COM99", 9600)
        # not connected → graceful failure, never raises
        res = d.write_block(0, "HOLDING", [1])
        assert not res.success
        assert "Not connected" in res.error
        res2 = d.read_block(0, "HOLDING", 5)
        assert not res2.success

    def test_write_block_is_part_of_driver_contract(self):
        assert issubclass(MitsubishiDriver, PLCDriver)
        # contract: PLCDriver declares write_block abstractly
        assert "write_block" in PLCDriver.__abstractmethods__


# ----------------------------------------------------------------------
# Live roundtrip against an in-process pymodbus TCP server
# ----------------------------------------------------------------------
SERVER_PORT = 15090


@pytest.fixture(scope="module")
def modbus_server():
    from pymodbus.datastore import (
        ModbusSequentialDataBlock,
        ModbusSlaveContext,
        ModbusServerContext,
    )
    from pymodbus.server import StartTcpServer

    hr = ModbusSequentialDataBlock(0, [0] * 65536)
    co = ModbusSequentialDataBlock(0, [False] * 65536)
    di = ModbusSequentialDataBlock(0, [False] * 4096)
    ir = ModbusSequentialDataBlock(0, [0] * 4096)
    slave = ModbusSlaveContext(di=di, co=co, hr=hr, ir=ir, zero_mode=True)
    context = ModbusServerContext(slaves=slave, single=True)

    thread = threading.Thread(
        target=StartTcpServer,
        kwargs={"context": context, "address": ("127.0.0.1", SERVER_PORT)},
        daemon=True,
    )
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", SERVER_PORT), 0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.skip("in-process Modbus server did not start")

    yield SERVER_PORT


@pytest.fixture
def connected_driver(modbus_server):
    d = MitsubishiDriver("127.0.0.1", modbus_server, timeout_ms=2000)
    assert d.connect(), "driver failed to connect to in-process server"
    yield d
    d.disconnect()


class TestRoundtrip:
    def test_holding_101_write_then_read(self, connected_driver):
        d = connected_driver
        values = [(i * 7) % 65536 for i in range(101)]
        w = d.write_block(100, "HOLDING", values)
        assert w.success, w.error
        r = d.read_block(100, "HOLDING", 101)
        assert r.success, r.error
        assert r.values == values

    def test_coils_100_write_then_read(self, connected_driver):
        d = connected_driver
        values = [i % 2 for i in range(100)]
        w = d.write_block(0, "COIL", values)
        assert w.success, w.error
        r = d.read_block(0, "COIL", 100)
        assert r.success, r.error
        assert r.values == values

    def test_multi_chunk_300_roundtrip(self, connected_driver):
        d = connected_driver
        values = [(i * 13) % 65536 for i in range(300)]
        w = d.write_block(500, "HOLDING", values)   # 3 write chunks
        assert w.success, w.error
        r = d.read_block(500, "HOLDING", 300)       # 3 read chunks
        assert r.success, r.error
        assert r.values == values
        # 1 probe in connect + 3 writes + 3 reads
        stats = d.get_quality_stats()
        assert stats["failed_requests"] == 0

    def test_single_write_still_works_alongside(self, connected_driver):
        d = connected_driver
        w = d.write_register(1000, "HOLDING", 4242)
        assert w.success, w.error
        r = d.read_registers(1000, "HOLDING", 1)
        assert r.success and r.values == [4242]
