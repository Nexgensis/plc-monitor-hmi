"""
src/plc/__init__.py — Universal PLC Monitor
Public API for the PLC driver package.

Import from here to get the full driver surface:
    from src.plc import PLCDriverFactory, PLCDriver
    from src.plc import PLCReadResult, PLCWriteResult
"""
from .base_driver import PLCDriver, PLCReadResult, PLCWriteResult
from .mitsubishi_driver import MitsubishiDriver
from .mitsubishi_rtu_driver import MitsubishiRTUDriver
from .delta_driver import DeltaDriver
from .delta_rtu_driver import DeltaRTUDriver
from .driver_factory import PLCDriverFactory
from .data_model import PLCDataModel, RegisterReading, PLCStatus
from .connection_manager import ConnectionManager
from .write_manager import PLCWriteManager

__all__ = [
    "PLCDriver",
    "PLCReadResult",
    "PLCWriteResult",
    "MitsubishiDriver",
    "MitsubishiRTUDriver",
    "DeltaDriver",
    "DeltaRTUDriver",
    "PLCDriverFactory",
    "PLCDataModel",
    "RegisterReading",
    "ParameterReading",
    "PLCStatus",
    "ConnectionManager",
    "PLCWriteManager",
]
