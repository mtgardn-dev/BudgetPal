from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable

from PySide6.QtCore import Qt
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

from core.persistence.repositories.accounts_repo import AccountsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository
from core.services.income import IncomeService
from core.ui.qt.models.income_model import IncomeTableModel


class IncomeDefinitionsDialog(QDialog):
    def __init__(
        self,
        *,
        income_service: IncomeService,
        categories_repo: CategoriesRepository,
        accounts_repo: AccountsRepository,
        logger: logging.Logger,
        on_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.income_service = income_service
        self.categories_repo = categories_repo
        self.accounts_repo = accounts_repo
        self.logger = logger
        self.on_changed = on_changed
        self.sort_key = "description"
        self.editing_income_id: int | None = None

        self.setWindowTitle("Income Definitions")
        self.setModal(False)
        self.resize(1240, 780)

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
        details_layout.addWidget(QLabel("Recurring Income Definition"))

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description")
        self.description_input.setMinimumWidth(420)
        self.description_input.setMaximumWidth(520)

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
        self.category_input.setFixedWidth(340)

        self.account_input = QComboBox()
        self.account_input.setEditable(False)
        self.account_input.setFixedWidth(300)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMinimumWidth(420)
        self.note_input.setMaximumWidth(760)

        interval_holder = QWidget()
        interval_row = QHBoxLayout(interval_holder)
        interval_row.setContentsMargins(0, 0, 0, 0)
        interval_row.setSpacing(4)
        interval_row.addWidget(self.interval_count_input)
        interval_row.addWidget(self.interval_unit_combo)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        row1.addWidget(QLabel("Description"))
        row1.addWidget(self.description_input)
        row1.addWidget(QLabel("Start Date"))
        row1.addWidget(self.start_date_input)
        row1.addWidget(QLabel("Interval"))
        row1.addWidget(interval_holder)
        row1.addStretch(1)
        details_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        row2.addWidget(QLabel("Amount (USD)"))
        row2.addWidget(self.amount_input)
        row2.addWidget(QLabel("Category"))
        row2.addWidget(self.category_input)
        row2.addWidget(QLabel("Account"))
        row2.addWidget(self.account_input)
        row2.addStretch(1)
        details_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)
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
        self.model = IncomeTableModel([])
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
        self.table.setColumnWidth(5, 120)
        self.table.horizontalHeader().setStretchLastSection(True)
        list_layout.addWidget(self.table, 1)

        sort_row = QHBoxLayout()
        self.sort_category_button = QPushButton("Sort by Category")
        self.sort_description_button = QPushButton("Sort by Description")
        self.sort_account_button = QPushButton("Sort by Account")
        sort_row.addWidget(self.sort_category_button)
        sort_row.addWidget(self.sort_description_button)
        sort_row.addWidget(self.sort_account_button)
        sort_row.addStretch(1)
        list_layout.addLayout(sort_row)
        root.addWidget(list_frame, 1)

        self.new_button.clicked.connect(self.new_form)
        self.save_button.clicked.connect(self.save_definition)
        self.delete_button.clicked.connect(self.delete_definition)
        self.close_button.clicked.connect(self.close)
        self.sort_category_button.clicked.connect(lambda: self.set_sort("category"))
        self.sort_description_button.clicked.connect(lambda: self.set_sort("description"))
        self.sort_account_button.clicked.connect(lambda: self.set_sort("account"))
        self.table.clicked.connect(self.on_selection_changed)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.on_selection_changed())

        self._refresh_category_choices()
        self._refresh_account_choices()
        QWidget.setTabOrder(self.description_input, self.start_date_input)
        QWidget.setTabOrder(self.start_date_input, self.interval_count_input)
        QWidget.setTabOrder(self.interval_count_input, self.interval_unit_combo)
        QWidget.setTabOrder(self.interval_unit_combo, self.amount_input)
        QWidget.setTabOrder(self.amount_input, self.category_input)
        QWidget.setTabOrder(self.category_input, self.account_input)
        QWidget.setTabOrder(self.account_input, self.note_input)
        QWidget.setTabOrder(self.note_input, self.new_button)
        QWidget.setTabOrder(self.new_button, self.save_button)
        QWidget.setTabOrder(self.save_button, self.delete_button)
        QWidget.setTabOrder(self.delete_button, self.close_button)
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
                if combo.isEditable():
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
        for row in self.categories_repo.list_active(category_type="income"):
            self.category_input.addItem(str(row["name"]), int(row["category_id"]))
        if selected_category_id is not None:
            self._combo_select_data(self.category_input, int(selected_category_id))
        elif selected_text:
            self.category_input.setEditText(selected_text)
        else:
            self.category_input.setCurrentIndex(0)
            self.category_input.setEditText("")

    def _refresh_account_choices(self) -> None:
        selected_account_id = self.account_input.currentData()
        self.account_input.clear()
        for row in self.accounts_repo.list_active():
            self.account_input.addItem(str(row["name"]), int(row["account_id"]))
        if selected_account_id is not None:
            self._combo_select_data(self.account_input, int(selected_account_id))
        elif self.account_input.count() > 0:
            checking_idx = self.account_input.findText("Checking", Qt.MatchFixedString)
            if checking_idx < 0:
                for idx in range(self.account_input.count()):
                    if self.account_input.itemText(idx).strip().casefold() == "checking":
                        checking_idx = idx
                        break
            self.account_input.setCurrentIndex(checking_idx if checking_idx >= 0 else 0)

    def set_sort(self, sort_key: str) -> None:
        self.sort_key = sort_key
        self.reload_rows()

    def reload_rows(self) -> None:
        rows = self.income_service.list_definitions(sort_by=self.sort_key)
        self.model.replace_rows(rows)
        self.logger.info("Loaded %s income definitions (sort=%s)", len(rows), self.sort_key)

    def new_form(self) -> None:
        self.editing_income_id = None
        self.description_input.clear()
        self.start_date_input.setText(date.today().isoformat())
        self.interval_count_input.setText("1")
        self.interval_unit_combo.setCurrentText("months")
        self.amount_input.clear()
        self.note_input.clear()
        self.category_input.setCurrentIndex(0)
        self.category_input.setEditText("")
        if self.account_input.count() > 0:
            checking_idx = self.account_input.findText("Checking", Qt.MatchFixedString)
            if checking_idx < 0:
                for idx in range(self.account_input.count()):
                    if self.account_input.itemText(idx).strip().casefold() == "checking":
                        checking_idx = idx
                        break
            self.account_input.setCurrentIndex(checking_idx if checking_idx >= 0 else 0)
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
        self.editing_income_id = int(row.get("income_id") or 0)
        self.description_input.setText(str(row.get("description") or ""))
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
        self._combo_select_data(self.account_input, row.get("account_id"))

    @staticmethod
    def _parse_currency_cents_or_none(amount_text: str) -> int | None:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric (example: 3146.00).") from exc
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents < 0:
            raise ValueError("Amount cannot be negative.")
        return cents

    def _build_payload(self) -> dict:
        description = self.description_input.text().strip()
        if not description:
            raise ValueError("Description is required.")

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
                existing = self.categories_repo.find_by_name(category_name, category_type="income")
                if existing:
                    category_id = int(existing["category_id"])
                else:
                    category_id = self.categories_repo.upsert(category_name, is_income=True)
                    self._refresh_category_choices()
                    self._combo_select_data(self.category_input, category_id)

        account_id = self.account_input.currentData()
        if account_id is None:
            raise ValueError("Account is required.")

        return {
            "description": description,
            "start_date": start_date_text,
            "interval_count": interval_count,
            "interval_unit": interval_unit,
            "amount_cents": amount_cents,
            "category_id": int(category_id) if category_id is not None else None,
            "account_id": int(account_id),
            "notes": self.note_input.text().strip() or None,
        }

    def save_definition(self) -> None:
        try:
            payload = self._build_payload()
            if self.editing_income_id:
                updated = self.income_service.update_definition(
                    income_id=int(self.editing_income_id),
                    **payload,
                )
                if not updated:
                    QMessageBox.warning(self, "Save Definition", "Selected definition no longer exists.")
                    self.reload_rows()
                    self.new_form()
                    return
                self.logger.info("Updated income definition %s", self.editing_income_id)
            else:
                new_id = self.income_service.add_definition(**payload)
                self.logger.info("Added income definition %s", new_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Definition", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save income definition failed: %s", exc)
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
        income_id = int(row.get("income_id") or 0)
        if not income_id:
            QMessageBox.warning(self, "Delete Definition", "Invalid definition selection.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Definition",
            f"Delete income definition '{row.get('description', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.income_service.delete_definition(income_id)
        except Exception as exc:
            self.logger.error("Delete income definition failed: %s", exc)
            QMessageBox.critical(self, "Delete Definition Failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Definition", "Selected definition no longer exists.")
            return
        self.logger.info("Deleted income definition %s", income_id)
        self.reload_rows()
        self.new_form()
        if self.on_changed:
            self.on_changed()
