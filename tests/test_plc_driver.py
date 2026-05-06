"""
Unit tests for PLC drivers, address conversion, and data type validators.
Uses mock objects for pymodbus clients to test logic without hardware.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.utils.validators import (
    compute_modbus_address, 
    convert_raw_to_value, 
    get_register_count
)
from src.plc.driver_factory import PLCDriverFactory
from src.plc.mitsubishi_driver import MitsubishiDriver
from src.plc.delta_driver import DeltaDriver
from src.plc.connection_tester import ConnectionTester


class TestAddressConversion:
    """Test compute_modbus_address() logic for different brands and types."""
    
    def test_holding_same_for_both_brands(self):
        # D-registers are typically mapped 1:1 to Modbus 4x addresses
        assert compute_modbus_address(100, "HOLDING", "mitsubishi") == 100
        assert compute_modbus_address(100, "HOLDING", "delta") == 100

    def test_coil_mitsubishi_m10(self):
        # Mitsubishi M0 = 1, so M10 = 11
        assert compute_modbus_address(10, "COIL", "mitsubishi") == 11

    def test_coil_delta_m10(self):
        # Delta M0 = 2049, so M10 = 2059
        assert compute_modbus_address(10, "COIL", "delta") == 2059

    def test_discrete_mitsubishi_x0(self):
        # Mitsubishi X0 = 0x400 (1024)
        assert compute_modbus_address(0, "DISCRETE", "mitsubishi") == 1024

    def test_discrete_delta_x0(self):
        # Delta X0 = 1024
        assert compute_modbus_address(0, "DISCRETE", "delta") == 1024


class TestDataTypeConversion:
    """Test convert_raw_to_value() for engineering unit conversion."""

    def test_bool_true(self):
        assert convert_raw_to_value([1], "BOOL", 1.0) == 1.0
        assert convert_raw_to_value([0], "BOOL", 1.0) == 0.0

    def test_int16_negative(self):
        # 0xFD48 is -696 in signed 16-bit
        assert convert_raw_to_value([0xFD48], "INT16", 1.0) == -696.0

    def test_uint16(self):
        assert convert_raw_to_value([3456], "UINT16", 0.01) == pytest.approx(34.56)

    def test_float32_normal_order(self):
        # Example: 12.5 in float32 is 0x41480000
        # raw_words = [0x4148, 0x0000]
        assert convert_raw_to_value([0x4148, 0x0000], "FLOAT32", 1.0) == 12.5

    def test_float32_word_swap(self):
        # raw_words = [0x0000, 0x4148] with swap=True should be 12.5
        assert convert_raw_to_value([0x0000, 0x4148], "FLOAT32", 1.0, word_swap=True) == 12.5

    def test_bcd16(self):
        # 0x3456 BCD should be interpreted as integer 3456
        assert convert_raw_to_value([0x3456], "BCD16", 1.0) == 3456.0

    def test_int32_two_registers(self):
        # 0x00010000 = 65536
        assert convert_raw_to_value([0x0001, 0x0000], "INT32", 1.0) == 65536.0

    def test_register_count_float32_is_2(self):
        assert get_register_count("FLOAT32") == 2
        assert get_register_count("INT16") == 1


class TestMitsubishiDriver:
    """Test core driver logic using mocked pymodbus client."""

    def test_raises_if_host_empty(self):
        with pytest.raises(ValueError):
            MitsubishiDriver(host="", port=502)

    @patch('src.plc.mitsubishi_driver.ModbusTcpClient')
    def test_connect_success(self, MockClient):
        client = MockClient.return_value
        client.connect.return_value = True
        # Mock the probe read
        client.read_holding_registers.return_value.isError.return_value = False
        
        driver = MitsubishiDriver("127.0.0.1", 502)
        assert driver.connect() is True

    @patch('src.plc.mitsubishi_driver.ModbusTcpClient')
    def test_read_holding_calls_correct_pymodbus_fn(self, MockClient):
        client = MockClient.return_value
        driver = MitsubishiDriver("127.0.0.1", 502)
        driver._client = client
        
        driver.read_registers(100, "HOLDING", 1)
        client.read_holding_registers.assert_called_once_with(
            address=100, count=1, slave=1
        )

    @patch('src.plc.mitsubishi_driver.ModbusTcpClient')
    def test_batch_read_single_request(self, MockClient):
        client = MockClient.return_value
        driver = MitsubishiDriver("127.0.0.1", 502)
        driver._client = client
        
        # Batch read [100, 101, 102]
        # min=100, max=102, span=3
        driver.read_batch_by_type([100, 101, 102], "HOLDING")
        client.read_holding_registers.assert_called_once_with(
            address=100, count=3, slave=1
        )


class TestDriverFactory:
    """Test instantiation logic for various profiles."""

    def test_creates_mitsubishi_tcp(self):
        profile = {"brand": "mitsubishi", "protocol": "TCP", "host": "1.1.1.1"}
        driver = PLCDriverFactory.create(profile)
        assert isinstance(driver, MitsubishiDriver)
        assert driver.brand == "mitsubishi"

    def test_creates_delta_tcp(self):
        profile = {"brand": "delta", "protocol": "TCP", "host": "1.1.1.1"}
        driver = PLCDriverFactory.create(profile)
        assert isinstance(driver, DeltaDriver)
        assert driver.brand == "delta"

    def test_raises_if_tcp_host_empty(self):
        profile = {"brand": "mitsubishi", "protocol": "TCP", "host": ""}
        with pytest.raises(ValueError):
            PLCDriverFactory.create(profile)

    def test_creates_generic_as_mitsubishi(self):
        profile = {"brand": "generic", "protocol": "TCP", "host": "1.1.1.1"}
        driver = PLCDriverFactory.create(profile)
        assert isinstance(driver, MitsubishiDriver)


class TestConnectionTester:
    """Test the QThread that validates settings."""

    @patch('src.plc.connection_tester.PLCDriverFactory.create')
    def test_emits_failed_if_driver_creation_fails(self, mock_factory_create):
        mock_factory_create.side_effect = ValueError("Missing IP")
        
        tester = ConnectionTester({"protocol": "TCP"})
        
        # We need a spy or mock for the signals
        tester.test_failed = MagicMock()
        tester.run()
        
        tester.test_failed.emit.assert_called_with("Missing IP")
