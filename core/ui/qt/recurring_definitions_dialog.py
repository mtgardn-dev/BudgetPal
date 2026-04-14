from __future__ import annotations

import logging
from datetime import date, datetime
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
from core.services.bills import BillsService
from core.ui.qt.models.bills_model import BillsTableModel


class RecurringDefinitionsDialog(QDialog):
    def __init__(
        self,
        *,
        bills_service: BillsService,
        categories_repo: CategoriesRepository,
        logger: logging.Logger,
        on_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bills_service = bills_service
        self.categories_repo = categories_repo
        self.logger = logger
        self.on_changed = on_changed
        self.sort_key = "payment_due"
        self.editing_bill_id: int | None = None

        self.setWindowTitle("Bill Definitions")
        self.setModal(False)
        self.resize(1220, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(8)
        heading_row.addWidget(QLabel("Recurring Bill Definition"))
        heading_row.addStretch(1)
        self.close_button = QPushButton("Close")
        heading_row.addWidget(self.close_button)
        details_layout.addLayout(heading_row)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name")
        self.name_input.setFixedWidth(420)

        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        self.start_date_input.setFixedWidth(140)

        self.interval_count_input = QLineEdit("1")
        self.interval_count_input.setFixedWidth(60)

        self.interval_unit_combo = QComboBox()
        self.interval_unit_combo.addItems(["days", "weeks", "months", "years", "once"])
        self.interval_unit_combo.setCurrentText("months")
        self.interval_unit_combo.setFixedWidth(120)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(120)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.setInsertPolicy(QComboBox.NoInsert)
        self.category_input.setMinimumWidth(220)
        self.category_input.setMaximumWidth(320)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setFixedWidth(560)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.addWidget(QLabel("Name"))
        row1.addWidget(self.name_input)
        row1.addWidget(QLabel("Start Date"))
        row1.addWidget(self.start_date_input)
        row1.addStretch(1)
        details_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(QLabel("Interval"))
        interval_holder = QWidget()
        interval_row = QHBoxLayout(interval_holder)
        interval_row.setContentsMargins(0, 0, 0, 0)
        interval_row.setSpacing(6)
        interval_row.addWidget(self.interval_count_input)
        interval_row.addWidget(self.interval_unit_combo)
        row2.addWidget(interval_holder)
        row2.addWidget(QLabel("Amount (USD)"))
        row2.addWidget(self.amount_input)
        row2.addWidget(QLabel("Category"))
        row2.addWidget(self.category_input)
        row2.addStretch(1)
        details_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(8)
        row3.addWidget(QLabel("Note"))
        row3.addWidget(self.note_input)
        row3.addStretch(1)
        details_layout.addLayout(row3)

        action_row = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        action_row.addWidget(self.new_button)
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
        self.model = BillsTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(320)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 260)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 100)
        self.table.horizontalHeader().setStretchLastSection(True)
        list_layout.addWidget(self.table, 1)

        sort_row = QHBoxLayout()
        self.sort_name_button = QPushButton("Sort by Name")
        self.sort_category_button = QPushButton("Sort by Category")
        self.sort_due_button = QPushButton("Sort by Payment Due")
        sort_row.addWidget(self.sort_name_button)
        sort_row.addWidget(self.sort_category_button)
        sort_row.addWidget(self.sort_due_button)
        sort_row.addStretch(1)
        list_layout.addLayout(sort_row)

        root.addWidget(list_frame, 1)

        self.new_button.clicked.connect(self.new_form)
        self.save_button.clicked.connect(self.save_definition)
        self.delete_button.clicked.connect(self.delete_definition)
        self.close_button.clicked.connect(self.close)
        self.sort_name_button.clicked.connect(lambda: self.set_sort("name"))
        self.sort_category_button.clicked.connect(lambda: self.set_sort("category"))
        self.sort_due_button.clicked.connect(lambda: self.set_sort("payment_due"))
        self.table.clicked.connect(self.on_selection_changed)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.on_selection_changed())

        self._refresh_category_choices()
        self.new_form()
        self.reload_rows()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload_rows()

    @staticmethod
    def _combo_select_data(combo: QComboBox, target_data: int | None) -> None:
        if target_data is None:
            if combo.count() > 0:
                combo.setCurrentIndex(0)
                combo.setEditText("")
            return
        idx = combo.findData(target_data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _refresh_category_choices(self) -> None:
        selected_category_id = self.category_input.currentData()
        selected_text = self.category_input.currentText().strip()
        self.category_input.clear()
        self.category_input.addItem("", None)
        for row in self.categories_repo.list_active(category_type="expense"):
            self.category_input.addItem(str(row["name"]), int(row["category_id"]))

        if selected_category_id is not None:
            self._combo_select_data(self.category_input, int(selected_category_id))
        elif selected_text:
            self.category_input.setEditText(selected_text)
        else:
            self.category_input.setCurrentIndex(0)
            self.category_input.setEditText("")

    def set_sort(self, sort_key: str) -> None:
        self.sort_key = sort_key
        self.reload_rows()

    def reload_rows(self) -> None:
        all_rows = self.bills_service.list_bill_definitions(sort_by=self.sort_key)
        rows = [row for row in all_rows if str(row.get("source_system") or "").strip().lower() == "budgetpal"]
        self.model.replace_rows(rows)
        self.logger.info("Loaded %s recurring bill definitions (sort=%s)", len(rows), self.sort_key)

    def new_form(self) -> None:
        self.editing_bill_id = None
        self.name_input.clear()
        self.start_date_input.setText(date.today().isoformat())
        self.interval_count_input.setText("1")
        self.interval_unit_combo.setCurrentText("months")
        self.amount_input.clear()
        self.note_input.clear()
        self.category_input.setCurrentIndex(0)
        self.category_input.setEditText("")
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
        self.editing_bill_id = int(row.get("bill_id") or 0)
        self.name_input.setText(str(row.get("name") or ""))

        start_date = str(row.get("start_date") or "").strip()
        payment_due = str(row.get("payment_due") or "").strip()
        self.start_date_input.setText(start_date or payment_due or date.today().isoformat())

        self.interval_count_input.setText(str(int(row.get("interval_count") or 1)))
        interval_unit = str(row.get("interval_unit") or "months").strip().lower()
        if not interval_unit.endswith("s") and interval_unit != "once":
            interval_unit = f"{interval_unit}s"
        if self.interval_unit_combo.findText(interval_unit) >= 0:
            self.interval_unit_combo.setCurrentText(interval_unit)
        else:
            self.interval_unit_combo.setCurrentText("months")

        amount_cents = row.get("default_amount_cents")
        if amount_cents is None:
            self.amount_input.clear()
        else:
            self.amount_input.setText(f"{int(amount_cents) / 100:.2f}")

        self.note_input.setText(str(row.get("notes") or ""))
        self._combo_select_data(self.category_input, row.get("category_id"))

    @staticmethod
    def _parse_currency_cents_or_none(amount_text: str) -> int | None:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric (example: 74.68).") from exc
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents < 0:
            raise ValueError("Amount cannot be negative.")
        return cents

    def _build_payload(self) -> dict:
        name = self.name_input.text().strip()
        if not name:
            raise ValueError("Bill name is required.")

        start_date_text = self.start_date_input.text().strip()
        try:
            datetime.strptime(start_date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Start Date must be in YYYY-MM-DD format.") from exc

        interval_text = self.interval_count_input.text().strip()
        if not interval_text:
            raise ValueError("Interval is required.")
        try:
            interval_count = int(interval_text)
        except ValueError as exc:
            raise ValueError("Interval must be a whole number.") from exc
        if interval_count < 1:
            raise ValueError("Interval must be at least 1.")

        interval_unit = self.interval_unit_combo.currentText().strip().lower()
        if interval_unit not in {"days", "weeks", "months", "years", "once"}:
            raise ValueError("Interval unit is invalid.")

        amount_cents = self._parse_currency_cents_or_none(self.amount_input.text())

        category_id = self.category_input.currentData()
        if category_id is None:
            category_name = self.category_input.currentText().strip()
            if category_name:
                existing = self.categories_repo.find_by_name(category_name, category_type="expense")
                if existing:
                    category_id = int(existing["category_id"])
                else:
                    category_id = self.categories_repo.upsert(category_name, is_income=False)
                    self._refresh_category_choices()
                    self._combo_select_data(self.category_input, category_id)

        return {
            "name": name,
            "start_date": start_date_text,
            "interval_count": interval_count,
            "interval_unit": interval_unit,
            "amount_cents": amount_cents,
            "category_id": int(category_id) if category_id is not None else None,
            "notes": self.note_input.text().strip() or None,
        }

    def save_definition(self) -> None:
        try:
            payload = self._build_payload()
            if self.editing_bill_id:
                updated = self.bills_service.update_bill_definition(
                    bill_id=int(self.editing_bill_id),
                    **payload,
                )
                if not updated:
                    QMessageBox.warning(self, "Save Definition", "Selected definition no longer exists.")
                    self.reload_rows()
                    self.new_form()
                    return
                self.logger.info("Updated recurring definition %s", self.editing_bill_id)
            else:
                new_id = self.bills_service.add_bill_definition(**payload)
                self.logger.info("Added recurring definition %s", new_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Definition", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save definition failed: %s", exc)
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
        bill_id = int(row.get("bill_id") or 0)
        if not bill_id:
            QMessageBox.warning(self, "Delete Definition", "Invalid definition selection.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Definition",
            f"Delete recurring definition '{row.get('name', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.bills_service.delete_bill_definition(bill_id)
        except Exception as exc:
            self.logger.error("Delete definition failed: %s", exc)
            QMessageBox.critical(self, "Delete Definition Failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Definition", "Selected definition no longer exists.")
            return

        self.logger.info("Deleted recurring definition %s", bill_id)
        self.reload_rows()
        self.new_form()
        if self.on_changed:
            self.on_changed()
