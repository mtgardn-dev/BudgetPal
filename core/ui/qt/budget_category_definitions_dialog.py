from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.persistence.repositories.categories_repo import CategoriesRepository
from core.services.budget_allocations import BudgetAllocationsService
from core.ui.qt.models.dict_table_model import DictTableModel


class BudgetCategoryDefinitionsDialog(QDialog):
    def __init__(
        self,
        *,
        service: BudgetAllocationsService,
        categories_repo: CategoriesRepository,
        logger: logging.Logger,
        on_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.categories_repo = categories_repo
        self.logger = logger
        self.on_changed = on_changed
        self.editing_definition_id: int | None = None

        self.setWindowTitle("Budget Category Definitions")
        self.setModal(False)
        self.resize(1180, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addStretch(1)
        self.close_button = QPushButton("Close")
        top_row.addWidget(self.close_button)
        root.addLayout(top_row)

        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        details_layout.addWidget(QLabel("Budget Category Definition"))

        self.category_input = QComboBox()
        self.category_input.setEditable(False)
        self.category_input.setMinimumWidth(260)
        self.category_input.setMaximumWidth(360)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(130)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMinimumWidth(420)
        self.note_input.setMaximumWidth(760)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        row1.addWidget(QLabel("Category"))
        row1.addWidget(self.category_input)
        row1.addWidget(QLabel("Amount"))
        row1.addWidget(self.amount_input)
        row1.addStretch(1)
        details_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        row2.addWidget(QLabel("Note"))
        row2.addWidget(self.note_input)
        row2.addStretch(1)
        details_layout.addLayout(row2)

        action_row = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        details_layout.addLayout(action_row)
        root.addWidget(details_frame, 0)

        list_frame = QFrame()
        list_frame.setFrameShape(QFrame.StyledPanel)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)
        list_layout.addWidget(QLabel("Definitions"))

        self.table = QTableView()
        self.model = DictTableModel(
            headers=["Category", "Amount", "Note"],
            key_order=["category_name", "amount_display", "note"],
            rows=[],
        )
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(320)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 140)
        self.table.horizontalHeader().setStretchLastSection(True)
        list_layout.addWidget(self.table, 1)

        root.addWidget(list_frame, 1)

        self.save_button.clicked.connect(self.save_definition)
        self.delete_button.clicked.connect(self.delete_definition)
        self.close_button.clicked.connect(self.close)
        self.table.clicked.connect(self.on_selection_changed)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.on_selection_changed())

        self._refresh_category_choices()
        self.new_form()
        self.reload_rows()

    @staticmethod
    def _parse_currency_cents(amount_text: str) -> int:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return 0
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric (example: 100.00).") from exc
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents < 0:
            raise ValueError("Amount cannot be negative.")
        return cents

    @staticmethod
    def _combo_select_data(combo: QComboBox, target_data: int | None) -> None:
        if target_data is None:
            if combo.count() > 0:
                combo.setCurrentIndex(0)
            return
        idx = combo.findData(target_data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _refresh_category_choices(self) -> None:
        selected_category_id = self.category_input.currentData()
        self.category_input.clear()
        self.category_input.addItem("", None)
        for row in self.categories_repo.list_active(category_type="expense"):
            self.category_input.addItem(str(row["name"]), int(row["category_id"]))
        if selected_category_id is not None:
            self._combo_select_data(self.category_input, int(selected_category_id))
        elif self.category_input.count() > 0:
            self.category_input.setCurrentIndex(0)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_rows()

    def reload_rows(self) -> None:
        rows = self.service.list_definitions()
        self.model.replace_rows(rows)
        self.logger.info("Loaded %s budget category definitions", len(rows))

    def new_form(self) -> None:
        self.editing_definition_id = None
        if self.category_input.count() > 0:
            self.category_input.setCurrentIndex(0)
        self.amount_input.clear()
        self.note_input.clear()
        self.table.clearSelection()

    def _selected_row(self) -> dict | None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return None
        return self.model.row_dict(selection[0].row())

    def on_selection_changed(self) -> None:
        row = self._selected_row()
        if not row:
            return
        self.editing_definition_id = int(row.get("definition_id") or 0)
        self._combo_select_data(self.category_input, row.get("category_id"))
        cents = int(row.get("default_amount_cents") or 0)
        self.amount_input.setText(f"{cents / 100:.2f}")
        self.note_input.setText(str(row.get("note") or ""))

    def save_definition(self) -> None:
        category_id = self.category_input.currentData()
        if category_id is None:
            QMessageBox.warning(self, "Save Definition", "Category is required.")
            return
        try:
            amount_cents = self._parse_currency_cents(self.amount_input.text())
            note = self.note_input.text().strip() or None
            definition_id = self.service.upsert_definition(
                category_id=int(category_id),
                amount_cents=amount_cents,
                note=note,
            )
            self.logger.info("Saved budget category definition %s", definition_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Definition", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save budget category definition failed: %s", exc)
            QMessageBox.critical(self, "Save Definition Failed", str(exc))
            return

        self.reload_rows()
        self.new_form()
        if self.on_changed:
            self.on_changed()

    def delete_definition(self) -> None:
        row = self._selected_row()
        if not row:
            QMessageBox.information(self, "Delete Definition", "Select a definition to delete.")
            return
        definition_id = int(row.get("definition_id") or 0)
        if not definition_id:
            QMessageBox.warning(self, "Delete Definition", "Invalid definition selection.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Definition",
            f"Delete budget definition for '{row.get('category_name', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.service.delete_definition(definition_id)
        except Exception as exc:
            self.logger.error("Delete budget definition failed: %s", exc)
            QMessageBox.critical(self, "Delete Definition Failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Definition", "Selected definition no longer exists.")
            return
        self.logger.info("Deleted budget category definition %s", definition_id)
        self.reload_rows()
        self.new_form()
        if self.on_changed:
            self.on_changed()
