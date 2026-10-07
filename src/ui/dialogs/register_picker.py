"""
register_picker.py — Universal PLC Monitor
Modal dialog to pick registers from the library.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QListWidget, QListWidgetItem, QPushButton)
from PyQt6.QtCore import Qt

from src.utils.debounce import DebouncedSignal


class RegisterPicker(QDialog):
    def __init__(self, parent, registers: list[dict], already_mapped_ids: set[int]):
        super().__init__(parent)
        self.setWindowTitle("Select Register")
        self.setFixedSize(400, 500)
        self.selected_register = None
        self._all_regs = registers
        self._mapped_ids = already_mapped_ids

        self._search_debounce = DebouncedSignal(150, self)
        self._search_debounce.triggered.connect(lambda: self._populate(self.search_input.text()))

        self._init_ui()
        self._populate("")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search registers...")
        self.search_input.textChanged.connect(lambda: self._search_debounce.emit())
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_accept)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add to Model")
        self.add_btn.setObjectName("btn_success")
        self.add_btn.clicked.connect(self._on_accept)
        self.add_btn.setEnabled(False)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.add_btn)
        layout.addLayout(btn_row)

        self.list_widget.currentRowChanged.connect(lambda r: self.add_btn.setEnabled(r >= 0))

    def _populate(self, text: str):
        self.list_widget.clear()
        text = text.lower()
        
        for reg in self._all_regs:
            if text in reg["name"].lower() or text in str(reg["register_address"]):
                item = QListWidgetItem(f"{reg['name']} (D{reg['register_address']})")
                item.setData(Qt.ItemDataRole.UserRole, reg)
                
                if reg["id"] in self._mapped_ids:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setText(item.text() + " [Already Mapped]")
                
                self.list_widget.addItem(item)

    def _on_accept(self):
        item = self.list_widget.currentItem()
        if item and (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self.selected_register = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    @staticmethod
    def pick(parent, registers: list[dict], already_mapped_ids: set[int]) -> dict | None:
        dlg = RegisterPicker(parent, registers, already_mapped_ids)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_register
        return None
