"""
Dialog for adding or editing switch models.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTextEdit, QComboBox, QPushButton, QFormLayout,
    QGroupBox,
)
from PyQt6.QtCore import Qt


class ModelDialog(QDialog):
    """
    Modal dialog for creating or editing a PLC switch model.

    Parameters
    ----------
    mode : str
        ``"add"`` or ``"edit"``.
    model_data : dict, optional
        Existing model dict (required when *mode* == ``"edit"``).
    existing_models : list[dict], optional
        List of all models — enables the "Copy parameters from" combo
        (only shown in *add* mode).
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        mode: str = "add",
        model_data: Optional[Dict[str, Any]] = None,
        existing_models: Optional[List[Dict[str, Any]]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._model_data = model_data or {}
        self._existing_models = existing_models or []
        self.result_data: Dict[str, Any] = {}

        self.setWindowTitle("Add Model" if mode == "add" else "Edit Model")
        self.setMinimumWidth(420)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._build_ui()
        self._populate_fields()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        form_group = QGroupBox("Model Details")
        form = QFormLayout(form_group)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Switch Type A")
        form.addRow("Name *:", self.name_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Optional description")
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self.desc_edit)

        self.model_no_edit = QLineEdit()
        self.model_no_edit.setPlaceholderText("e.g. SW-A-100")
        form.addRow("Model Number:", self.model_no_edit)

        root.addWidget(form_group)

        # Copy-from combo (add mode only, when existing models provided)
        self._copy_group = QGroupBox("Copy Parameters From (optional)")
        copy_layout = QFormLayout(self._copy_group)
        self.copy_combo = QComboBox()
        self.copy_combo.addItem("— None —", None)
        for m in self._existing_models:
            self.copy_combo.addItem(m.get("name", f"Model #{m.get('id')}"), m.get("id"))
        copy_layout.addRow("Source Model:", self.copy_combo)
        root.addWidget(self._copy_group)
        self._copy_group.setVisible(self._mode == "add" and len(self._existing_models) > 0)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save" if self._mode == "add" else "Update")
        save_btn.setObjectName("btn_primary")
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    # ── Populate existing data (edit mode) ───────────────────────────

    def _populate_fields(self) -> None:
        if self._mode == "edit" and self._model_data:
            self.name_edit.setText(self._model_data.get("name", ""))
            self.desc_edit.setPlainText(self._model_data.get("description", ""))
            self.model_no_edit.setText(self._model_data.get("model_number", ""))

    # ── Save ─────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            return

        self.result_data = {
            "name": name,
            "description": self.desc_edit.toPlainText().strip(),
            "model_number": self.model_no_edit.text().strip(),
            "copy_from_model_id": self.copy_combo.currentData(),
        }
        self.accept()
