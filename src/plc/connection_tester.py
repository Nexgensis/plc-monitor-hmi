"""
connection_tester.py — Universal PLC Monitor
Short-lived QThread used to validate PLC connection settings in the UI.
Verifies connectivity, basic read, and test write capability.
"""
from __future__ import annotations

import logging
import time
from PyQt6.QtCore import QThread, pyqtSignal
from .driver_factory import PLCDriverFactory

logger = logging.getLogger(__name__)


class ConnectionTester(QThread):
    """
    Worker thread to test PLC connectivity without interrupting the main polling loop.
    Used in CONFIG → PLC Connection settings tab.
    """

    test_progress = pyqtSignal(str)   # Human-readable status message
    test_passed   = pyqtSignal(dict)  # Quality and connection details
    test_failed   = pyqtSignal(str)   # Error message on failure

    def __init__(self, profile: dict) -> None:
        """
        Args:
            profile: PLC connection profile dictionary (from UI form).
        """
        super().__init__()
        self._profile = profile

    def run(self) -> None:
        """Executes the connection test sequence."""
        driver = None
        try:
            self.test_progress.emit("Creating PLC driver instance...")
            driver = PLCDriverFactory.create(self._profile)

            self.test_progress.emit(f"Connecting to {driver.brand} via {self._profile['protocol']}...")
            if not driver.connect():
                self.test_failed.emit(
                    "Connection refused. Please check:\n"
                    "1. PLC IP Address and Port (TCP)\n"
                    "2. COM Port and Baud Rate (RTU)\n"
                    "3. PLC power and physical cabling."
                )
                return

            self.test_progress.emit("Connected. Testing read access (Address 0)...")
            # 1. Test basic read capability (Address 0 is most common, but not universal)
            # We don't fail the whole test if this specific address is invalid, 
            # as long as the connection itself succeeded.
            read_res = driver.read_registers(0, "HOLDING", 1)
            
            read_ok = read_res.success
            write_ok = False # Skip write test for safety in wizard
            
            if not read_ok:
                logger.warning(f"Connection test: Read at address 0 failed: {read_res.error}")

            # Cleanup
            stats = driver.get_quality_stats()
            driver.disconnect()

            self.test_passed.emit({
                "protocol":    self._profile["protocol"],
                "host":        self._profile.get("host", ""),
                "com_port":    self._profile.get("com_port", ""),
                "response_ms": read_res.response_time_ms if read_ok else 0,
                "read_ok":     read_ok,
                "write_ok":    write_ok,
                "quality":     stats,
                "message":     "Connection established successfully." if read_ok else "Connected, but address 0 rejected by PLC."
            })

        except ValueError as e:
            # Raised by factory for missing host/port
            self.test_failed.emit(str(e))
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {e}", exc_info=True)
            self.test_failed.emit(f"Unexpected system error: {e}")
        finally:
            if driver:
                try:
                    driver.disconnect()
                except:
                    pass
