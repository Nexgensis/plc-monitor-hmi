"""
ui/components/plc_tag_editor.py
Mapping panel linking logical model signal variables mechanically to Modbus TCP register addresses uniquely.
"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QSpinBox, 
                             QComboBox, QCheckBox, QHeaderView, QGroupBox, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QThread

from database.model_repo import ModelRepository
from database.db_manager import Database
from core.constants import REG_DISCRETE, REG_COIL, REG_INPUT, REG_HOLDING
from plc.plc_driver import PLCDriver

logger = logging.getLogger(__name__)


class ConnectionTestThread(QThread):
    """Background worker securing Main Thread isolation while Modbus driver probes hardware asynchronously."""
    result = pyqtSignal(bool, str)
    def __init__(self, host: str, port: int, slave_id: int, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.slave_id = slave_id
        
    def run(self):
        try:
            driver = PLCDriver(self.host, self.port, self.slave_id)
            if driver.connect():
                driver.disconnect()
                self.result.emit(True, "Connected — heartbeat successful")
            else:
                self.result.emit(False, "Failed — Connection refused")
        except Exception as e:
            self.result.emit(False, f"Failed — {str(e)}")


class PLCTagEditor(QWidget):
    tags_saved = pyqtSignal(int)
    
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._model_repo = ModelRepository(db)
        self._current_model_id = None
        
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_info = QLabel("Map abstracted logic arrays definitively across fixed logical register nodes.")
        lbl_info.setStyleSheet("color: #5a6a8a; font-style: italic;")
        layout.addWidget(lbl_info)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Signal Name", "Register Addr", "Reg Type", "Data Type", 
            "Scale Factor", "Unit", "Test Addr", "Enabled"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.table, stretch=1)
        
        # Connection Test Section
        self.group_test = QGroupBox("Test PLC Connection:")
        test_layout = QHBoxLayout(self.group_test)
        
        self.edit_host = QLineEdit("127.0.0.1")
        self.edit_host.setFixedWidth(120)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(0, 65535)
        self.spin_port.setValue(5020)
        self.spin_port.setFixedWidth(90)
        
        self.spin_slave = QSpinBox()
        self.spin_slave.setRange(1, 247)
        self.spin_slave.setValue(1)
        self.spin_slave.setFixedWidth(60)
        
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.setObjectName("btn_secondary")
        self.btn_test.clicked.connect(self._on_test_connection_clicked)
        
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setStyleSheet("font-weight: bold;")
        self.lbl_test_result.hide()
        
        test_layout.addWidget(QLabel("Host/IP:"))
        test_layout.addWidget(self.edit_host)
        test_layout.addWidget(QLabel("Port:"))
        test_layout.addWidget(self.spin_port)
        test_layout.addWidget(QLabel("Slave:"))
        test_layout.addWidget(self.spin_slave)
        test_layout.addWidget(self.btn_test)
        test_layout.addWidget(self.lbl_test_result)
        test_layout.addStretch()
        
        layout.addWidget(self.group_test)
        
        # Action Bar
        action_layout = QHBoxLayout()
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_save = QPushButton("Save Tag Config")
        self.btn_save.setObjectName("btn_success")
        
        self.btn_save.clicked.connect(self.save_tags)
        
        self.lbl_status = QLabel("")
        self.lbl_status.hide()
        
        action_layout.addWidget(self.btn_reset)
        action_layout.addStretch()
        action_layout.addWidget(self.lbl_status)
        action_layout.addWidget(self.btn_save)
        
        layout.addLayout(action_layout)

    def load_model(self, model_id: int) -> None:
        self._current_model_id = model_id
        if not model_id:
            self.table.setRowCount(0)
            return
            
        full = self._model_repo.get_full_model_config(model_id)
        signals = full.get("signals", [])
        tags = full.get("plc_tags", [])
        
        # Build lookup internally
        tag_lookup = {t["tag_name"]: t for t in tags}
        
        self.table.setRowCount(len(signals))
        for r, sig in enumerate(signals):
            n = sig["signal_name"]
            t_data = tag_lookup.get(n, {})
            
            # Name
            item_n = QTableWidgetItem(n)
            item_n.setFlags(item_n.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item_n)
            
            # Reg Addr
            sp_reg = QSpinBox()
            sp_reg.setRange(0, 65535)
            sp_reg.setValue(t_data.get("register_address", 40001))
            self.table.setCellWidget(r, 1, sp_reg)
            
            # Reg Type
            cmb_type = QComboBox()
            cmb_type.addItems([REG_HOLDING, REG_INPUT, REG_COIL, REG_DISCRETE])
            type_val = t_data.get("register_type", REG_HOLDING)
            cmb_type.setCurrentText(type_val)
            self.table.setCellWidget(r, 2, cmb_type)
            
            # Data Type
            cmb_data = QComboBox()
            cmb_data.addItems(["INT16", "UINT16", "FLOAT32", "BOOL"])
            data_val = t_data.get("data_type", "UINT16")
            cmb_data.setCurrentText(data_val)
            self.table.setCellWidget(r, 3, cmb_data)
            
            # Scale Factor
            le_scale = QLineEdit(str(t_data.get("scale_factor", 1.0)))
            self.table.setCellWidget(r, 4, le_scale)
            
            # Unit
            le_unit = QLineEdit(t_data.get("unit", "mV"))
            self.table.setCellWidget(r, 5, le_unit)
            
            # Test Addr (unused strictly in logic constraints thus mock)
            item_ta = QTableWidgetItem("0")
            self.table.setItem(r, 6, item_ta)
            
            # Enabled
            chk = QCheckBox()
            chk.setChecked(sig.get("enabled", True))
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setContentsMargins(0,0,0,0)
            h.addWidget(chk)
            self.table.setCellWidget(r, 7, wrap)

    def save_tags(self) -> bool:
        if not self._current_model_id:
            return False
            
        new_tags = []
        for r in range(self.table.rowCount()):
            n = self.table.item(r, 0).text()
            sp: QSpinBox = self.table.cellWidget(r, 1)
            cmb_t: QComboBox = self.table.cellWidget(r, 2)
            cmb_d: QComboBox = self.table.cellWidget(r, 3)
            le_s: QLineEdit = self.table.cellWidget(r, 4)
            le_u: QLineEdit = self.table.cellWidget(r, 5)
            
            addr = sp.value()
            if addr <= 0:
                self._show_status("Invalid Register Addr. Must be > 0.", False)
                return False
                
            try:
                sc = float(le_s.text())
            except ValueError:
                self._show_status("Scale Factor must be numerical.", False)
                return False
                
            new_tags.append({
                "tag_name": n,
                "register_address": addr,
                "register_type": cmb_t.currentText(),
                "data_type": cmb_d.currentText(),
                "scale_factor": sc,
                "unit": le_u.text().strip()
            })
            
        self._model_repo.set_plc_tags(self._current_model_id, new_tags)
        self.tags_saved.emit(self._current_model_id)
        self._show_status("Tag Config Saved Successfully", True)
        return True

    def _show_status(self, msg: str, success: bool) -> None:
        c = "#2ecc71" if success else "#c0392b"
        self.lbl_status.setStyleSheet(f"color: {c}; font-weight: bold;")
        self.lbl_status.setText(msg)
        self.lbl_status.show()

    def _on_test_connection_clicked(self) -> None:
        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Testing...")
        self.lbl_test_result.setStyleSheet("color: #f39c12; font-weight: bold;")
        self.lbl_test_result.show()
        
        self.thread = ConnectionTestThread(
            self.edit_host.text(), 
            self.spin_port.value(),
            self.spin_slave.value()
        )
        self.thread.result.connect(self._on_test_complete)
        self.thread.start()

    def _on_test_complete(self, success: bool, msg: str) -> None:
        self.btn_test.setEnabled(True)
        c = "#2ecc71" if success else "#c0392b"
        self.lbl_test_result.setStyleSheet(f"color: {c}; font-weight: bold;")
        self.lbl_test_result.setText(msg)

    def get_register_map(self) -> dict:
        return {}  # Extracted dynamically during connection manager runtime loops
