# src/ui/settings_window.py
"""
SettingsWindow — Admin-only three-panel settings dialog.

Layout:
  LEFT  (220px)  — Model list + CRUD buttons + "Push to PLC"
  CENTRE (flex)  — 5-tab editor (Params, Registers, Limits, Block, Connection)
  RIGHT (240px)  — PLCLivePanel (live register readback + write log)
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout,
    QFrame, QLabel, QPushButton,
    QListWidget, QListWidgetItem,
    QTabWidget, QWidget, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent

from src.ui.app_state import AppState
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.ui.dialogs.model_dialog import ModelDialog
from src.ui.components.param_editor import ParamEditor
from src.ui.components.register_mapper import RegisterMapper
from src.ui.components.limits_editor import LimitsEditor
from src.ui.components.plc_block_editor import PLCBlockEditor
from src.ui.components.plc_config_panel import PLCConfigPanel
from src.ui.components.plc_live_panel import PLCLivePanel

logger = logging.getLogger(__name__)


class SettingsWindow(QDialog):
    """
    Admin-only settings dialog.

    Opens from LoginWindow as a modal window (ApplicationModal).
    Fixed size 1200 × 750, centred on parent.
    """

    def __init__(self, app_state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._current_model_id: Optional[int] = None
        self._dirty: bool = False
        self._push_worker = None

        self.setWindowTitle("Settings — PLC Monitor")
        self.setFixedSize(1200, 750)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )

        self._setup_ui()
        self._refresh_model_list()

        # Pre-select the currently active model if one is set
        active_id = self._app_state.current_model_id
        if active_id:
            self._select_model_by_id(active_id)

    # ==================================================================
    # UI Construction
    # ==================================================================

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_left_panel())
        root.addWidget(self._build_centre_panel(), stretch=1)
        root.addWidget(self._build_right_panel())

    # ── LEFT: model list ──────────────────────────────────────────────

    def _build_left_panel(self) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(220)
        frame.setStyleSheet(
            "QFrame { background: #ffffff; border-right: 1px solid #d0d8e8; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        hdr = QLabel("Models")
        hdr.setStyleSheet("color: #1e2d4a; font-size: 14px; font-weight: 700;")
        layout.addWidget(hdr)

        self.btn_add_model = QPushButton("+ Add Model")
        self.btn_add_model.setObjectName("btn_success")
        self.btn_add_model.clicked.connect(self._on_add_model)
        layout.addWidget(self.btn_add_model)

        self.model_list = QListWidget()
        self.model_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self.model_list.setEditTriggers(
            QListWidget.EditTrigger.NoEditTriggers
        )
        self.model_list.currentItemChanged.connect(self._on_model_selected)
        layout.addWidget(self.model_list, stretch=1)

        # Edit / Delete row
        ed_row = QHBoxLayout()
        self.btn_edit_model = QPushButton("Edit")
        self.btn_edit_model.setStyleSheet(
            "background: #1e2d4a; color: white;"
        )
        self.btn_edit_model.clicked.connect(self._on_edit_model)

        self.btn_delete_model = QPushButton("Delete")
        self.btn_delete_model.setObjectName("btn_danger")
        self.btn_delete_model.clicked.connect(self._on_delete_model)

        ed_row.addWidget(self.btn_edit_model)
        ed_row.addWidget(self.btn_delete_model)
        layout.addLayout(ed_row)

        # Divider
        layout.addWidget(self._make_divider())

        # Push to PLC
        self.btn_push = QPushButton("▶  Push to PLC")
        self.btn_push.setObjectName("btn_success")
        self.btn_push.clicked.connect(self._on_push_to_plc)
        layout.addWidget(self.btn_push)

        self.push_status_lbl = QLabel("Never pushed")
        self.push_status_lbl.setStyleSheet(
            "color: #6c757d; font-size: 11px;"
        )
        self.push_status_lbl.setWordWrap(True)
        layout.addWidget(self.push_status_lbl)

        layout.addWidget(self._make_divider())

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.clicked.connect(self._on_close_requested)
        layout.addWidget(self.btn_close)

        return frame

    # ── CENTRE: tab editor ────────────────────────────────────────────

    def _build_centre_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.centre_tabs = QTabWidget()
        self.centre_tabs.setDocumentMode(True)

        # Tab 0 — Parameters
        self.param_editor = ParamEditor(self._app_state)
        self.param_editor.params_saved.connect(self._on_params_saved)
        tab0 = self._wrap_tab(self.param_editor)
        self.centre_tabs.addTab(tab0, "Parameters")

        # Tab 1 — Register Mapping
        self.register_mapper = RegisterMapper(self._app_state)
        self.register_mapper.registers_saved.connect(self._on_registers_saved)
        tab1 = self._wrap_tab(self.register_mapper)
        self.centre_tabs.addTab(tab1, "Register Mapping")

        # Tab 2 — Limit Values
        self.limits_editor = LimitsEditor(self._app_state)
        self.limits_editor.limits_saved.connect(self._on_limits_saved)
        tab2 = self._wrap_tab(self.limits_editor)
        self.centre_tabs.addTab(tab2, "Limit Values")

        # Tab 3 — Model Block
        self.block_editor = PLCBlockEditor(self._app_state)
        tab3 = self._wrap_tab(self.block_editor)
        self.centre_tabs.addTab(tab3, "Model Block")

        # Tab 4 — Connection
        self.config_panel = PLCConfigPanel(self._app_state)
        tab4 = self._wrap_tab(self.config_panel)
        self.centre_tabs.addTab(tab4, "Connection")

        layout.addWidget(self.centre_tabs)
        return container

    def _wrap_tab(self, widget: QWidget) -> QWidget:
        """Add standard padding around a tab's content widget."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)
        layout.addWidget(widget)
        return container

    # ── RIGHT: live panel ─────────────────────────────────────────────

    def _build_right_panel(self) -> PLCLivePanel:
        self.plc_live_panel = PLCLivePanel(self._app_state)
        return self.plc_live_panel

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_divider(self) -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet("background: #d0d8e8; max-height: 1px; border: none;")
        return d

    # ==================================================================
    # Model list management
    # ==================================================================

    def _refresh_model_list(self) -> None:
        models = self._app_state.model_repo.get_all_models()
        self.model_list.blockSignals(True)
        self.model_list.clear()

        status_dot = {
            "success": "✓",
            "failed":  "✗",
            "never":   "○",
            "pending": "◌",
        }
        for m in models:
            dot  = status_dot.get(m.get("push_status", "never"), "○")
            item = QListWidgetItem(f"{dot}  {m['name']}")
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.model_list.addItem(item)

        self.model_list.blockSignals(False)

    def _select_model_by_id(self, model_id: int) -> None:
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == model_id:
                self.model_list.setCurrentItem(item)
                return

    def _clear_all_editors(self) -> None:
        """Reset all tab editors when no model is selected."""
        self.centre_tabs.setEnabled(False)
        self.push_status_lbl.setText("No model selected")
        self.plc_live_panel.update_plc_status(
            self._app_state.is_plc_connected
        )

    def _update_push_status(self, model: dict) -> None:
        ps = model.get("push_status", "never")
        ts = model.get("last_pushed_at") or ""
        ts_short = ts[11:19] if len(ts) >= 19 else ts
        labels = {
            "success": f"✓  Pushed {ts_short}",
            "failed":  f"✗  Push failed {ts_short}",
            "never":   "○  Never pushed",
            "pending": "◌  Pending",
        }
        self.push_status_lbl.setText(labels.get(ps, f"○  {ps}"))

    # ==================================================================
    # Model list slots
    # ==================================================================

    def _on_model_selected(self, item: Optional[QListWidgetItem]) -> None:
        if not item:
            return
        model_id = item.data(Qt.ItemDataRole.UserRole)
        if not model_id:
            return

        self._current_model_id = model_id
        self.centre_tabs.setEnabled(True)

        # Load every tab editor
        self.param_editor.load_model(model_id)
        self.register_mapper.load_model(model_id)
        self.limits_editor.load_model(model_id)
        self.block_editor.load_model(model_id)
        self.plc_live_panel.load_model(model_id)

        # Update push status label
        model = self._app_state.model_repo.get_model(model_id)
        if model:
            self._update_push_status(model)

        logger.debug("SettingsWindow: model selected id=%d", model_id)

    # ==================================================================
    # CRUD handlers
    # ==================================================================

    def _on_add_model(self) -> None:
        models = self._app_state.model_repo.get_all_models()
        dlg = ModelDialog(
            mode="add",
            existing_models=models,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.result_data
        try:
            new_id = self._app_state.model_repo.create_model(
                name=data["name"],
                description=data.get("description", ""),
                model_number=data.get("model_number", ""),
                plc_block_start_register=data.get("plc_block_start_register", 0),
            )
            # Copy parameters from existing model if requested
            src_id = data.get("copy_from_model_id")
            if src_id:
                self._app_state.param_repo.duplicate_model_parameters(
                    src_id, new_id
                )
            self._refresh_model_list()
            self._select_model_by_id(new_id)
            logger.info("SettingsWindow: created model id=%d name='%s'", new_id, data["name"])
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Create Model", str(exc))
        except Exception as exc:
            logger.exception("SettingsWindow: create_model error")
            QMessageBox.critical(self, "Error", str(exc))

    def _on_edit_model(self) -> None:
        if not self._current_model_id:
            return
        model = self._app_state.model_repo.get_model(self._current_model_id)
        if not model:
            return

        dlg = ModelDialog(
            mode="edit",
            model_data=model,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.result_data
        try:
            self._app_state.model_repo.update_model(
                self._current_model_id,
                name=data.get("name"),
                description=data.get("description"),
                model_number=data.get("model_number"),
                plc_block_start_register=data.get("plc_block_start_register"),
            )
            self._refresh_model_list()
            self._select_model_by_id(self._current_model_id)
            logger.info("SettingsWindow: edited model id=%d", self._current_model_id)
        except Exception as exc:
            logger.exception("SettingsWindow: update_model error")
            QMessageBox.critical(self, "Update Error", str(exc))

    def _on_delete_model(self) -> None:
        if not self._current_model_id:
            return
        model = self._app_state.model_repo.get_model(self._current_model_id)
        if not model:
            return

        confirmed = ConfirmDialog.ask(
            self,
            "Delete Model",
            f"Delete '{model['name']}'?\n\n"
            "All parameters, register mappings, limits and test history "
            "for this model will be permanently deleted.",
            confirm_text="Delete",
            danger=True,
        )
        if not confirmed:
            return

        try:
            self._app_state.model_repo.delete_model(self._current_model_id)
            logger.info(
                "SettingsWindow: deleted model id=%d name='%s'",
                self._current_model_id, model["name"],
            )
        except Exception as exc:
            logger.exception("SettingsWindow: delete_model error")
            QMessageBox.critical(self, "Delete Error", str(exc))
            return

        self._current_model_id = None
        self._refresh_model_list()
        self._clear_all_editors()

    # ==================================================================
    # Push to PLC
    # ==================================================================

    def _on_push_to_plc(self) -> None:
        if not self._current_model_id:
            QMessageBox.information(
                self, "No Model", "Select a model first."
            )
            return
        if not self._app_state.is_plc_connected:
            QMessageBox.warning(
                self, "Not Connected", "PLC is not connected."
            )
            return

        # Validate parameters before push
        warnings = self._app_state.param_repo.validate_model_parameters(
            self._current_model_id
        )
        if warnings:
            msg = "\n".join(warnings)
            reply = QMessageBox.question(
                self,
                "Configuration Warnings",
                f"Warnings found:\n{msg}\n\nPush anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        config = self._app_state.model_repo.get_full_model_config(
            self._current_model_id
        )
        if not config:
            QMessageBox.critical(self, "Error", "Could not load model configuration.")
            return

        operator_id = (
            self._app_state.current_user.get("id", 0)
            if self._app_state.current_user else 0
        )

        self.push_status_lbl.setText("◌  Pushing…")

        from src.plc.model_push_worker import ModelPushWorker
        self._push_worker = ModelPushWorker(
            config,
            self._app_state.write_manager,
            operator_id,
            parent=self,
        )
        self._push_worker.push_success.connect(
            lambda name: self._on_push_success(name)
        )
        self._push_worker.push_failed.connect(
            lambda name, err: self._on_push_failed(name, err)
        )
        self._push_worker.start()
        logger.info(
            "SettingsWindow: push started for model_id=%d",
            self._current_model_id,
        )

    def _on_push_success(self, model_name: str) -> None:
        self.push_status_lbl.setText(f"✓  Pushed {model_name}")
        self.push_status_lbl.setStyleSheet("color: #1a6b3a; font-size: 11px;")
        self._refresh_model_list()
        self.plc_live_panel.update_write_log()
        logger.info("SettingsWindow: push success model='%s'", model_name)

    def _on_push_failed(self, model_name: str, error: str) -> None:
        self.push_status_lbl.setText("✗  Push failed")
        self.push_status_lbl.setStyleSheet("color: #c0392b; font-size: 11px;")
        QMessageBox.critical(
            self,
            "Push Failed",
            f"Model '{model_name}' push failed:\n{error}",
        )
        logger.error(
            "SettingsWindow: push failed model='%s' error='%s'",
            model_name, error,
        )

    # ==================================================================
    # Cross-tab reload signals
    # ==================================================================

    def _on_params_saved(self, model_id: int) -> None:
        """After ParamEditor saves — reload all downstream tabs."""
        self.register_mapper.load_model(model_id)
        self.limits_editor.load_model(model_id)
        self.block_editor.load_model(model_id)
        self._set_dirty(False)

        # Update active evaluator if this is the current model
        if model_id == self._app_state.current_model_id:
            new_config = self._app_state.model_repo.get_full_model_config(model_id)
            if new_config:
                self._app_state.set_model(new_config)
                cm = self._app_state.connection_manager
                if cm and hasattr(cm, "update_parameters"):
                    cm.update_parameters(new_config.get("parameters", []))

        logger.debug("SettingsWindow: params saved model_id=%d", model_id)

    def _on_registers_saved(self, model_id: int) -> None:
        """After RegisterMapper saves — refresh live panel."""
        self.plc_live_panel.load_model(model_id)
        self._set_dirty(False)
        logger.debug("SettingsWindow: registers saved model_id=%d", model_id)

    def _on_limits_saved(self, model_id: int) -> None:
        """After LimitsEditor saves — update evaluator + live panel."""
        self.plc_live_panel.update_write_log()
        self._set_dirty(False)

        if model_id == self._app_state.current_model_id:
            new_config = self._app_state.model_repo.get_full_model_config(model_id)
            if new_config:
                self._app_state.set_model(new_config)

        logger.debug("SettingsWindow: limits saved model_id=%d", model_id)

    # ==================================================================
    # Dirty state
    # ==================================================================

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty

    # ==================================================================
    # Close handling
    # ==================================================================

    def _on_close_requested(self) -> None:
        """Called by the Close button."""
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        # Check if any tab editor has unsaved changes
        dirty = (
            self._dirty
            or self.param_editor.is_dirty()
        )
        if dirty:
            confirmed = ConfirmDialog.ask(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Close anyway?",
                confirm_text="Close",
                danger=True,
            )
            if not confirmed:
                event.ignore()
                return
        event.accept()
