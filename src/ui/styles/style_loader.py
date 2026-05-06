import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

class StyleLoader:
    """Utility class to load external stylesheets and provide inline styles."""

    @staticmethod
    def load(app: QApplication) -> None:
        """
        Reads app_style.qss from the same directory and applies it to the QApplication.
        """
        try:
            qss_path = Path(__file__).parent / "app_style.qss"
            if qss_path.exists():
                content = qss_path.read_text(encoding="utf-8")
                app.setStyleSheet(content)
                logger.info(f"Stylesheet loaded ({len(content)} chars)")
            else:
                logger.warning(f"Stylesheet not found at {qss_path}")
        except Exception as e:
            logger.warning(f"Failed to load stylesheet: {e}")

    @staticmethod
    def get_result_style(result: str) -> str:
        """
        Returns inline style string for result labels.
        result: PASS|FAIL|BYPASS|PENDING|RUNNING
        """
        styles = {
            "PASS":    "background:#1a6b3a;color:white;border-radius:4px;padding:3px 10px;",
            "FAIL":    "background:#c0392b;color:white;border-radius:4px;padding:3px 10px;",
            "BYPASS":  "background:#6c757d;color:white;border-radius:4px;padding:3px 10px;",
            "PENDING": "background:#d0d8e8;color:#1a1a2e;border-radius:4px;padding:3px 10px;",
            "RUNNING": "background:#d4890a;color:white;border-radius:4px;padding:3px 10px;",
        }
        return styles.get(result.upper(), "")

    @staticmethod
    def get_plc_status_style(connected: bool) -> str:
        """
        Inline style for PLC status indicator label.
        """
        if connected:
            return "background:#1a6b3a;color:white;padding:4px 12px;border-radius:4px;"
        else:
            return "background:#c0392b;color:white;padding:4px 12px;border-radius:4px;"
