from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.app_context import BudgetPalContext
from core.domain import TransactionInput
from core.importers.subtracker_view import SubTrackerIntegrationError
from core.importers.xlsx_transactions import XLSXTransactionImporter
from core.services.reporting import ReportingService
from core.settings import get_settings_manager
from core.ui.qt.settings_dialog import SettingsDialog
from core.ui.qt.sub_payments_dialog import SubPaymentsDialog
from core.ui.qt.tabs.bills import BillsTab
from core.ui.qt.tabs.buckets import BucketsTab
from core.ui.qt.tabs.budget_month import BudgetMonthTab
from core.ui.qt.tabs.dashboard import DashboardTab
from core.ui.qt.tabs.reports import ReportsTab
from core.ui.qt.tabs.transactions import TransactionsTab


class BudgetPalWindow(QMainWindow):
    LOG_LEVEL_COLORS = {
        "DEBUG": "#6B7280",
        "INFO": "#0F766E",
        "WARNING": "#B45309",
        "ERROR": "#B91C1C",
        "CRITICAL": "#7F1D1D",
        "DEFAULT": "#111827",
    }
    BUTTON_STYLESHEET = """
    QPushButton {
        background-color: #2563EB;
        color: #FFFFFF;
        border: 1px solid #1D4ED8;
        border-radius: 4px;
        padding: 4px 10px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #1D4ED8;
    }
    QPushButton:pressed {
        background-color: #1E40AF;
    }
    QPushButton:disabled {
        background-color: #93C5FD;
        color: #E5E7EB;
        border: 1px solid #93C5FD;
    }
    """

    def __init__(self, context: BudgetPalContext, logger: logging.Logger, log_emitter) -> None:
        super().__init__()
        self.context = context
        self.logger = logger
        self.log_emitter = log_emitter
        self.reporting_service = ReportingService(context.db)
        self.setStyleSheet(self.BUTTON_STYLESHEET)
        self.account_type_to_id: dict[str, int] = {}
        self.account_id_to_type: dict[int, str] = {}
        self._suppress_selection_autoload = False
        self._suppress_type_defaults = False
        self.sub_payments_dialog: SubPaymentsDialog | None = None
        self.bills_sort_key = "payment_due"

        self.setWindowTitle("BudgetPal")
        configured_width = int(self.context.settings["ui"]["window"].get("width", 1240))
        configured_height = int(self.context.settings["ui"]["window"].get("height", 820))
        self.resize(
            max(800, int(round(configured_width * 1.25))),
            configured_height,
        )

        self.tabs = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.transactions_tab = TransactionsTab()
        self.budget_tab = BudgetMonthTab()
        self.bills_tab = BillsTab()
        self.buckets_tab = BucketsTab()
        self.reports_tab = ReportsTab()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.transactions_tab, "Transactions")
        self.tabs.addTab(self.budget_tab, "Budget (Month)")
        self.tabs.addTab(self.bills_tab, "Bills")
        self.tabs.addTab(self.buckets_tab, "Savings Buckets")
        self.tabs.addTab(self.reports_tab, "Reports")
        self._init_central_layout()

        self._init_log_dock()
        self.setStatusBar(QStatusBar())
        today = date.today()
        self.transactions_view_year = today.year
        self.transactions_view_month = today.month
        self.bills_view_year = today.year
        self.bills_view_month = today.month

        self._populate_month_selectors()
        self._wire_events()
        self._refresh_transactions_month_filter(
            preferred_month=f"{self.transactions_view_year}-{self.transactions_view_month:02d}"
        )
        self._refresh_bills_month_filter(
            preferred_month=f"{self.bills_view_year}-{self.bills_view_month:02d}"
        )
        self._refresh_transaction_form_choices()
        self._clear_transaction_form()
        self._refresh_bill_form_choices()
        self.new_bill_form()
        self.refresh_transactions()
        self.refresh_bills()

        self.log_emitter.message.connect(self.append_log_message)
        self.logger.info("BudgetPal UI initialized")

    def _init_log_dock(self) -> None:
        dock = QDockWidget("Activity Log", self)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea)

        holder = QWidget()
        layout = QVBoxLayout(holder)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Operations, errors, and status events"))
        controls.addStretch(1)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._clear_log)
        controls.addWidget(clear_button)
        layout.addLayout(controls)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.document().setMaximumBlockCount(1000)
        layout.addWidget(self.log_area)

        dock.setWidget(holder)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def _init_central_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(12)

        self.logo_placeholder = QLabel("BudgetPal Logo (TBD)")
        self.logo_placeholder.setAlignment(Qt.AlignCenter)
        self.logo_placeholder.setFixedSize(180, 56)
        self.logo_placeholder.setStyleSheet(
            "border: 1px dashed #9CA3AF; color: #4B5563; background: #F9FAFB;"
        )
        header_layout.addWidget(self.logo_placeholder)

        self.app_title_label = QLabel("BudgetPal")
        # Let the system palette choose text color so contrast adapts to light/dark themes.
        self.app_title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        header_layout.addWidget(self.app_title_label)
        header_layout.addStretch(1)

        self.settings_button = QPushButton("Settings")
        self.about_button = QPushButton("About")
        self.exit_button = QPushButton("Exit")
        header_layout.addWidget(self.settings_button)
        header_layout.addWidget(self.about_button)
        header_layout.addWidget(self.exit_button)

        root_layout.addWidget(header_frame)
        root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

    def _populate_month_selectors(self) -> None:
        current = date.today()
        month_labels = []
        for offset in range(-3, 10):
            month = current.month + offset
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            month_labels.append(f"{year}-{month:02d}")

        selectors = [
            self.dashboard_tab.month_picker,
            self.budget_tab.month_picker,
            self.bills_tab.month_filter,
        ]
        for selector in selectors:
            selector.clear()
            selector.addItems(month_labels)
            selector.setCurrentText(f"{current.year}-{current.month:02d}")

    @staticmethod
    def _rolling_month_labels(months_back: int = 12, months_forward: int = 12) -> list[str]:
        current = date.today()
        labels: list[str] = []
        for offset in range(-months_back, months_forward + 1):
            month = current.month + offset
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            labels.append(f"{year}-{month:02d}")
        return labels

    def _wire_events(self) -> None:
        self.dashboard_tab.refresh_subs_button.clicked.connect(self.refresh_subscriptions)
        self.bills_tab.refresh_subtracker_button.clicked.connect(self.refresh_subscriptions)
        self.dashboard_tab.import_button.clicked.connect(self.import_transactions_xlsx)
        self.dashboard_tab.sub_payments_button.clicked.connect(self.show_sub_payments_dialog)
        self.transactions_tab.import_button.clicked.connect(self.import_transactions_xlsx)
        self.transactions_tab.add_button.clicked.connect(self.add_transaction)
        self.transactions_tab.save_button.clicked.connect(self.save_transaction)
        self.transactions_tab.delete_button.clicked.connect(self.delete_selected_transaction)
        self.transactions_tab.expenses_table.clicked.connect(self._on_expense_row_clicked)
        self.transactions_tab.income_table.clicked.connect(self._on_income_row_clicked)
        self.transactions_tab.expenses_table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_transaction_selection_changed()
        )
        self.transactions_tab.income_table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_transaction_selection_changed()
        )
        self.transactions_tab.month_filter.currentTextChanged.connect(self.on_transactions_month_changed)
        self.transactions_tab.expense_radio.toggled.connect(lambda checked: self._on_type_changed("expense", checked))
        self.transactions_tab.income_radio.toggled.connect(lambda checked: self._on_type_changed("income", checked))

        self.bills_tab.new_button.clicked.connect(self.new_bill_form)
        self.bills_tab.save_button.clicked.connect(self.save_bill)
        self.bills_tab.delete_button.clicked.connect(self.delete_bill)
        self.bills_tab.report_button.clicked.connect(self.export_bills_report)
        self.bills_tab.sort_name_button.clicked.connect(lambda: self.set_bills_sort("name"))
        self.bills_tab.sort_category_button.clicked.connect(lambda: self.set_bills_sort("category"))
        self.bills_tab.sort_due_button.clicked.connect(lambda: self.set_bills_sort("payment_due"))
        self.bills_tab.table.clicked.connect(self.on_bill_selection_changed)
        self.bills_tab.table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_bill_selection_changed()
        )
        self.bills_tab.month_filter.currentTextChanged.connect(self.on_bills_month_changed)
        self.dashboard_tab.month_picker.currentTextChanged.connect(self.on_dashboard_month_changed)
        self.reports_tab.run_button.clicked.connect(self.run_selected_report)
        self.reports_tab.export_button.clicked.connect(self.export_archive)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        self.about_button.clicked.connect(self.show_about_dialog)
        self.exit_button.clicked.connect(self.close)

    def import_transactions_xlsx(self) -> None:
        start_dir = self._import_dialog_start_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Transactions XLSX",
            start_dir,
            "Excel Files (*.xlsx *.xlsm *.xltx *.xltm);;All Files (*)",
        )
        if not file_path:
            return
        self._persist_last_import_dir(Path(file_path).parent)

        importer = XLSXTransactionImporter(
            self.context.transactions_service,
            self.context.categories_repo,
            self.context.accounts_repo,
        )

        try:
            result = importer.import_file(Path(file_path))
        except ValueError as exc:
            self.logger.error("XLSX import validation failed: %s", exc)
            QMessageBox.warning(self, "XLSX Import Error", str(exc))
            return
        except Exception as exc:
            self.logger.error("XLSX import failed: %s", exc)
            QMessageBox.critical(self, "XLSX Import Failed", str(exc))
            return

        month_text = result.import_period_key
        self._refresh_transactions_month_filter(preferred_month=month_text)
        self._refresh_bills_month_filter(preferred_month=month_text)
        self._refresh_transaction_form_choices()
        self.refresh_transactions()
        self.refresh_bills()
        filename = Path(file_path).name
        self.statusBar().showMessage(
            f"Imported {result.imported_count} transactions from {filename} "
            f"(replaced {result.deleted_count} prior rows for {month_text})",
            7000,
        )
        self.logger.info(
            "Imported %s transactions from %s, replaced %s rows for month: %s",
            result.imported_count,
            file_path,
            result.deleted_count,
            month_text,
        )

    def _import_dialog_start_dir(self) -> str:
        ui_settings = self.context.settings.get("ui", {})
        raw = str(ui_settings.get("last_import_dir", "")).strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return str(candidate)
        return str(Path.home())

    def _persist_last_import_dir(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
        except OSError:
            resolved = directory

        ui_settings = self.context.settings.setdefault("ui", {})
        new_value = str(resolved)
        if str(ui_settings.get("last_import_dir", "")).strip() == new_value:
            return

        ui_settings["last_import_dir"] = new_value
        try:
            get_settings_manager().save(self.context.settings)
        except OSError as exc:
            self.logger.error("Failed to save last import directory: %s", exc)

    def _selected_year_month(self, selector) -> tuple[int, int]:
        raw = selector.currentText().strip()
        year_str, month_str = raw.split("-")
        return int(year_str), int(month_str)

    def refresh_transactions(self) -> None:
        rows = self.context.transactions_service.list_for_month(
            year=self.transactions_view_year,
            month=self.transactions_view_month,
            limit=5000,
        )

        expense_rows: list[dict] = []
        income_rows: list[dict] = []
        for row in rows:
            data = dict(row)
            amount_cents = int(data.get("amount_cents") or 0)
            data["display_amount_cents"] = abs(amount_cents)
            data["description_display"] = self._normalized_display_text(data.get("description"))

            if data.get("txn_type") == "income" or amount_cents > 0:
                income_rows.append(data)
            elif data.get("txn_type") == "expense" or amount_cents < 0:
                expense_rows.append(data)

        expense_rows.sort(
            key=lambda r: (str(r.get("txn_date", "")), int(r.get("txn_id") or 0)),
        )
        income_rows.sort(
            key=lambda r: (str(r.get("txn_date", "")), int(r.get("txn_id") or 0)),
        )

        self.transactions_tab.expense_model.replace_rows(expense_rows)
        self.transactions_tab.income_model.replace_rows(income_rows)
        self.logger.info(
            "Loaded %s transactions for %s-%02d (%s expenses, %s income)",
            len(rows),
            self.transactions_view_year,
            self.transactions_view_month,
            len(expense_rows),
            len(income_rows),
        )

    def _set_transactions_view_month(self, year: int, month: int) -> None:
        self.transactions_view_year = year
        self.transactions_view_month = month
        self.transactions_tab.view_heading.setText(
            f"Transactions for {self.transactions_view_year}-{self.transactions_view_month:02d}"
        )

    def _set_bills_view_month(self, year: int, month: int) -> None:
        self.bills_view_year = year
        self.bills_view_month = month
        self.bills_tab.view_heading.setText(
            f"Bills for {self.bills_view_year}-{self.bills_view_month:02d}"
        )

    def _refresh_transactions_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.transactions_tab.month_filter.currentText().strip()
        months = self.context.transactions_service.list_available_months()
        default_month = date.today().strftime("%Y-%m")

        month_set = set(months)
        month_set.add(default_month)
        if preferred_month:
            month_set.add(preferred_month)
        month_values = sorted(month_set, reverse=True)

        self.transactions_tab.month_filter.blockSignals(True)
        self.transactions_tab.month_filter.clear()
        self.transactions_tab.month_filter.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.transactions_tab.month_filter.setCurrentText(target_month)
        self.transactions_tab.month_filter.blockSignals(False)

        year_str, month_str = target_month.split("-")
        self._set_transactions_view_month(int(year_str), int(month_str))

    def _refresh_bills_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.bills_tab.month_filter.currentText().strip()
        months = self.context.transactions_service.list_available_months()
        default_month = date.today().strftime("%Y-%m")

        month_set = set(months)
        month_set.update(self._rolling_month_labels(months_back=12, months_forward=12))
        month_set.add(default_month)
        if current_month:
            month_set.add(current_month)
        if preferred_month:
            month_set.add(preferred_month)
        month_values = sorted(month_set, reverse=True)

        self.bills_tab.month_filter.blockSignals(True)
        self.bills_tab.month_filter.clear()
        self.bills_tab.month_filter.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.bills_tab.month_filter.setCurrentText(target_month)
        self.bills_tab.month_filter.blockSignals(False)

        year_str, month_str = target_month.split("-")
        self._set_bills_view_month(int(year_str), int(month_str))

    def on_transactions_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        try:
            year_str, month_str = value.split("-")
            self._set_transactions_view_month(int(year_str), int(month_str))
        except ValueError:
            self.logger.warning("Invalid month filter value: %s", value)
            return
        self.refresh_transactions()

    def on_bills_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        try:
            year_str, month_str = value.split("-")
            self._set_bills_view_month(int(year_str), int(month_str))
        except ValueError:
            self.logger.warning("Invalid bills month filter value: %s", value)
            return
        self.refresh_bills()

    def on_dashboard_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        # Keep Bills month in sync with Dashboard month selection for planning workflows.
        self._refresh_bills_month_filter(preferred_month=value)
        self.refresh_bills()

    def _refresh_transaction_form_choices(self) -> None:
        selected_category_id = self.transactions_tab.category_input.currentData()
        selected_category_text = self._normalized_display_text(self.transactions_tab.category_input.currentText())
        selected_account_type = self._selected_account_type()

        self.transactions_tab.category_input.clear()
        self.transactions_tab.category_input.addItem("", None)
        for row in self.context.categories_repo.list_active():
            self.transactions_tab.category_input.addItem(str(row["name"]), int(row["category_id"]))

        self.account_type_to_id = {}
        self.account_id_to_type = {}
        for row in self.context.accounts_repo.list_active():
            account_type = str(row["account_type"]).strip().lower()
            account_id = int(row["account_id"])
            self.account_type_to_id[account_type] = account_id
            self.account_id_to_type[account_id] = account_type

        if selected_category_id is not None:
            self._combo_select_data(self.transactions_tab.category_input, selected_category_id)
        elif selected_category_text:
            self.transactions_tab.category_input.setEditText(selected_category_text)
        elif self.transactions_tab.category_input.count() > 0:
            self.transactions_tab.category_input.setCurrentIndex(0)
            self.transactions_tab.category_input.setEditText("")

        for account_type, radio in self.transactions_tab.account_radios.items():
            radio.setEnabled(account_type in self.account_type_to_id)

        if (
            selected_account_type
            and selected_account_type in self.transactions_tab.account_radios
            and selected_account_type in self.account_type_to_id
        ):
            self.transactions_tab.account_radios[selected_account_type].setChecked(True)
        else:
            preferred = ("checking", "cash", "credit", "savings")
            selected = False
            for account_type in preferred:
                if account_type in self.account_type_to_id:
                    self.transactions_tab.account_radios[account_type].setChecked(True)
                    selected = True
                    break
            if not selected:
                for account_type, radio in self.transactions_tab.account_radios.items():
                    if radio.isEnabled():
                        radio.setChecked(True)
                        break

    @staticmethod
    def _combo_select_data(combo, target_data: int | None) -> None:
        if target_data is None:
            if combo.count() > 0:
                combo.setCurrentIndex(0)
                if hasattr(combo, "setEditText"):
                    combo.setEditText("")
            return
        index = combo.findData(target_data)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _clear_transaction_form(self) -> None:
        self.transactions_tab.editing_txn_id = None
        self.transactions_tab.txn_date_input.setText(date.today().isoformat())
        self._suppress_type_defaults = True
        self.transactions_tab.expense_radio.setChecked(True)
        self._suppress_type_defaults = False
        self.transactions_tab.amount_input.clear()
        self.transactions_tab.description_input.clear()
        self.transactions_tab.note_input.clear()
        self.transactions_tab.payment_type_input.clear()
        self.transactions_tab.category_input.setCurrentIndex(0)
        self.transactions_tab.category_input.setEditText("")
        self.transactions_tab.subscription_checkbox.setChecked(False)
        self.transactions_tab.subscription_checkbox.setEnabled(True)
        self.transactions_tab.expenses_table.clearSelection()
        self.transactions_tab.income_table.clearSelection()
        self._apply_type_defaults("expense")

    def _refresh_bill_form_choices(self) -> None:
        selected_category_id = self.bills_tab.category_input.currentData()
        selected_category_text = self._normalized_display_text(self.bills_tab.category_input.currentText())

        self.bills_tab.category_input.clear()
        self.bills_tab.category_input.addItem("", None)
        for row in self.context.categories_repo.list_active():
            self.bills_tab.category_input.addItem(str(row["name"]), int(row["category_id"]))

        if selected_category_id is not None:
            self._combo_select_data(self.bills_tab.category_input, selected_category_id)
        elif selected_category_text:
            self.bills_tab.category_input.setEditText(selected_category_text)
        else:
            self.bills_tab.category_input.setCurrentIndex(0)
            self.bills_tab.category_input.setEditText("")

    def new_bill_form(self) -> None:
        self.bills_tab.editing_bill_id = None
        self.bills_tab.bill_name_input.clear()
        self.bills_tab.start_date_input.setText(date.today().isoformat())
        self.bills_tab.interval_count_input.setText("1")
        self.bills_tab.interval_unit_combo.setCurrentText("months")
        self.bills_tab.amount_input.clear()
        self.bills_tab.note_input.clear()
        self.bills_tab.category_input.setCurrentIndex(0)
        self.bills_tab.category_input.setEditText("")
        self.bills_tab.table.clearSelection()

    def _selected_bill_row(self) -> dict | None:
        selection = self.bills_tab.table.selectionModel().selectedRows()
        if not selection:
            return None
        return self.bills_tab.model.row_dict(selection[0].row())

    def on_bill_selection_changed(self) -> None:
        row = self._selected_bill_row()
        if row:
            self._load_bill_into_form(row)

    def _load_bill_into_form(self, row: dict) -> None:
        self.bills_tab.editing_bill_id = int(row.get("bill_id") or 0)
        self.bills_tab.bill_name_input.setText(self._normalized_display_text(row.get("name")))
        start_date = self._normalized_display_text(row.get("start_date"))
        self.bills_tab.start_date_input.setText(start_date or date.today().isoformat())
        self.bills_tab.interval_count_input.setText(str(int(row.get("interval_count") or 1)))
        raw_unit = self._normalized_display_text(row.get("interval_unit")) or "months"
        if raw_unit.endswith("s"):
            normalized_unit = raw_unit
        else:
            normalized_unit = f"{raw_unit}s"
        if self.bills_tab.interval_unit_combo.findText(normalized_unit) >= 0:
            self.bills_tab.interval_unit_combo.setCurrentText(normalized_unit)
        else:
            self.bills_tab.interval_unit_combo.setCurrentText("months")
        amount_cents = row.get("default_amount_cents")
        if amount_cents is None:
            self.bills_tab.amount_input.clear()
        else:
            self.bills_tab.amount_input.setText(f"{int(amount_cents) / 100:.2f}")
        self.bills_tab.note_input.setText(self._normalized_display_text(row.get("notes")))
        self._combo_select_data(self.bills_tab.category_input, row.get("category_id"))

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

    def _build_bill_payload(self) -> dict:
        name = self._normalized_display_text(self.bills_tab.bill_name_input.text())
        if not name:
            raise ValueError("Bill name is required.")

        start_date_text = self.bills_tab.start_date_input.text().strip()
        try:
            datetime.strptime(start_date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Start Date must be in YYYY-MM-DD format.") from exc

        interval_raw = self.bills_tab.interval_count_input.text().strip()
        if not interval_raw:
            raise ValueError("Interval is required.")
        try:
            interval_count = int(interval_raw)
        except ValueError as exc:
            raise ValueError("Interval must be a whole number.") from exc
        if interval_count < 1:
            raise ValueError("Interval must be at least 1.")

        interval_unit = self.bills_tab.interval_unit_combo.currentText().strip().lower()
        if interval_unit not in {"days", "weeks", "months", "years"}:
            raise ValueError("Interval unit must be days, weeks, months, or years.")

        amount_cents = self._parse_currency_cents_or_none(self.bills_tab.amount_input.text())

        category_id = self.bills_tab.category_input.currentData()
        if category_id is None:
            category_name = self._normalized_display_text(self.bills_tab.category_input.currentText())
            if category_name:
                existing = self.context.categories_repo.find_by_name(category_name)
                if existing:
                    category_id = int(existing["category_id"])
                else:
                    category_id = self.context.categories_repo.upsert(category_name, is_income=False)
                    self._refresh_bill_form_choices()
                    self._combo_select_data(self.bills_tab.category_input, category_id)

        return {
            "name": name,
            "start_date": start_date_text,
            "interval_count": interval_count,
            "interval_unit": interval_unit,
            "amount_cents": amount_cents,
            "category_id": int(category_id) if category_id is not None else None,
            "notes": self._normalized_display_text(self.bills_tab.note_input.text()) or None,
        }

    def save_bill(self) -> None:
        bill_id = self.bills_tab.editing_bill_id
        action_label = "Save Bill"

        try:
            payload = self._build_bill_payload()
            if bill_id:
                updated = self.context.bills_service.update_bill_definition(bill_id=bill_id, **payload)
                if not updated:
                    QMessageBox.warning(self, action_label, "Selected bill no longer exists.")
                    self.refresh_bills()
                    self.new_bill_form()
                    return
                self.logger.info("Updated bill %s", bill_id)
                self.statusBar().showMessage("Bill updated.", 3000)
            else:
                new_bill_id = self.context.bills_service.add_bill_definition(**payload)
                self.logger.info("Added bill %s", new_bill_id)
                self.statusBar().showMessage("Bill added.", 3000)
        except ValueError as exc:
            QMessageBox.warning(self, action_label, str(exc))
            return
        except Exception as exc:
            self.logger.error("Save bill failed: %s", exc)
            QMessageBox.critical(self, "Save Bill Failed", str(exc))
            return

        self.refresh_bills()
        self.new_bill_form()

    def delete_bill(self) -> None:
        row = self._selected_bill_row()
        if not row:
            QMessageBox.information(self, "Delete Bill", "Select a bill to delete.")
            return
        bill_id = int(row.get("bill_id") or 0)
        if not bill_id:
            QMessageBox.warning(self, "Delete Bill", "Invalid bill selection.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Bill",
            f"Delete bill '{row.get('name', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.context.bills_service.delete_bill_definition(bill_id)
        except Exception as exc:
            self.logger.error("Delete bill failed: %s", exc)
            QMessageBox.critical(self, "Delete Bill Failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Bill", "Selected bill no longer exists.")
        else:
            self.logger.info("Deleted bill %s", bill_id)
            self.statusBar().showMessage("Bill deleted.", 3000)

        self.refresh_bills()
        self.new_bill_form()

    def set_bills_sort(self, sort_key: str) -> None:
        self.bills_sort_key = sort_key
        self.refresh_bills()


    def _selected_account_type(self) -> str | None:
        for account_type, radio in self.transactions_tab.account_radios.items():
            if radio.isChecked():
                return account_type
        return None

    def _set_account_by_type(self, account_type: str) -> None:
        radio = self.transactions_tab.account_radios.get(account_type)
        if radio and radio.isEnabled():
            radio.setChecked(True)

    def _on_type_changed(self, txn_type: str, checked: bool) -> None:
        if not checked or self._suppress_type_defaults:
            return
        self._apply_type_defaults(txn_type)

    def _apply_type_defaults(self, txn_type: str) -> None:
        if txn_type == "income":
            self._set_account_by_type("checking")
            self.transactions_tab.subscription_checkbox.setChecked(False)
            self.transactions_tab.subscription_checkbox.setEnabled(False)
            self.transactions_tab.tax_checkbox.setChecked(True)
            return

        self._set_account_by_type("credit")
        self.transactions_tab.subscription_checkbox.setEnabled(True)
        self.transactions_tab.subscription_checkbox.setChecked(False)
        self.transactions_tab.tax_checkbox.setChecked(False)

    def _selected_transaction_row(self) -> dict | None:
        expense_selection = self.transactions_tab.expenses_table.selectionModel().selectedRows()
        income_selection = self.transactions_tab.income_table.selectionModel().selectedRows()
        if expense_selection:
            return self.transactions_tab.expense_model.row_dict(expense_selection[0].row())
        if income_selection:
            return self.transactions_tab.income_model.row_dict(income_selection[0].row())
        return None

    def _on_expense_row_clicked(self, index) -> None:
        if self._suppress_selection_autoload:
            return
        self.transactions_tab.income_table.clearSelection()
        row = self.transactions_tab.expense_model.row_dict(index.row())
        if row:
            self._load_transaction_into_form(row, show_status=False)

    def _on_income_row_clicked(self, index) -> None:
        if self._suppress_selection_autoload:
            return
        self.transactions_tab.expenses_table.clearSelection()
        row = self.transactions_tab.income_model.row_dict(index.row())
        if row:
            self._load_transaction_into_form(row, show_status=False)

    def on_transaction_selection_changed(self) -> None:
        if self._suppress_selection_autoload:
            return
        row = self._selected_transaction_row()
        if row:
            self._load_transaction_into_form(row, show_status=False)

    def _load_transaction_into_form(self, row: dict, show_status: bool = True) -> None:
        self.transactions_tab.editing_txn_id = int(row["txn_id"])
        amount_cents = int(row.get("amount_cents") or 0)
        self.transactions_tab.txn_date_input.setText(str(row.get("txn_date", "")))
        self._suppress_type_defaults = True
        if amount_cents > 0:
            self.transactions_tab.income_radio.setChecked(True)
        else:
            self.transactions_tab.expense_radio.setChecked(True)
        self._suppress_type_defaults = False
        self.transactions_tab.amount_input.setText(f"{abs(amount_cents) / 100:.2f}")
        self.transactions_tab.description_input.setText(
            self._normalized_display_text(row.get("description"))
        )
        self.transactions_tab.note_input.setText(
            self._normalized_display_text(row.get("note"))
        )
        self.transactions_tab.payment_type_input.setText(
            self._normalized_display_text(row.get("payment_type"))
        )
        self.transactions_tab.subscription_checkbox.setChecked(bool(row.get("is_subscription")))
        self.transactions_tab.subscription_checkbox.setEnabled(amount_cents <= 0)
        self.transactions_tab.tax_checkbox.setChecked(bool(row.get("tax_deductible")))
        self._combo_select_data(self.transactions_tab.category_input, row.get("category_id"))
        account_type = self.account_id_to_type.get(int(row.get("account_id") or 0))
        if account_type and account_type in self.transactions_tab.account_radios:
            self.transactions_tab.account_radios[account_type].setChecked(True)
        if show_status:
            self.statusBar().showMessage("Loaded selected transaction into editor.", 3000)

    @staticmethod
    def _parse_amount_cents(amount_text: str, txn_type_text: str) -> int:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            raise ValueError("Amount is required.")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric (example: 74.68).") from exc

        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents <= 0:
            raise ValueError("Amount must be greater than 0.")
        if txn_type_text.lower() == "expense":
            return -abs(cents)
        return abs(cents)

    def _build_transaction_input(self, existing: dict | None = None) -> TransactionInput:
        date_text = self.transactions_tab.txn_date_input.text().strip()
        if not date_text:
            raise ValueError("Date is required.")
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Date must be in yyyy-mm-dd format.") from exc

        txn_type_text = "Income" if self.transactions_tab.income_radio.isChecked() else "Expense"
        amount_cents = self._parse_amount_cents(self.transactions_tab.amount_input.text(), txn_type_text)
        description = self._normalized_display_text(self.transactions_tab.description_input.text())
        note_text = self._normalized_display_text(self.transactions_tab.note_input.text())
        payment_type = self._normalized_display_text(self.transactions_tab.payment_type_input.text())

        category_id = self.transactions_tab.category_input.currentData()
        if category_id is None:
            category_name = self.transactions_tab.category_input.currentText().strip()
            if not category_name:
                raise ValueError("Category is required.")
            existing_category = self.context.categories_repo.find_by_name(category_name)
            if existing_category:
                category_id = int(existing_category["category_id"])
            else:
                category_id = self.context.categories_repo.upsert(
                    category_name,
                    is_income=(txn_type_text.lower() == "income"),
                )

        account_type = self._selected_account_type()
        if not account_type:
            raise ValueError("Account is required.")
        account_id = self.account_type_to_id.get(account_type)
        if account_id is None:
            raise ValueError("Selected account is unavailable.")

        internal_payee = description or "Transaction"

        source_system = str((existing or {}).get("source_system") or "manual")
        source_uid = (existing or {}).get("source_uid") or f"manual:{uuid.uuid4()}"
        existing_import_period = str((existing or {}).get("import_period_key") or "").strip() or None
        if source_system == "xlsx_import":
            import_period_key = existing_import_period or date_text[:7]
        else:
            import_period_key = date_text[:7]
        tax_deductible = self.transactions_tab.tax_checkbox.isChecked()
        is_subscription = (
            self.transactions_tab.subscription_checkbox.isChecked()
            if txn_type_text.lower() == "expense"
            else False
        )
        tax_category = (existing or {}).get("tax_category")
        if tax_deductible and txn_type_text.lower() == "expense" and not tax_category:
            tax_category = "Other"
        if not tax_deductible or txn_type_text.lower() == "income":
            tax_category = None

        return TransactionInput(
            txn_date=date_text,
            amount_cents=amount_cents,
            txn_type="income" if amount_cents > 0 else "expense",
            payee=internal_payee,
            description=description or None,
            category_id=int(category_id),
            account_id=int(account_id),
            is_subscription=is_subscription,
            note=note_text or None,
            source_system=source_system,
            source_uid=str(source_uid),
            import_period_key=import_period_key,
            payment_type=payment_type or None,
            import_hash=(existing or {}).get("import_hash"),
            tax_deductible=tax_deductible,
            tax_category=tax_category,
            tax_note=(existing or {}).get("tax_note"),
            receipt_uri=(existing or {}).get("receipt_uri"),
            transfer_group_id=(existing or {}).get("transfer_group_id"),
        )

    @staticmethod
    def _normalized_display_text(value: object | None) -> str:
        text = str(value).strip() if value is not None else ""
        if text in {"...", "…"}:
            return ""
        return text

    def add_transaction(self) -> None:
        self.save_transaction(force_insert=True)

    def save_transaction(self, force_insert: bool = False) -> None:
        editing_txn_id = None if force_insert else self.transactions_tab.editing_txn_id
        existing = None
        if editing_txn_id is not None:
            existing = self.context.transactions_service.get_transaction(editing_txn_id)
            if existing is None:
                QMessageBox.warning(self, "Save Transaction", "The selected transaction no longer exists.")
                self._clear_transaction_form()
                self.refresh_transactions()
                return

        try:
            txn = self._build_transaction_input(existing=existing)
            if editing_txn_id is None:
                txn_id = self.context.transactions_service.add_transaction(txn)
                self.logger.info("Added transaction %s", txn_id)
                self.statusBar().showMessage("Transaction added.", 3000)
            else:
                updated = self.context.transactions_service.update_transaction(editing_txn_id, txn)
                if not updated:
                    QMessageBox.warning(self, "Save Transaction", "No transaction was updated.")
                    return
                self.logger.info("Updated transaction %s", editing_txn_id)
                self.statusBar().showMessage("Transaction updated.", 3000)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Transaction", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save transaction failed: %s", exc)
            QMessageBox.critical(self, "Save Transaction Failed", str(exc))
            return

        self._refresh_transaction_form_choices()
        self._refresh_transactions_month_filter(preferred_month=txn.txn_date[:7])
        self._suppress_selection_autoload = True
        try:
            self.refresh_transactions()
            self._clear_transaction_form()
        finally:
            self._suppress_selection_autoload = False

    def delete_selected_transaction(self) -> None:
        row = self._selected_transaction_row()
        if not row:
            QMessageBox.information(self, "Delete Transaction", "Select an expense or income row to delete.")
            return

        txn_id = int(row["txn_id"])
        answer = QMessageBox.question(
            self,
            "Delete Transaction",
            f"Delete selected transaction #{txn_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        deleted = self.context.transactions_service.delete_transaction(txn_id)
        if not deleted:
            QMessageBox.warning(self, "Delete Transaction", "The selected transaction no longer exists.")
        else:
            self.logger.info("Deleted transaction %s", txn_id)
            self.statusBar().showMessage("Transaction deleted.", 3000)

        self._refresh_transactions_month_filter(
            preferred_month=f"{self.transactions_view_year}-{self.transactions_view_month:02d}"
        )
        self.refresh_transactions()
        self._clear_transaction_form()

    @staticmethod
    def _build_bill_category_subtotals(rows: list[dict]) -> list[dict]:
        totals_by_category: dict[str, int] = {}
        for row in rows:
            category_name = str(row.get("category_name") or "Uncategorized").strip() or "Uncategorized"
            amount_cents = row.get("default_amount_cents")
            cents = int(amount_cents) if amount_cents is not None else 0
            totals_by_category[category_name] = totals_by_category.get(category_name, 0) + cents

        subtotal_rows: list[dict] = []
        for category_name, cents in totals_by_category.items():
            subtotal_rows.append(
                {
                    "category_name": category_name,
                    "subtotal_display": f"${cents / 100:.2f}",
                }
            )
        subtotal_rows.sort(
            key=lambda row: (
                str(row.get("category_name") or "").strip().casefold(),
                str(row.get("category_name") or "").strip(),
            )
        )
        return subtotal_rows

    def refresh_bills(self) -> None:
        rows = self.context.bills_service.list_bill_definitions(
            sort_by=self.bills_sort_key,
            year=self.bills_view_year,
            month=self.bills_view_month,
        )
        self.bills_tab.model.replace_rows(rows)
        subtotal_rows = self._build_bill_category_subtotals(rows)
        self.bills_tab.category_totals_model.replace_rows(subtotal_rows)
        total_cents = sum(int(row.get("default_amount_cents") or 0) for row in rows)
        self.bills_tab.total_subtotals_value_label.setText(f"${total_cents / 100:.2f}")
        self.logger.info(
            "Loaded %s recurring bills for %s-%02d (sort=%s)",
            len(rows),
            self.bills_view_year,
            self.bills_view_month,
            self.bills_sort_key,
        )

    @staticmethod
    def _truncate_report_text(value: str, max_len: int) -> str:
        text = str(value or "").strip()
        if max_len <= 0:
            return ""
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."

    def _write_bills_report_pdf(self, save_path: Path, rows: list[dict], subtotal_rows: list[dict]) -> None:
        writer = QPdfWriter(str(save_path))
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setResolution(120)
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)

        painter = QPainter()
        if not painter.begin(writer):
            raise OSError(f"Unable to create PDF at {save_path}")

        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        line_height = metrics.height() + 2
        page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
        left = page_rect.left()
        top = page_rect.top()
        bottom = page_rect.bottom()

        y = top + line_height

        def draw_line(line: str) -> None:
            nonlocal y
            if y > bottom - line_height:
                writer.newPage()
                painter.setFont(font)
                y = top + line_height
            painter.drawText(left, y, line)
            y += line_height

        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        draw_line(f"BudgetPal Bills Report - {month_label}")
        draw_line(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        draw_line("")

        draw_line("Section 1: Recurring Bills and Subscriptions")
        draw_line("Category         Name                   Payment Due Interval       Amount Note")
        draw_line("-------------------------------------------------------------------------------")
        for row in rows:
            category = self._truncate_report_text(str(row.get("category_name") or ""), 16)
            name = self._truncate_report_text(str(row.get("name") or ""), 22)
            payment_due = self._truncate_report_text(str(row.get("payment_due") or ""), 10)
            interval = self._truncate_report_text(str(row.get("interval_display") or ""), 12)
            amount = self._truncate_report_text(str(row.get("amount_display") or ""), 10)
            note = self._truncate_report_text(str(row.get("notes") or ""), 26)
            line = f"{category:<16} {name:<22} {payment_due:<10} {interval:<12} {amount:>10} {note}"
            draw_line(line)

        draw_line("")
        draw_line("Section 2: Category Sub-Totals")
        draw_line("Category                             Subtotal")
        draw_line("--------------------------------------------------")
        for row in subtotal_rows:
            category = self._truncate_report_text(str(row.get("category_name") or ""), 34)
            subtotal = self._truncate_report_text(str(row.get("subtotal_display") or ""), 12)
            draw_line(f"{category:<34} {subtotal:>12}")

        painter.end()

    def export_bills_report(self) -> None:
        start_dir = self._bills_report_dialog_start_dir()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bills Report PDF",
            str(Path(start_dir) / "budgetpal_bills_report.pdf"),
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not file_path:
            return

        save_path = Path(file_path)
        if save_path.suffix.lower() != ".pdf":
            save_path = save_path.with_suffix(".pdf")
        self._persist_last_bills_report_dir(save_path.parent)

        rows = self.context.bills_service.list_bill_definitions(
            sort_by=self.bills_sort_key,
            year=self.bills_view_year,
            month=self.bills_view_month,
        )
        subtotal_rows = self._build_bill_category_subtotals(rows)

        try:
            self._write_bills_report_pdf(save_path, rows, subtotal_rows)
        except OSError as exc:
            self.logger.error("Bills report export failed: %s", exc)
            QMessageBox.critical(self, "Bills Report Export Failed", str(exc))
            return

        self.logger.info("Exported bills report PDF to %s (%s rows, %s subtotals)", save_path, len(rows), len(subtotal_rows))
        self.statusBar().showMessage(f"Bills report saved: {save_path.name}", 5000)

    def _bills_report_dialog_start_dir(self) -> str:
        ui_settings = self.context.settings.get("ui", {})
        raw = str(ui_settings.get("last_bills_report_dir", "")).strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return str(candidate)

        import_dir = str(ui_settings.get("last_import_dir", "")).strip()
        if import_dir:
            candidate = Path(import_dir).expanduser()
            if candidate.exists():
                return str(candidate)
        return str(Path.home())

    def _persist_last_bills_report_dir(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
        except OSError:
            resolved = directory

        ui_settings = self.context.settings.setdefault("ui", {})
        new_value = str(resolved)
        if str(ui_settings.get("last_bills_report_dir", "")).strip() == new_value:
            return

        ui_settings["last_bills_report_dir"] = new_value
        try:
            get_settings_manager().save(self.context.settings)
        except OSError as exc:
            self.logger.error("Failed to save last bills report directory: %s", exc)

    def refresh_subscriptions(self) -> None:
        if not self.context.subscriptions_service:
            message = (
                "SubTracker DB path is not configured in budgetpal_config.json "
                "under subtracker.database_path"
            )
            self.logger.error(message)
            QMessageBox.warning(self, "SubTracker Not Configured", message)
            return

        try:
            count = self.context.subscriptions_service.refresh_subtracker_bills(
                year=self.bills_view_year,
                month=self.bills_view_month,
            )
            mapping_errors = list(getattr(self.context.subscriptions_service, "last_mapping_errors", []))
            if mapping_errors:
                preview = "\n".join(mapping_errors[:5])
                if len(mapping_errors) > 5:
                    preview += f"\n...and {len(mapping_errors) - 5} more."
                self.logger.error(
                    "SubTracker category mapping fallback occurred for %s rows.",
                    len(mapping_errors),
                )
                QMessageBox.warning(
                    self,
                    "SubTracker Category Mapping Warning",
                    "Some SubTracker category IDs do not match BudgetPal categories.\n"
                    "Those subscriptions were assigned to Uncategorized.\n\n"
                    f"{preview}",
                )
            self.logger.info("Refreshed %s active subscriptions from SubTracker", count)
            self.statusBar().showMessage(
                f"Refreshed {count} active subscriptions from SubTracker",
                4000,
            )
            self.refresh_bills()
        except SubTrackerIntegrationError as exc:
            self.logger.error("SubTracker integration failed: %s", exc)
            QMessageBox.critical(self, "SubTracker Integration Error", str(exc))

    def show_sub_payments_dialog(self) -> None:
        if not self.context.subscription_payments_service:
            message = (
                "SubTracker DB path is not configured in budgetpal_config.json "
                "under subtracker.database_path"
            )
            QMessageBox.warning(self, "Sub Payments Unavailable", message)
            return

        if self.sub_payments_dialog is None:
            self.sub_payments_dialog = SubPaymentsDialog(
                service=self.context.subscription_payments_service,
                logger=self.logger,
                parent=self,
            )
            self.sub_payments_dialog.setAttribute(Qt.WA_DeleteOnClose, False)

        self.sub_payments_dialog.open_month(self.transactions_view_year, self.transactions_view_month)
        self.sub_payments_dialog.show()
        self.sub_payments_dialog.raise_()
        self.sub_payments_dialog.activateWindow()

    def run_selected_report(self) -> None:
        report_name = self.reports_tab.report_picker.currentText()
        year = int(self.reports_tab.year_picker.currentText())
        if report_name == "Tax deductible summary":
            rows = self.context.tax_service.summary(year)
            lines = [
                f"{r['tax_category']}: {r['total_cents']} cents ({r['txn_count']} txns)"
                for r in rows
            ]
        elif report_name == "Tax deductible detail":
            rows = self.context.tax_service.detail(year)
            lines = [
                f"{r['txn_date']} | {r['description']} | {r['amount_cents']} | {r['tax_category'] or '-'}"
                for r in rows
            ]
        else:
            lines = ["Monthly budget summary placeholder"]

        self.reports_tab.output.setPlainText("\n".join(lines) if lines else "No results")
        self.logger.info("Generated report '%s'", report_name)

    def export_archive(self) -> None:
        export_path = self.reporting_service.export_archive()
        self.logger.info("Exported archive to %s", export_path)
        self.statusBar().showMessage(f"Exported archive: {export_path}", 6000)

    @staticmethod
    def _extract_log_level(message: str) -> str:
        parts = [part.strip() for part in message.split("|", 3)]
        if len(parts) >= 2 and parts[1]:
            return parts[1].upper()
        return "INFO"

    def append_log_message(self, message: str) -> None:
        level = self._extract_log_level(message)
        color_hex = self.LOG_LEVEL_COLORS.get(level, self.LOG_LEVEL_COLORS["DEFAULT"])
        self.log_area.setTextColor(QColor(color_hex))
        self.log_area.append(message)
        self.log_area.setTextColor(QColor(self.LOG_LEVEL_COLORS["DEFAULT"]))

    def _clear_log(self) -> None:
        self.log_area.clear()
        self.logger.info("Activity log cleared by user")

    def show_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            settings=self.context.settings,
            categories_repo=self.context.categories_repo,
            parent=self,
        )
        accepted = bool(dialog.exec())

        if dialog.categories_dirty:
            self._refresh_transaction_form_choices()
            self._refresh_bill_form_choices()
            self.refresh_transactions()
            self.refresh_bills()
            self.logger.info("Categories updated from Settings dialog")

        if not accepted:
            return

        new_settings = dialog.settings_value()
        old_db_path = str(self.context.settings.get("database", {}).get("path", "")).strip()
        old_subtracker_db_path = str(
            self.context.settings.get("subtracker", {}).get("database_path", "")
        ).strip()
        old_window_cfg = self.context.settings.get("ui", {}).get("window", {})
        old_window_width = int(old_window_cfg.get("width", 1240))
        old_window_height = int(old_window_cfg.get("height", 820))

        settings_mgr = get_settings_manager()
        try:
            settings_mgr.save(new_settings)
        except OSError as exc:
            self.logger.error("Failed to save settings: %s", exc)
            QMessageBox.critical(
                self,
                "Settings Save Error",
                "BudgetPal could not write the settings file.\n\n"
                f"{exc}\n\n"
                "Check file permissions and try again.",
            )
            return
        self.context.refresh_settings(new_settings)

        window_cfg = new_settings.get("ui", {}).get("window", {})
        configured_width = int(window_cfg.get("width", 1240))
        configured_height = int(window_cfg.get("height", 820))
        if configured_width != old_window_width or configured_height != old_window_height:
            self.resize(max(800, int(round(configured_width * 1.25))), configured_height)

        level_name = str(new_settings.get("logging", {}).get("level", "INFO")).upper()
        self.logger.setLevel(getattr(logging, level_name, logging.INFO))

        new_db_path = str(new_settings.get("database", {}).get("path", "")).strip()
        new_subtracker_db_path = str(new_settings.get("subtracker", {}).get("database_path", "")).strip()
        restart_needed = old_db_path != new_db_path
        subtracker_changed = old_subtracker_db_path != new_subtracker_db_path

        self.logger.info("Settings saved to config file")
        if restart_needed:
            self.statusBar().showMessage(
                "Settings saved. Restart required for BudgetPal DB path changes.",
                7000,
            )
            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings saved to config.\n\n"
                "Restart BudgetPal to apply the new BudgetPal database path.",
            )
        else:
            self.statusBar().showMessage("Settings saved.", 4000)

        if subtracker_changed:
            if self.sub_payments_dialog is not None:
                self.sub_payments_dialog.close()
                self.sub_payments_dialog = None
            self.logger.info("SubTracker path updated; integration binding refreshed")

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About BudgetPal",
            "BudgetPal\n"
            "Local-first household budgeting app.\n\n"
            "Build status: MVP foundation.",
        )
