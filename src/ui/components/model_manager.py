"""
ui/components/model_manager.py
Side panel containing Model selection loops, DB query refreshes, and cascading CRUD actions.
Maps directly to Admin constraints layouts implicitly.
"""

from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from src.db.model_repo import ModelRepository
from src.ui.dialogs.confirm_dialog import ConfirmDialog
from src.ui.dialogs.model_dialog import ModelDialog

class ModelManager(QFrame):
    """
    Sub-screen mechanism organizing the repository lists via SQLite integrations structurally.
    """
    model_selected = pyqtSignal(int)
    model_changed = pyqtSignal()
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._model_repo = ModelRepository(self._db)
        
        self.setObjectName("card")
        self.setStyleSheet("QFrame#card { background-color: #f8f9fc; border: 1px solid #d0d8e8; border-radius: 4px; }")
        
        self._current_selected_id = None
        self._setup_ui()
        self.refresh_model_list()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(20)
        
        # --- LEFT PANEL: MODEL LIST ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        left_layout.addWidget(QLabel("Existing Models", styleSheet="font-weight: bold; font-size: 14px;"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Sr No", "Solution Name"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("selection-background-color: #c8e6c9; selection-color: black;")
        
        self.table.cellDoubleClicked.connect(self._on_table_item_activated)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        
        left_layout.addWidget(self.table)
        
        lbl_hint = QLabel("Select a model from the list to edit or delete it.")
        lbl_hint.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        left_layout.addWidget(lbl_hint)
        
        main_layout.addWidget(left_panel, stretch=2)
        
        # --- RIGHT PANEL ---
        right_panel = QFrame()
        right_panel.setObjectName("form_card")
        right_layout = QVBoxLayout(right_panel)
        
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)
        
        right_layout.addWidget(QLabel("Model Details", styleSheet="font-weight: bold; font-size: 14px; color: #1e2d4a;"))
        self.edit_name = QLineEdit()
        self.edit_desc = QLineEdit()
        self.edit_no = QLineEdit()
        self.edit_image = QLineEdit()
        self.edit_image.setPlaceholderText("(Optional URL or Path)")
        
        right_layout.addWidget(QLabel("Model Name:"))
        right_layout.addWidget(self.edit_name)
        right_layout.addWidget(QLabel("Model Description:"))
        right_layout.addWidget(self.edit_desc)
        right_layout.addWidget(QLabel("Model Number / Code:"))
        right_layout.addWidget(self.edit_no)
        right_layout.addWidget(QLabel("Image Reference:"))
        right_layout.addWidget(self.edit_image)
        
        right_layout.addStretch()
        
        # Action Buttons Area
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setObjectName("btn_success")
        self.btn_save.clicked.connect(self._on_save_clicked)
        
        self.btn_delete = QPushButton("Delete Model")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        
        right_layout.addLayout(btn_layout)

        # Add-New Trigger
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #ecf0f1;")
        right_layout.addWidget(divider)
        
        self.btn_add = QPushButton("+ Add New Model")
        self.btn_add.clicked.connect(self._on_add_clicked)
        right_layout.addWidget(self.btn_add)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.hide()
        right_layout.addWidget(self.lbl_status)
        
        main_layout.addWidget(right_panel, stretch=1)

    def refresh_model_list(self) -> None:
        """Wipes and seamlessly reprints DB matrices mapped iteratively to internal QTable items"""
        models = self._model_repo.get_all_models()
        self.table.setRowCount(0)
        
        for idx, m in enumerate(models):
            self.table.insertRow(idx)
            # Safe caching within hidden abstract properties mechanically 
            item_sr = QTableWidgetItem(str(idx + 1))
            item_sr.setData(Qt.ItemDataRole.UserRole, m["id"])
            item_name = QTableWidgetItem(m["name"])
            
            self.table.setItem(idx, 0, item_sr)
            self.table.setItem(idx, 1, item_name)
            
            # Maintain active persistence tracking state visually 
            if self._current_selected_id == m["id"]:
                self.table.selectRow(idx)

    def _on_selection_changed(self) -> None:
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            item = self.table.item(row, 0)
            if item:
                self._current_selected_id = item.data(Qt.ItemDataRole.UserRole)

    def _on_table_item_activated(self, row: int, col: int) -> None:
        """Load selected model into form fields instantly."""
        if self._current_selected_id is None:
            return
            
        full_model = self._model_repo.get_model(self._current_selected_id)
        if full_model:
            self.edit_name.setText(full_model.get("name", ""))
            self.edit_desc.setText(full_model.get("description", ""))
            self.edit_no.setText(full_model.get("model_number", ""))
            self.edit_image.setText(full_model.get("image_path", ""))
            self.model_selected.emit(self._current_selected_id)

    def _on_add_clicked(self) -> None:
        """Route logic through generic modal blocks enforcing persistence."""
        dialog = ModelDialog(mode="add", parent=self)
        if dialog.exec():
            data = dialog.result_data
            new_id = self._model_repo.create_model(data["name"], data["description"], data["model_number"])
            self._current_selected_id = new_id
            self.refresh_model_list()
            self.model_changed.emit()
            self._show_temp_status("Model added.")

    def _on_edit_clicked(self) -> None:
        if self._current_selected_id is None:
            return
            
        full_model = self._model_repo.get_model(self._current_selected_id)
        dialog = ModelDialog(mode="edit", model_data=full_model, parent=self)
        if dialog.exec():
            data = dialog.result_data
            # Assuming Database repo implementation supports update logically matching previous signatures bounds 
            self._model_repo.update_model(self._current_selected_id, data["name"], data["description"], data["model_number"])
            self.refresh_model_list()
            self.model_changed.emit()

    def _on_delete_clicked(self) -> None:
        if self._current_selected_id is None:
            return
            
        row = self.table.currentRow()
        name = self.table.item(row, 1).text()
        
        msg = f"Delete '{name}'? This will remove all signals, limits and test history for this model."
        if ConfirmDialog.ask(self, "Delete?", msg, danger=True):
            self._model_repo.delete_model(self._current_selected_id)
            self._current_selected_id = None
            self.edit_name.clear()
            self.edit_desc.clear()
            self.edit_no.clear()
            self.refresh_model_list()
            self.model_changed.emit()

    def _on_save_clicked(self) -> None:
        if self._current_selected_id is None:
            return
            
        name = self.edit_name.text().strip()
        desc = self.edit_desc.text().strip()
        num = self.edit_no.text().strip()
        
        if not name:
            return
            
        self._model_repo.update_model(self._current_selected_id, name, desc, num)
        self.refresh_model_list()
        self.model_changed.emit()
        self._show_temp_status("Saved.")

    def _show_temp_status(self, msg: str) -> None:
        self.lbl_status.setText(msg)
        self.lbl_status.show()
        QTimer.singleShot(2000, self.lbl_status.hide)
        
    def _on_close_clicked(self) -> None:
        """Route exit signals recursively tracking parent boundaries to eliminate memory bleed."""
        if self.window():
            self.window().close()
