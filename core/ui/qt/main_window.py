from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPixmap
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
from core.build_info import load_build_info
from core.domain import TransactionInput
from core.importers.subtracker_view import SubTrackerIntegrationError
from core.importers.xlsx_transactions import XLSXTransactionImporter
from core.path_registry import BudgetPalPathRegistry
from core.services.help_service import HelpService
from core.services.reporting import ReportingService
from core.settings import get_settings_manager
from core.ui.qt.budget_category_definitions_dialog import BudgetCategoryDefinitionsDialog
from core.ui.qt.income_definitions_dialog import IncomeDefinitionsDialog
from core.ui.qt.recurring_definitions_dialog import RecurringDefinitionsDialog
from core.ui.qt.settings_dialog import SettingsDialog
from core.ui.qt.sub_payments_dialog import SubPaymentsDialog
from core.ui.qt.tabs.balance_checking import BalanceCheckingTab
from core.ui.qt.tabs.bills import BillsTab
from core.ui.qt.tabs.buckets import BucketsTab
from core.ui.qt.tabs.budget_month import BudgetMonthTab
from core.ui.qt.tabs.dashboard import DashboardTab
from core.ui.qt.tabs.income import IncomeTab
from core.ui.qt.tabs.reports import ReportPreviewDialog, ReportsTab
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
        self.help_service = HelpService()
        self.setStyleSheet(self.BUTTON_STYLESHEET)
        self.account_type_to_id: dict[str, int] = {}
        self.account_id_to_type: dict[int, str] = {}
        self._suppress_selection_autoload = False
        self._suppress_type_defaults = False
        self.sub_payments_dialog: SubPaymentsDialog | None = None
        self.bill_definitions_dialog: RecurringDefinitionsDialog | None = None
        self.income_definitions_dialog: IncomeDefinitionsDialog | None = None
        self.budget_definitions_dialog: BudgetCategoryDefinitionsDialog | None = None
        self.bills_sort_key = "payment_due"
        self.income_sort_key = "description"
        self.budget_sort_key = "category"
        self._editing_bill_source_system: str | None = None
        self._bills_dirty_by_month: dict[str, bool] = {}
        self._subscriptions_dirty_by_month: dict[str, bool] = {}
        self._income_dirty_by_month: dict[str, bool] = {}
        self._budget_dirty_by_month: dict[str, bool] = {}
        self._loading_dashboard_starting_balance = False
        self._loading_checking_beginning_balance = False
        self._open_report_previews: list[ReportPreviewDialog] = []

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
        self.balance_checking_tab = BalanceCheckingTab()
        self.budget_tab = BudgetMonthTab()
        self.bills_tab = BillsTab()
        self.income_tab = IncomeTab()
        self.buckets_tab = BucketsTab()
        self.reports_tab = ReportsTab()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.transactions_tab, "Transactions")
        self.tabs.addTab(self.income_tab, "Income")
        self.tabs.addTab(self.bills_tab, "Bills")
        self.tabs.addTab(self.budget_tab, "Budget Allocations")
        self.tabs.addTab(self.balance_checking_tab, "Balance Checking")
        self.tabs.addTab(self.buckets_tab, "Savings")
        self.tabs.addTab(self.reports_tab, "Reports")
        self._init_central_layout()

        self._init_log_dock()
        self.setStatusBar(QStatusBar())
        today = date.today()
        self.transactions_view_year = today.year
        self.transactions_view_month = today.month
        self.budget_view_year = today.year
        self.budget_view_month = today.month
        self.balance_checking_view_year = today.year
        self.balance_checking_view_month = today.month
        self.bills_view_year = today.year
        self.bills_view_month = today.month
        self.income_view_year = today.year
        self.income_view_month = today.month

        self._populate_month_selectors()
        self._wire_events()
        self._refresh_dashboard_month_filter(
            preferred_month=f"{today.year}-{today.month:02d}"
        )
        self._refresh_transactions_month_filter(
            preferred_month=f"{self.transactions_view_year}-{self.transactions_view_month:02d}"
        )
        self._refresh_balance_checking_month_filter(
            preferred_month=f"{self.balance_checking_view_year}-{self.balance_checking_view_month:02d}"
        )
        self._refresh_budget_month_filter(
            preferred_month=f"{self.budget_view_year}-{self.budget_view_month:02d}"
        )
        self._refresh_bills_month_filter(
            preferred_month=f"{self.bills_view_year}-{self.bills_view_month:02d}"
        )
        self._refresh_income_month_filter(
            preferred_month=f"{self.income_view_year}-{self.income_view_month:02d}"
        )
        self._sync_reports_period_from_dashboard(
            preferred_month=f"{today.year}-{today.month:02d}"
        )
        self._refresh_transaction_form_choices()
        self._clear_transaction_form()
        self._refresh_budget_form_choices()
        self._refresh_bill_form_choices()
        self._refresh_income_form_choices()
        self.new_budget_form()
        self.new_bill_form()
        self.new_income_form()
        self.refresh_transactions()
        self.refresh_balance_checking()
        self.refresh_budget_allocations()
        self.refresh_bills()
        self.refresh_income()
        self.refresh_dashboard()

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
        root_layout.setContentsMargins(2, 8, 8, 8)
        root_layout.setSpacing(8)

        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(24, 4, 10, 4)
        header_layout.setSpacing(24)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(110, 110)
        logo_path = BudgetPalPathRegistry.logo_image_file()
        if logo_path and logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                self.logo_label.setPixmap(
                    pixmap.scaled(
                        self.logo_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            else:
                self.logo_label.setText("BudgetPal")
        else:
            self.logo_label.setText("BudgetPal")
        header_layout.addWidget(self.logo_label)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        self.app_title_label = QLabel("BudgetPal")
        # Let the system palette choose text color so contrast adapts to light/dark themes.
        self.app_title_label.setStyleSheet("font-size: 30px; font-weight: 700;")

        title_layout.addWidget(self.app_title_label)

        header_layout.addWidget(title_block)
        header_layout.addStretch(1)

        self.help_button = QPushButton("Help")
        self.settings_button = QPushButton("Settings")
        self.about_button = QPushButton("About")
        self.exit_button = QPushButton("Exit")
        header_layout.addWidget(self.help_button)
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
            self.budget_tab.month_picker,
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
        self.bills_tab.refresh_subtracker_button.clicked.connect(self.refresh_subscriptions)
        self.dashboard_tab.starting_balance_input.editingFinished.connect(self.save_dashboard_starting_balance)
        self.transactions_tab.import_button.clicked.connect(self.import_transactions_xlsx)
        self.transactions_tab.sub_payments_button.clicked.connect(self.show_sub_payments_dialog)
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
        self.balance_checking_tab.month_filter.currentTextChanged.connect(self.on_balance_checking_month_changed)
        self.balance_checking_tab.save_beginning_balance_button.clicked.connect(
            self.save_balance_checking_beginning_balance
        )
        self.balance_checking_tab.beginning_balance_input.editingFinished.connect(
            self.save_balance_checking_beginning_balance
        )
        self.balance_checking_tab.clear_all_button.clicked.connect(self.clear_all_balance_checking_rows)
        self.balance_checking_tab.reset_all_button.clicked.connect(self.reset_all_balance_checking_rows)
        self.balance_checking_tab.table.clicked.connect(self.on_balance_checking_table_clicked)
        self.balance_checking_tab.model.txn_cleared_toggled.connect(
            self.on_balance_checking_cleared_toggled
        )

        self.budget_tab.save_button.clicked.connect(self.save_budget_allocation)
        self.budget_tab.delete_button.clicked.connect(self.delete_budget_allocation)
        self.budget_tab.definitions_button.clicked.connect(self.show_budget_definitions_dialog)
        self.budget_tab.refresh_button.clicked.connect(self.refresh_budget_for_selected_month)
        self.budget_tab.table.clicked.connect(self.on_budget_selection_changed)
        self.budget_tab.table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_budget_selection_changed()
        )
        self.budget_tab.month_picker.currentTextChanged.connect(self.on_budget_month_changed)

        self.bills_tab.save_button.clicked.connect(self.save_bill)
        self.bills_tab.delete_button.clicked.connect(self.delete_bill)
        self.bills_tab.refresh_bills_button.clicked.connect(self.refresh_bills_for_selected_month)
        self.bills_tab.bill_definitions_button.clicked.connect(self.show_bill_definitions_dialog)
        self.bills_tab.sort_name_button.clicked.connect(lambda: self.set_bills_sort("name"))
        self.bills_tab.sort_category_button.clicked.connect(lambda: self.set_bills_sort("category"))
        self.bills_tab.sort_due_button.clicked.connect(lambda: self.set_bills_sort("payment_due"))
        self.bills_tab.table.clicked.connect(self.on_bill_selection_changed)
        self.bills_tab.table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_bill_selection_changed()
        )
        self.bills_tab.month_filter.currentTextChanged.connect(self.on_bills_month_changed)
        self.income_tab.save_button.clicked.connect(self.save_income)
        self.income_tab.delete_button.clicked.connect(self.delete_income)
        self.income_tab.refresh_income_button.clicked.connect(self.refresh_income_for_selected_month)
        self.income_tab.income_definitions_button.clicked.connect(self.show_income_definitions_dialog)
        self.income_tab.sort_category_button.clicked.connect(lambda: self.set_income_sort("category"))
        self.income_tab.sort_description_button.clicked.connect(lambda: self.set_income_sort("description"))
        self.income_tab.sort_account_button.clicked.connect(lambda: self.set_income_sort("account"))
        self.income_tab.table.clicked.connect(self.on_income_selection_changed)
        self.income_tab.table.selectionModel().selectionChanged.connect(
            lambda *_: self.on_income_selection_changed()
        )
        self.income_tab.month_filter.currentTextChanged.connect(self.on_income_month_changed)
        self.dashboard_tab.month_picker.currentTextChanged.connect(self.on_dashboard_month_changed)
        self.reports_tab.run_button.clicked.connect(self.run_selected_report)
        self.help_button.clicked.connect(self.show_help)
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
        self._refresh_dashboard_month_filter(preferred_month=month_text)
        self._refresh_transactions_month_filter(preferred_month=month_text)
        self._refresh_balance_checking_month_filter(preferred_month=month_text)
        self._refresh_budget_month_filter(preferred_month=month_text)
        self._refresh_bills_month_filter(preferred_month=month_text)
        self._refresh_transaction_form_choices()
        self.budget_tab.month_picker.blockSignals(True)
        self.budget_tab.month_picker.setCurrentText(month_text)
        self.budget_tab.month_picker.blockSignals(False)
        self.dashboard_tab.month_picker.blockSignals(True)
        self.dashboard_tab.month_picker.setCurrentText(month_text)
        self.dashboard_tab.month_picker.blockSignals(False)
        self._sync_reports_period_from_dashboard(preferred_month=month_text)
        self.refresh_transactions()
        self.refresh_balance_checking()
        self.refresh_budget_allocations()
        self.refresh_bills()
        self.refresh_income()
        self.refresh_dashboard()
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
        self.refresh_dashboard()

    def refresh_balance_checking(self) -> None:
        beginning_balance_cents = self.context.transactions_service.get_checking_month_beginning_balance(
            year=self.balance_checking_view_year,
            month=self.balance_checking_view_month,
        )
        self._loading_checking_beginning_balance = True
        try:
            self.balance_checking_tab.beginning_balance_input.setText(
                f"{beginning_balance_cents / 100:.2f}"
            )
        finally:
            self._loading_checking_beginning_balance = False

        rows = self.context.transactions_service.list_checking_ledger_for_month(
            year=self.balance_checking_view_year,
            month=self.balance_checking_view_month,
            limit=10000,
        )
        running_balance_cents = int(beginning_balance_cents)
        table_rows: list[dict] = []
        for row in rows:
            data = dict(row)
            txn_type = str(data.get("txn_type") or "").strip().lower()
            raw_amount_cents = int(data.get("amount_cents") or 0)
            if txn_type == "income":
                signed_amount_cents = abs(raw_amount_cents)
            elif txn_type == "expense":
                signed_amount_cents = -abs(raw_amount_cents)
            else:
                signed_amount_cents = raw_amount_cents

            running_balance_cents += signed_amount_cents
            data["payment_type_display"] = self._normalized_display_text(data.get("payment_type"))
            data["description_display"] = self._normalized_display_text(data.get("description"))
            data["note_display"] = self._normalized_display_text(data.get("note"))
            data["amount_display"] = self._format_currency_signed(signed_amount_cents)
            data["running_balance_display"] = self._format_currency_balance(running_balance_cents)
            table_rows.append(data)

        self.balance_checking_tab.model.replace_rows(table_rows)
        self.logger.info(
            "Loaded %s checking ledger rows for %s-%02d",
            len(table_rows),
            self.balance_checking_view_year,
            self.balance_checking_view_month,
        )

    def save_balance_checking_beginning_balance(self) -> None:
        if self._loading_checking_beginning_balance:
            return
        try:
            beginning_balance_cents = self._parse_currency_cents_allow_negative(
                self.balance_checking_tab.beginning_balance_input.text()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Beginning Balance", str(exc))
            self.refresh_balance_checking()
            return

        self.context.transactions_service.set_checking_month_beginning_balance(
            year=self.balance_checking_view_year,
            month=self.balance_checking_view_month,
            beginning_balance_cents=beginning_balance_cents,
        )
        self.statusBar().showMessage(
            f"Saved checking beginning balance for {self.balance_checking_view_year:04d}-{self.balance_checking_view_month:02d}.",
            3000,
        )
        self.refresh_balance_checking()

    def on_balance_checking_cleared_toggled(self, txn_id: int, is_cleared: bool) -> None:
        updated = self.context.transactions_service.set_transaction_cleared(
            txn_id=int(txn_id),
            is_cleared=bool(is_cleared),
        )
        if not updated:
            QMessageBox.warning(
                self,
                "Update Cleared Status",
                "The selected transaction no longer exists.",
            )
            self.refresh_balance_checking()
            return
        self.logger.info("Updated transaction %s cleared status to %s", txn_id, int(is_cleared))
        self.statusBar().showMessage("Updated cleared status.", 3000)
        self.refresh_balance_checking()
        self.refresh_transactions()

    def on_balance_checking_table_clicked(self, index) -> None:
        if not index.isValid() or int(index.column()) != 6:
            return
        row = self.balance_checking_tab.model.row_dict(index.row())
        if not row:
            return
        txn_id = int(row.get("txn_id") or 0)
        if txn_id <= 0:
            return
        current = bool(row.get("is_cleared"))
        self.on_balance_checking_cleared_toggled(txn_id, not current)

    def _set_all_balance_checking_rows(self, is_cleared: bool) -> None:
        changed = 0
        model = self.balance_checking_tab.model
        for index in range(model.rowCount()):
            row = model.row_dict(index) or {}
            txn_id = int(row.get("txn_id") or 0)
            if txn_id <= 0:
                continue
            current = bool(row.get("is_cleared"))
            if current == bool(is_cleared):
                continue
            updated = self.context.transactions_service.set_transaction_cleared(
                txn_id=txn_id,
                is_cleared=bool(is_cleared),
            )
            if updated:
                changed += 1
        if changed:
            self.refresh_balance_checking()
            self.refresh_transactions()
        self.statusBar().showMessage(
            f"Updated {changed} checking rows.",
            3000,
        )

    def clear_all_balance_checking_rows(self) -> None:
        self._set_all_balance_checking_rows(False)

    def reset_all_balance_checking_rows(self) -> None:
        self._set_all_balance_checking_rows(True)

    def _set_transactions_view_month(self, year: int, month: int) -> None:
        self.transactions_view_year = year
        self.transactions_view_month = month
        self.transactions_tab.view_heading.setText(
            f"Transactions for {self.transactions_view_year}-{self.transactions_view_month:02d}"
        )

    def _set_budget_view_month(self, year: int, month: int) -> None:
        self.budget_view_year = year
        self.budget_view_month = month
        self.budget_tab.view_heading.setText(
            f"Budget Allocations for {self.budget_view_year}-{self.budget_view_month:02d}"
        )

    def _set_balance_checking_view_month(self, year: int, month: int) -> None:
        self.balance_checking_view_year = year
        self.balance_checking_view_month = month
        self.balance_checking_tab.view_heading.setText(
            f"Balance Checking for {self.balance_checking_view_year}-{self.balance_checking_view_month:02d}"
        )

    def _set_bills_view_month(self, year: int, month: int) -> None:
        self.bills_view_year = year
        self.bills_view_month = month
        self.bills_tab.view_heading.setText(
            f"Bills for {self.bills_view_year}-{self.bills_view_month:02d}"
        )

    def _set_income_view_month(self, year: int, month: int) -> None:
        self.income_view_year = year
        self.income_view_month = month
        self.income_tab.view_heading.setText(
            f"Income for {self.income_view_year}-{self.income_view_month:02d}"
        )

    @staticmethod
    def _month_key(year: int, month: int) -> str:
        return f"{int(year):04d}-{int(month):02d}"

    @staticmethod
    def _normalized_source_system(source_system: str | None) -> str:
        source = str(source_system or "").strip().lower()
        if source == "subtracker":
            return "subtracker"
        return "budgetpal"

    def _mark_bills_month_dirty(self, year: int, month: int, source_system: str | None) -> None:
        key = self._month_key(year, month)
        source = self._normalized_source_system(source_system)
        if source == "subtracker":
            self._subscriptions_dirty_by_month[key] = True
        else:
            self._bills_dirty_by_month[key] = True

    def _is_bills_month_dirty(self, year: int, month: int) -> bool:
        key = self._month_key(year, month)
        return bool(self._bills_dirty_by_month.get(key) or self._subscriptions_dirty_by_month.get(key))

    def _is_subscriptions_month_dirty(self, year: int, month: int) -> bool:
        key = self._month_key(year, month)
        return bool(self._subscriptions_dirty_by_month.get(key))

    def _clear_bills_month_dirty(self, year: int, month: int, source_system: str | None = None) -> None:
        key = self._month_key(year, month)
        if source_system is None:
            self._bills_dirty_by_month[key] = False
            self._subscriptions_dirty_by_month[key] = False
            return
        source = self._normalized_source_system(source_system)
        if source == "subtracker":
            self._subscriptions_dirty_by_month[key] = False
        else:
            self._bills_dirty_by_month[key] = False

    def _mark_income_month_dirty(self, year: int, month: int) -> None:
        key = self._month_key(year, month)
        self._income_dirty_by_month[key] = True

    def _is_income_month_dirty(self, year: int, month: int) -> bool:
        key = self._month_key(year, month)
        return bool(self._income_dirty_by_month.get(key))

    def _clear_income_month_dirty(self, year: int, month: int) -> None:
        key = self._month_key(year, month)
        self._income_dirty_by_month[key] = False

    def _mark_budget_month_dirty(self, year: int, month: int) -> None:
        key = self._month_key(year, month)
        self._budget_dirty_by_month[key] = True

    def _is_budget_month_dirty(self, year: int, month: int) -> bool:
        key = self._month_key(year, month)
        return bool(self._budget_dirty_by_month.get(key))

    def _clear_budget_month_dirty(self, year: int, month: int) -> None:
        key = self._month_key(year, month)
        self._budget_dirty_by_month[key] = False

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

    def _refresh_budget_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.budget_tab.month_picker.currentText().strip()
        months = self.context.transactions_service.list_available_months()
        months.extend(self.context.budget_allocations_service.list_available_months())
        default_month = date.today().strftime("%Y-%m")

        month_set = set(months)
        month_set.update(self._rolling_month_labels(months_back=12, months_forward=12))
        month_set.add(default_month)
        if current_month:
            month_set.add(current_month)
        if preferred_month:
            month_set.add(preferred_month)
        month_values = sorted(month_set, reverse=True)

        self.budget_tab.month_picker.blockSignals(True)
        self.budget_tab.month_picker.clear()
        self.budget_tab.month_picker.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.budget_tab.month_picker.setCurrentText(target_month)
        self.budget_tab.month_picker.blockSignals(False)

        year_str, month_str = target_month.split("-")
        self._set_budget_view_month(int(year_str), int(month_str))

    def _refresh_balance_checking_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.balance_checking_tab.month_filter.currentText().strip()
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

        self.balance_checking_tab.month_filter.blockSignals(True)
        self.balance_checking_tab.month_filter.clear()
        self.balance_checking_tab.month_filter.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.balance_checking_tab.month_filter.setCurrentText(target_month)
        self.balance_checking_tab.month_filter.blockSignals(False)

        year_str, month_str = target_month.split("-")
        self._set_balance_checking_view_month(int(year_str), int(month_str))

    def _refresh_dashboard_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.dashboard_tab.month_picker.currentText().strip()
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

        self.dashboard_tab.month_picker.blockSignals(True)
        self.dashboard_tab.month_picker.clear()
        self.dashboard_tab.month_picker.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.dashboard_tab.month_picker.setCurrentText(target_month)
        self.dashboard_tab.month_picker.blockSignals(False)

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

    def _refresh_income_month_filter(self, preferred_month: str | None = None) -> None:
        current_month = self.income_tab.month_filter.currentText().strip()
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

        self.income_tab.month_filter.blockSignals(True)
        self.income_tab.month_filter.clear()
        self.income_tab.month_filter.addItems(month_values)

        target_month = preferred_month or current_month or default_month
        if target_month not in month_set:
            target_month = month_values[0]
        self.income_tab.month_filter.setCurrentText(target_month)
        self.income_tab.month_filter.blockSignals(False)

        year_str, month_str = target_month.split("-")
        self._set_income_view_month(int(year_str), int(month_str))

    def _sync_reports_period_from_dashboard(self, preferred_month: str | None = None) -> None:
        month_value = (preferred_month or self.dashboard_tab.month_picker.currentText() or "").strip()
        if not month_value:
            return
        try:
            year_str, month_str = month_value.split("-")
        except ValueError:
            return
        self.reports_tab.year_picker.setCurrentText(str(int(year_str)))
        self.reports_tab.month_picker.setCurrentText(f"{int(month_str):02d}")

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

    def on_budget_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        try:
            year_str, month_str = value.split("-")
            self._set_budget_view_month(int(year_str), int(month_str))
        except ValueError:
            self.logger.warning("Invalid budget month filter value: %s", value)
            return
        self.refresh_budget_allocations()

    def on_balance_checking_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        try:
            year_str, month_str = value.split("-")
            self._set_balance_checking_view_month(int(year_str), int(month_str))
        except ValueError:
            self.logger.warning("Invalid balance checking month filter value: %s", value)
            return
        self.refresh_balance_checking()

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

    def on_income_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        try:
            year_str, month_str = value.split("-")
            self._set_income_view_month(int(year_str), int(month_str))
        except ValueError:
            self.logger.warning("Invalid income month filter value: %s", value)
            return
        self.refresh_income()

    def on_dashboard_month_changed(self, month_value: str) -> None:
        value = month_value.strip()
        if not value:
            return
        # Keep Bills month in sync with Dashboard month selection for planning workflows.
        self._refresh_budget_month_filter(preferred_month=value)
        self._refresh_balance_checking_month_filter(preferred_month=value)
        self._refresh_bills_month_filter(preferred_month=value)
        self._refresh_income_month_filter(preferred_month=value)
        self._refresh_transactions_month_filter(preferred_month=value)
        self._sync_reports_period_from_dashboard(preferred_month=value)
        self.refresh_transactions()
        self.refresh_balance_checking()
        self.refresh_budget_allocations()
        self.refresh_bills()
        self.refresh_income()
        self.refresh_dashboard()

    @staticmethod
    def _format_currency(cents: int) -> str:
        return f"${int(cents) / 100:,.2f}"

    @staticmethod
    def _format_currency_signed(cents: int) -> str:
        value = int(cents)
        if value > 0:
            return f"+${value / 100:,.2f}"
        if value < 0:
            return f"-${abs(value) / 100:,.2f}"
        return "$0.00"

    @staticmethod
    def _format_currency_balance(cents: int) -> str:
        value = int(cents)
        if value < 0:
            return f"-${abs(value) / 100:,.2f}"
        return f"${value / 100:,.2f}"

    @staticmethod
    def _parse_currency_cents_allow_negative(amount_text: str) -> int:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return 0
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Starting Balance must be numeric (example: 5000.00).") from exc
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _dashboard_category_label(raw_value: object) -> str:
        text = str(raw_value or "").strip()
        return text or "Uncategorized"

    @classmethod
    def _build_dashboard_category_rows(
        cls,
        planned_by_category: dict[str, int],
        actual_by_category: dict[str, int],
        *,
        is_income: bool,
    ) -> list[dict]:
        rows: list[dict] = []
        planned_total = 0
        actual_total = 0
        categories = sorted(set(planned_by_category) | set(actual_by_category), key=str.casefold)
        for category_name in categories:
            planned_cents = int(planned_by_category.get(category_name, 0))
            actual_cents = int(actual_by_category.get(category_name, 0))
            if planned_cents == 0 and actual_cents == 0:
                continue
            planned_total += planned_cents
            actual_total += actual_cents
            diff_cents = (actual_cents - planned_cents) if is_income else (planned_cents - actual_cents)
            rows.append(
                {
                    "category_name": category_name,
                    "planned_display": cls._format_currency(planned_cents),
                    "actual_display": cls._format_currency(actual_cents),
                    "diff_display": cls._format_currency_signed(diff_cents),
                }
            )

        total_diff_cents = (actual_total - planned_total) if is_income else (planned_total - actual_total)
        total_row = {
            "category_name": "Totals",
            "planned_display": cls._format_currency(planned_total),
            "actual_display": cls._format_currency(actual_total),
            "diff_display": cls._format_currency_signed(total_diff_cents),
        }
        separator_row = {
            "category_name": "",
            "planned_display": "",
            "actual_display": "",
            "diff_display": "",
        }
        return [total_row, separator_row, *rows]

    def refresh_dashboard(self) -> None:
        month_value = self.dashboard_tab.month_picker.currentText().strip()
        if not month_value:
            return
        try:
            year_str, month_str = month_value.split("-")
            year = int(year_str)
            month = int(month_str)
        except ValueError:
            self.logger.warning("Invalid dashboard month value: %s", month_value)
            return

        month_row = self.context.budgeting_service.get_month(year, month)
        starting_balance_cents = int(month_row.get("starting_balance_cents") or 0)

        planned_expense_by_category: dict[str, int] = {}
        for row in self.context.budget_allocations_service.list_month_allocations(year=year, month=month):
            cents = int(row.get("planned_cents") or 0)
            if cents == 0:
                continue
            category_name = self._dashboard_category_label(row.get("category_name"))
            planned_expense_by_category[category_name] = planned_expense_by_category.get(category_name, 0) + cents

        planned_income_by_category: dict[str, int] = {}
        for row in self.context.income_service.list_month_income(year=year, month=month, sort_by="category"):
            cents = int(row.get("expected_amount_cents") or 0)
            if cents == 0:
                continue
            category_name = self._dashboard_category_label(row.get("category_name"))
            planned_income_by_category[category_name] = planned_income_by_category.get(category_name, 0) + cents

        actual_expense_by_category: dict[str, int] = {}
        actual_income_by_category: dict[str, int] = {}
        for row in self.context.transactions_service.list_for_month(year=year, month=month, limit=10000):
            txn_type = str(row.get("txn_type") or "").strip().lower()
            if txn_type == "transfer":
                continue
            amount_cents = int(row.get("amount_cents") or 0)
            if amount_cents == 0:
                continue
            category_name = self._dashboard_category_label(row.get("category_name"))
            if txn_type == "expense" or (txn_type != "income" and amount_cents < 0):
                actual_expense_by_category[category_name] = (
                    actual_expense_by_category.get(category_name, 0) + abs(amount_cents)
                )
            else:
                actual_income_by_category[category_name] = (
                    actual_income_by_category.get(category_name, 0) + abs(amount_cents)
                )

        planned_expenses_total = sum(planned_expense_by_category.values())
        actual_expenses_total = sum(actual_expense_by_category.values())
        planned_income_total = sum(planned_income_by_category.values())
        actual_income_total = sum(actual_income_by_category.values())
        end_balance_cents = starting_balance_cents + (actual_income_total - actual_expenses_total)

        expense_rows = self._build_dashboard_category_rows(
            planned_expense_by_category,
            actual_expense_by_category,
            is_income=False,
        )
        income_rows = self._build_dashboard_category_rows(
            planned_income_by_category,
            actual_income_by_category,
            is_income=True,
        )
        self.dashboard_tab.expenses_model.replace_rows(expense_rows)
        self.dashboard_tab.income_model.replace_rows(income_rows)

        self._loading_dashboard_starting_balance = True
        self.dashboard_tab.starting_balance_input.setText(self._format_currency(starting_balance_cents))
        self._loading_dashboard_starting_balance = False
        self.dashboard_tab.end_balance_value.setText(self._format_currency(end_balance_cents))
        self.dashboard_tab.planned_expenses_value.setText(self._format_currency(planned_expenses_total))
        self.dashboard_tab.actual_expenses_value.setText(self._format_currency(actual_expenses_total))
        self.dashboard_tab.planned_income_value.setText(self._format_currency(planned_income_total))
        self.dashboard_tab.actual_income_value.setText(self._format_currency(actual_income_total))

        self.logger.info(
            "Dashboard refreshed for %s-%02d (start=%s, end=%s)",
            year,
            month,
            starting_balance_cents,
            end_balance_cents,
        )

    def save_dashboard_starting_balance(self) -> None:
        if self._loading_dashboard_starting_balance:
            return
        month_value = self.dashboard_tab.month_picker.currentText().strip()
        if not month_value:
            return
        try:
            year_str, month_str = month_value.split("-")
            year = int(year_str)
            month = int(month_str)
        except ValueError:
            self.logger.warning("Invalid dashboard month for starting balance save: %s", month_value)
            return

        try:
            starting_balance_cents = self._parse_currency_cents_allow_negative(
                self.dashboard_tab.starting_balance_input.text()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Starting Balance", str(exc))
            self.refresh_dashboard()
            return

        self.context.budgeting_service.set_starting_balance(year, month, starting_balance_cents)
        self.statusBar().showMessage(
            f"Saved starting balance for {year:04d}-{month:02d}.",
            3000,
        )
        self.refresh_dashboard()

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

    def _refresh_budget_form_choices(self) -> None:
        selected_category_id = self.budget_tab.category_input.currentData()

        self.budget_tab.category_input.clear()
        for row in self.context.categories_repo.list_active():
            self.budget_tab.category_input.addItem(str(row["name"]), int(row["category_id"]))

        if selected_category_id is not None:
            self._combo_select_data(self.budget_tab.category_input, int(selected_category_id))
        elif self.budget_tab.category_input.count() > 0:
            self.budget_tab.category_input.setCurrentIndex(0)

    def new_budget_form(self) -> None:
        self.budget_tab.editing_budget_line_id = None
        if self.budget_tab.category_input.count() > 0:
            self.budget_tab.category_input.setCurrentIndex(0)
        self.budget_tab.amount_input.clear()
        self.budget_tab.note_input.clear()
        self.budget_tab.table.clearSelection()

    def _selected_budget_row(self) -> dict | None:
        selection = self.budget_tab.table.selectionModel().selectedRows()
        if not selection:
            return None
        return self.budget_tab.model.row_dict(selection[0].row())

    def on_budget_selection_changed(self) -> None:
        row = self._selected_budget_row()
        if row:
            self._load_budget_into_form(row)

    def _load_budget_into_form(self, row: dict) -> None:
        self.budget_tab.editing_budget_line_id = int(row.get("budget_line_id") or 0)
        self._combo_select_data(self.budget_tab.category_input, row.get("category_id"))
        planned_cents = int(row.get("planned_cents") or 0)
        self.budget_tab.amount_input.setText(f"{planned_cents / 100:.2f}")
        self.budget_tab.note_input.setText(self._normalized_display_text(row.get("note")))

    @staticmethod
    def _build_planned_bills_by_category(rows: list[dict]) -> dict[str, int]:
        planned_by_category: dict[str, int] = {}
        for row in rows:
            category_name = str(row.get("category_name") or "Uncategorized").strip() or "Uncategorized"
            cents = int(row.get("expected_amount_cents") or 0)
            if cents == 0:
                continue
            planned_by_category[category_name] = planned_by_category.get(category_name, 0) + cents
        return planned_by_category

    def refresh_budget_allocations(self) -> None:
        allocation_rows = self.context.budget_allocations_service.list_month_allocations(
            year=self.budget_view_year,
            month=self.budget_view_month,
        )
        planned_bills_by_category = self._build_planned_bills_by_category(
            self.context.bills_service.list_month_bills(
                year=self.budget_view_year,
                month=self.budget_view_month,
                sort_by="category",
            )
        )

        rows: list[dict] = []
        total_allocation_cents = 0
        total_planned_bills_cents = 0
        total_diff_cents = 0
        for allocation in allocation_rows:
            category_name = str(allocation.get("category_name") or "Uncategorized").strip() or "Uncategorized"
            allocation_cents = int(allocation.get("planned_cents") or 0)
            planned_bills_cents = int(planned_bills_by_category.get(category_name, 0))
            diff_cents = allocation_cents - planned_bills_cents
            total_allocation_cents += allocation_cents
            total_planned_bills_cents += planned_bills_cents
            total_diff_cents += diff_cents
            rows.append(
                {
                    **allocation,
                    "allocation_display": self._format_currency(allocation_cents),
                    "planned_bills_display": self._format_currency(planned_bills_cents),
                    "diff_display": self._format_currency_signed(diff_cents),
                    "note": str(allocation.get("note") or ""),
                }
            )

        rows.sort(
            key=lambda r: (
                str(r.get("category_name") or "").casefold(),
                int(r.get("budget_line_id") or 0),
            )
        )
        planned_income_total_cents = sum(
            int(row.get("expected_amount_cents") or 0)
            for row in self.context.income_service.list_month_income(
                year=self.budget_view_year,
                month=self.budget_view_month,
                sort_by="category",
            )
        )
        unallocated_cents = planned_income_total_cents - total_allocation_cents
        self.budget_tab.model.replace_rows(rows)
        self.budget_tab.totals_model.replace_rows(
            [
                {
                    "metric": "Allocation",
                    "value_display": self._format_currency(total_allocation_cents),
                },
                {
                    "metric": "Planned",
                    "value_display": self._format_currency(total_planned_bills_cents),
                },
                {
                    "metric": "Diff",
                    "value_display": self._format_currency_signed(total_diff_cents),
                },
                {
                    "metric": "Total Planned Income",
                    "value_display": self._format_currency(planned_income_total_cents),
                },
                {
                    "metric": "Unallocated",
                    "value_display": self._format_currency_signed(unallocated_cents),
                },
            ]
        )
        self.logger.info(
            "Loaded %s budget allocations for %s-%02d",
            len(rows),
            self.budget_view_year,
            self.budget_view_month,
        )
        self.refresh_dashboard()

    def save_budget_allocation(self) -> None:
        category_id = self.budget_tab.category_input.currentData()
        if category_id is None:
            QMessageBox.warning(self, "Save Budget Allocation", "Category is required.")
            return
        try:
            parsed = self._parse_currency_cents_or_none(self.budget_tab.amount_input.text())
            planned_cents = int(parsed or 0)
            note = self._normalized_display_text(self.budget_tab.note_input.text()) or None

            if self.budget_tab.editing_budget_line_id:
                updated = self.context.budget_allocations_service.update_month_allocation(
                    budget_line_id=int(self.budget_tab.editing_budget_line_id),
                    category_id=int(category_id),
                    planned_cents=planned_cents,
                    note=note,
                )
                if not updated:
                    QMessageBox.warning(
                        self,
                        "Save Budget Allocation",
                        "Selected budget allocation no longer exists.",
                    )
                    self.refresh_budget_allocations()
                    self.new_budget_form()
                    return
            else:
                self.context.budget_allocations_service.upsert_month_allocation(
                    year=self.budget_view_year,
                    month=self.budget_view_month,
                    category_id=int(category_id),
                    planned_cents=planned_cents,
                    note=note,
                )
            self._mark_budget_month_dirty(self.budget_view_year, self.budget_view_month)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Budget Allocation", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save budget allocation failed: %s", exc)
            QMessageBox.critical(self, "Save Budget Allocation Failed", str(exc))
            return

        self.refresh_budget_allocations()
        self.new_budget_form()

    def delete_budget_allocation(self) -> None:
        row = self._selected_budget_row()
        if not row:
            QMessageBox.information(self, "Delete Budget Allocation", "Select an allocation row to delete.")
            return
        budget_line_id = int(row.get("budget_line_id") or 0)
        if not budget_line_id:
            QMessageBox.warning(self, "Delete Budget Allocation", "Invalid allocation selection.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Budget Allocation",
            f"Delete allocation for '{row.get('category_name', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.context.budget_allocations_service.delete_month_allocation(budget_line_id)
        except Exception as exc:
            self.logger.error("Delete budget allocation failed: %s", exc)
            QMessageBox.critical(self, "Delete Budget Allocation Failed", str(exc))
            return
        if not deleted:
            QMessageBox.warning(self, "Delete Budget Allocation", "Selected allocation no longer exists.")
            return

        self._mark_budget_month_dirty(self.budget_view_year, self.budget_view_month)
        self.refresh_budget_allocations()
        self.new_budget_form()

    def set_budget_sort(self, sort_key: str) -> None:
        self.budget_sort_key = sort_key
        self.refresh_budget_allocations()

    def refresh_budget_for_selected_month(self) -> None:
        month_label = f"{self.budget_view_year:04d}-{self.budget_view_month:02d}"
        if self._is_budget_month_dirty(self.budget_view_year, self.budget_view_month):
            answer = QMessageBox.warning(
                self,
                "Refresh Category Budgets",
                "Refreshing category budgets will replace all monthly allocation instances for "
                f"{month_label} with current global budget category definitions.\n\n"
                "Any edits made to monthly budget allocations for this month will be lost.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                self.statusBar().showMessage("Refresh Category Budgets canceled.", 3000)
                return

        deleted, inserted = self.context.budget_allocations_service.regenerate_for_month(
            self.budget_view_year,
            self.budget_view_month,
        )
        self._clear_budget_month_dirty(self.budget_view_year, self.budget_view_month)
        self.refresh_budget_allocations()
        self.statusBar().showMessage(
            f"Refreshed category budgets for {month_label}: replaced {deleted}, generated {inserted}.",
            5000,
        )

    def _refresh_bill_form_choices(self) -> None:
        selected_category_id = self.bills_tab.category_input.currentData()

        self.bills_tab.category_input.clear()
        self.bills_tab.category_input.addItem("", None)
        for row in self.context.categories_repo.list_active():
            self.bills_tab.category_input.addItem(str(row["name"]), int(row["category_id"]))

        if selected_category_id is not None:
            self._combo_select_data(self.bills_tab.category_input, selected_category_id)
        else:
            self.bills_tab.category_input.setCurrentIndex(0)

    def new_bill_form(self) -> None:
        self.bills_tab.editing_bill_id = None
        self._editing_bill_source_system = None
        self.bills_tab.bill_name_input.clear()
        self.bills_tab.start_date_input.setText(date.today().isoformat())
        self.bills_tab.date_paid_input.clear()
        self.bills_tab.interval_count_input.clear()
        self.bills_tab.interval_unit_combo.setCurrentText("months")
        self.bills_tab.amount_input.clear()
        self.bills_tab.note_input.clear()
        self.bills_tab.category_input.setCurrentIndex(0)
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
        self.bills_tab.editing_bill_id = int(row.get("bill_occurrence_id") or 0)
        self._editing_bill_source_system = self._normalized_source_system(
            str(row.get("source_system") or "")
        )
        self.bills_tab.bill_name_input.setText(self._normalized_display_text(row.get("name")))
        due_date = self._normalized_display_text(row.get("payment_due") or row.get("expected_date"))
        self.bills_tab.start_date_input.setText(due_date or date.today().isoformat())
        self.bills_tab.date_paid_input.setText(self._normalized_display_text(row.get("paid_date")))
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
        amount_cents = row.get("expected_amount_cents")
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

    def _build_bill_occurrence_payload(self) -> dict:
        due_date_text = self.bills_tab.start_date_input.text().strip()
        try:
            datetime.strptime(due_date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Payment Due must be in YYYY-MM-DD format.") from exc

        paid_date_text = self.bills_tab.date_paid_input.text().strip()
        if paid_date_text:
            try:
                datetime.strptime(paid_date_text, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("Date Paid must be in YYYY-MM-DD format.") from exc

        amount_cents = self._parse_currency_cents_or_none(self.bills_tab.amount_input.text())

        return {
            "expected_date": due_date_text,
            "paid_date": paid_date_text or None,
            "expected_amount_cents": amount_cents,
            "notes": self._normalized_display_text(self.bills_tab.note_input.text()) or None,
        }

    def save_bill(self) -> None:
        bill_id = self.bills_tab.editing_bill_id
        action_label = "Save Bill Update"
        if not bill_id:
            QMessageBox.information(
                self,
                action_label,
                "Select a bill row to update this month occurrence.",
            )
            return

        try:
            payload = self._build_bill_occurrence_payload()
            updated = self.context.bills_service.update_occurrence(
                bill_occurrence_id=bill_id,
                expected_date=payload["expected_date"],
                expected_amount_cents=payload["expected_amount_cents"],
                paid_date=payload["paid_date"],
                note=payload["notes"],
            )
            if not updated:
                QMessageBox.warning(self, action_label, "Selected bill row no longer exists.")
                self.refresh_bills()
                self.new_bill_form()
                return
            self._mark_bills_month_dirty(
                self.bills_view_year,
                self.bills_view_month,
                self._editing_bill_source_system,
            )
            self.logger.info("Updated bill occurrence %s", bill_id)
            self.statusBar().showMessage("Bill updated for selected month.", 3000)
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
        bill_id = int(row.get("bill_occurrence_id") or 0)
        if not bill_id:
            QMessageBox.warning(self, "Delete Bill", "Invalid bill selection.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Bill",
            f"Delete bill '{row.get('name', '')}' for this month?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self.context.bills_service.delete_occurrence(bill_id)
        except Exception as exc:
            self.logger.error("Delete bill failed: %s", exc)
            QMessageBox.critical(self, "Delete Bill Failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Bill", "Selected bill no longer exists.")
        else:
            self._mark_bills_month_dirty(
                self.bills_view_year,
                self.bills_view_month,
                str(row.get("source_system") or ""),
            )
            self.logger.info("Deleted bill occurrence %s", bill_id)
            self.statusBar().showMessage("Bill deleted from selected month.", 3000)

        self.refresh_bills()
        self.new_bill_form()

    def set_bills_sort(self, sort_key: str) -> None:
        self.bills_sort_key = sort_key
        self.refresh_bills()

    def _refresh_income_form_choices(self) -> None:
        selected_category_id = self.income_tab.category_input.currentData()
        selected_account_name = self._normalized_display_text(self.income_tab.account_input.text())

        self.income_tab.category_input.clear()
        self.income_tab.category_input.addItem("", None)
        for row in self.context.categories_repo.list_active():
            self.income_tab.category_input.addItem(str(row["name"]), int(row["category_id"]))
        if selected_category_id is not None:
            self._combo_select_data(self.income_tab.category_input, selected_category_id)
        else:
            self.income_tab.category_input.setCurrentIndex(0)

        account_name = selected_account_name
        if not account_name:
            accounts = self.context.accounts_repo.list_active()
            if accounts:
                account_name = str(accounts[0]["name"])
        self.income_tab.account_input.setText(account_name)

    def new_income_form(self) -> None:
        self.income_tab.editing_income_occurrence_id = None
        self.income_tab.description_input.clear()
        self.income_tab.start_date_input.setText(date.today().isoformat())
        self.income_tab.interval_count_input.clear()
        self.income_tab.interval_unit_combo.setCurrentText("months")
        self.income_tab.amount_input.clear()
        self.income_tab.note_input.clear()
        self.income_tab.category_input.setCurrentIndex(0)
        self.income_tab.account_input.clear()
        self.income_tab.table.clearSelection()

    def _selected_income_row(self) -> dict | None:
        selection = self.income_tab.table.selectionModel().selectedRows()
        if not selection:
            return None
        return self.income_tab.model.row_dict(selection[0].row())

    def on_income_selection_changed(self) -> None:
        row = self._selected_income_row()
        if row:
            self._load_income_into_form(row)

    def _load_income_into_form(self, row: dict) -> None:
        self.income_tab.editing_income_occurrence_id = int(row.get("income_occurrence_id") or 0)
        self.income_tab.description_input.setText(self._normalized_display_text(row.get("description")))
        due_date = self._normalized_display_text(row.get("payment_due") or row.get("expected_date"))
        self.income_tab.start_date_input.setText(due_date or date.today().isoformat())
        self.income_tab.interval_count_input.setText(str(int(row.get("interval_count") or 1)))
        raw_unit = self._normalized_display_text(row.get("interval_unit")) or "months"
        normalized_unit = raw_unit if raw_unit.endswith("s") or raw_unit == "once" else f"{raw_unit}s"
        if self.income_tab.interval_unit_combo.findText(normalized_unit) >= 0:
            self.income_tab.interval_unit_combo.setCurrentText(normalized_unit)
        else:
            self.income_tab.interval_unit_combo.setCurrentText("months")
        amount_cents = row.get("expected_amount_cents")
        if amount_cents is None:
            self.income_tab.amount_input.clear()
        else:
            self.income_tab.amount_input.setText(f"{int(amount_cents) / 100:.2f}")
        self.income_tab.note_input.setText(self._normalized_display_text(row.get("notes")))
        self._combo_select_data(self.income_tab.category_input, row.get("category_id"))
        self.income_tab.account_input.setText(self._normalized_display_text(row.get("account_name")))

    def _build_income_occurrence_payload(self) -> dict:
        due_date_text = self.income_tab.start_date_input.text().strip()
        try:
            datetime.strptime(due_date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Payment Due must be in YYYY-MM-DD format.") from exc
        amount_cents = self._parse_currency_cents_or_none(self.income_tab.amount_input.text())
        return {
            "expected_date": due_date_text,
            "expected_amount_cents": amount_cents,
            "notes": self._normalized_display_text(self.income_tab.note_input.text()) or None,
        }

    def save_income(self) -> None:
        income_occurrence_id = self.income_tab.editing_income_occurrence_id
        if not income_occurrence_id:
            QMessageBox.information(
                self,
                "Save Income Update",
                "Select an income row to update this month occurrence.",
            )
            return
        try:
            payload = self._build_income_occurrence_payload()
            updated = self.context.income_service.update_occurrence(
                income_occurrence_id=income_occurrence_id,
                expected_date=payload["expected_date"],
                expected_amount_cents=payload["expected_amount_cents"],
                note=payload["notes"],
            )
            if not updated:
                QMessageBox.warning(self, "Save Income Update", "Selected income row no longer exists.")
                self.refresh_income()
                self.new_income_form()
                return
            self._mark_income_month_dirty(self.income_view_year, self.income_view_month)
            self.logger.info("Updated income occurrence %s", income_occurrence_id)
            self.statusBar().showMessage("Income updated for selected month.", 3000)
        except ValueError as exc:
            QMessageBox.warning(self, "Save Income Update", str(exc))
            return
        except Exception as exc:
            self.logger.error("Save income failed: %s", exc)
            QMessageBox.critical(self, "Save Income Failed", str(exc))
            return
        self.refresh_income()
        self.new_income_form()

    def delete_income(self) -> None:
        row = self._selected_income_row()
        if not row:
            QMessageBox.information(self, "Delete Income", "Select an income row to delete.")
            return
        income_occurrence_id = int(row.get("income_occurrence_id") or 0)
        if not income_occurrence_id:
            QMessageBox.warning(self, "Delete Income", "Invalid income selection.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Income",
            f"Delete income '{row.get('description', '')}' for this month?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            deleted = self.context.income_service.delete_occurrence(income_occurrence_id)
        except Exception as exc:
            self.logger.error("Delete income failed: %s", exc)
            QMessageBox.critical(self, "Delete Income Failed", str(exc))
            return
        if not deleted:
            QMessageBox.warning(self, "Delete Income", "Selected income row no longer exists.")
        else:
            self._mark_income_month_dirty(self.income_view_year, self.income_view_month)
            self.logger.info("Deleted income occurrence %s", income_occurrence_id)
            self.statusBar().showMessage("Income deleted from selected month.", 3000)
        self.refresh_income()
        self.new_income_form()

    def set_income_sort(self, sort_key: str) -> None:
        self.income_sort_key = sort_key
        self.refresh_income()

    @staticmethod
    def _build_income_category_subtotals(rows: list[dict]) -> list[dict]:
        totals_by_category: dict[str, int] = {}
        for row in rows:
            category_name = str(row.get("category_name") or "Uncategorized").strip() or "Uncategorized"
            amount_cents = int(row.get("expected_amount_cents") or 0)
            totals_by_category[category_name] = totals_by_category.get(category_name, 0) + amount_cents
        subtotal_rows = [
            {
                "category_name": category_name,
                "subtotal_display": f"${cents / 100:.2f}",
            }
            for category_name, cents in totals_by_category.items()
        ]
        subtotal_rows.sort(
            key=lambda item: (
                str(item.get("category_name") or "").strip().casefold(),
                str(item.get("category_name") or "").strip(),
            )
        )
        return subtotal_rows

    def refresh_income(self) -> None:
        rows = self.context.income_service.list_month_income(
            year=self.income_view_year,
            month=self.income_view_month,
            sort_by=self.income_sort_key,
        )
        self.income_tab.model.replace_rows(rows)
        subtotal_rows = self._build_income_category_subtotals(rows)
        self.income_tab.category_totals_model.replace_rows(subtotal_rows)
        total_cents = sum(int(row.get("expected_amount_cents") or 0) for row in rows)
        self.income_tab.total_income_value_label.setText(f"${total_cents / 100:.2f}")
        self.logger.info(
            "Loaded %s income occurrences for %s-%02d (sort=%s)",
            len(rows),
            self.income_view_year,
            self.income_view_month,
            self.income_sort_key,
        )
        self.refresh_dashboard()

    def refresh_income_for_selected_month(self) -> None:
        month_label = f"{self.income_view_year:04d}-{self.income_view_month:02d}"
        if self._is_income_month_dirty(self.income_view_year, self.income_view_month):
            answer = QMessageBox.warning(
                self,
                "Refresh Income",
                "Refreshing income will replace all income instances for "
                f"{month_label} with current global definitions.\n\n"
                "Any edits made to monthly income instances for this month will be lost.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                self.statusBar().showMessage("Refresh Income canceled.", 3000)
                return

        deleted, inserted = self.context.income_service.regenerate_for_month(
            self.income_view_year,
            self.income_view_month,
        )
        self._clear_income_month_dirty(self.income_view_year, self.income_view_month)
        self.refresh_income()
        self.logger.info(
            "Refreshed income for %s-%02d: replaced %s occurrences, generated %s from definitions.",
            self.income_view_year,
            self.income_view_month,
            deleted,
            inserted,
        )
        self.statusBar().showMessage(
            f"Refreshed income for {month_label}: replaced {deleted}, generated {inserted}.",
            5000,
        )


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
        self._refresh_balance_checking_month_filter(preferred_month=txn.txn_date[:7])
        self._suppress_selection_autoload = True
        try:
            self.refresh_transactions()
            self.refresh_balance_checking()
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
        self._refresh_balance_checking_month_filter(
            preferred_month=f"{self.transactions_view_year}-{self.transactions_view_month:02d}"
        )
        self.refresh_transactions()
        self.refresh_balance_checking()
        self._clear_transaction_form()

    @staticmethod
    def _build_bill_category_subtotals(rows: list[dict]) -> list[dict]:
        totals_by_category: dict[str, int] = {}
        for row in rows:
            category_name = str(row.get("category_name") or "Uncategorized").strip() or "Uncategorized"
            amount_cents = row.get("expected_amount_cents")
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
        rows = self.context.bills_service.list_month_bills(
            sort_by=self.bills_sort_key,
            year=self.bills_view_year,
            month=self.bills_view_month,
        )
        self.bills_tab.model.replace_rows(rows)
        subtotal_rows = self._build_bill_category_subtotals(rows)
        self.bills_tab.category_totals_model.replace_rows(subtotal_rows)
        total_cents = sum(int(row.get("expected_amount_cents") or 0) for row in rows)
        self.bills_tab.total_subtotals_value_label.setText(f"${total_cents / 100:.2f}")
        self.logger.info(
            "Loaded %s bill occurrences for %s-%02d (sort=%s)",
            len(rows),
            self.bills_view_year,
            self.bills_view_month,
            self.bills_sort_key,
        )
        if self.budget_view_year == self.bills_view_year and self.budget_view_month == self.bills_view_month:
            self.refresh_budget_allocations()
        else:
            self.refresh_dashboard()

    def refresh_bills_for_selected_month(self) -> None:
        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        if self._is_bills_month_dirty(self.bills_view_year, self.bills_view_month):
            answer = QMessageBox.warning(
                self,
                "Refresh Bills",
                "Refreshing bills will replace all bill instances for "
                f"{month_label} with current global definitions.\n\n"
                "Any edits made to monthly bill instances for this month will be lost.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                self.statusBar().showMessage("Refresh Bills canceled.", 3000)
                return

        deleted, inserted = self.context.bills_service.regenerate_for_month(
            self.bills_view_year,
            self.bills_view_month,
        )
        self._clear_bills_month_dirty(self.bills_view_year, self.bills_view_month)
        self.refresh_bills()
        self.logger.info(
            "Refreshed bills for %s-%02d: replaced %s occurrences, generated %s from definitions.",
            self.bills_view_year,
            self.bills_view_month,
            deleted,
            inserted,
        )
        self.statusBar().showMessage(
            f"Refreshed bills for {month_label}: replaced {deleted}, generated {inserted}.",
            5000,
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
        writer.setResolution(120)
        page_layout = writer.pageLayout()
        page_layout.setPageSize(QPageSize(QPageSize.A4))
        page_layout.setOrientation(QPageLayout.Landscape)
        page_layout.setUnits(QPageLayout.Inch)
        page_layout.setMargins(QMarginsF(0.5, 0.5, 0.5, 0.5))
        writer.setPageLayout(page_layout)

        painter = QPainter()
        if not painter.begin(writer):
            raise OSError(f"Unable to create PDF at {save_path}")

        normal_font = QFont("Arial", 12)
        bold_font = QFont("Arial", 12)
        bold_font.setBold(True)
        painter.setFont(normal_font)

        metrics = painter.fontMetrics()
        line_height = metrics.height() + 6
        base_row_height = metrics.height() + 10

        # Compute the content bounds from the full page using explicit 0.5" margins
        # so all four sides are consistent across platforms/viewers.
        resolution = writer.resolution()
        margin_px = int(round(0.5 * resolution))
        full_rect = writer.pageLayout().fullRectPixels(resolution)
        content_rect = full_rect.adjusted(margin_px, margin_px, -margin_px, -margin_px)
        content_rect = content_rect.adjusted(1, 1, -1, -1)  # avoid edge clipping on borders
        left = content_rect.left()
        top = content_rect.top()
        bottom = content_rect.bottom()
        table_width = content_rect.width()

        y = top

        def ensure_space(required_height: int) -> None:
            nonlocal y
            if y + required_height <= bottom:
                return
            writer.newPage()
            painter.setFont(normal_font)
            y = top

        def draw_line(text: str, *, bold: bool = False) -> None:
            ensure_space(line_height)
            painter.setFont(bold_font if bold else normal_font)
            painter.drawText(
                QRect(left, y, table_width, line_height),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                text,
            )
            painter.setFont(normal_font)
            nonlocal_y_increment()

        def nonlocal_y_increment(step: int = line_height) -> None:
            nonlocal y
            y += step

        def draw_table(
            *,
            title: str,
            columns: list[str],
            rows_data: list[list[str]],
            width_ratios: list[float],
            alignments: list[Qt.AlignmentFlag],
            wrap_columns: set[int] | None = None,
            bold_last_row: bool = False,
        ) -> None:
            nonlocal y
            if len(columns) != len(width_ratios) or len(columns) != len(alignments):
                raise ValueError("Columns, width ratios, and alignments must match.")
            wrap_columns = wrap_columns or set()

            widths = [int(table_width * ratio) for ratio in width_ratios]
            widths[-1] = table_width - sum(widths[:-1])

            def draw_header_row(section_title: str) -> None:
                nonlocal y
                draw_line(section_title, bold=True)
                ensure_space(base_row_height)
                x = left
                painter.setFont(bold_font)
                for idx, heading in enumerate(columns):
                    rect = QRect(x, y, widths[idx], base_row_height)
                    painter.fillRect(rect, QColor("#E5E7EB"))
                    painter.drawRect(rect)
                    painter.drawText(
                        rect.adjusted(6, 0, -6, 0),
                        int(Qt.AlignLeft | Qt.AlignVCenter),
                        heading,
                    )
                    x += widths[idx]
                painter.setFont(normal_font)
                y += base_row_height

            draw_header_row(title)
            for row_idx, row_cells in enumerate(rows_data):
                row_height = base_row_height
                for col_idx, cell in enumerate(row_cells):
                    if col_idx not in wrap_columns:
                        continue
                    probe_rect = QRect(0, 0, max(1, widths[col_idx] - 10), 10000)
                    wrapped_rect = painter.fontMetrics().boundingRect(
                        probe_rect,
                        int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop),
                        str(cell or ""),
                    )
                    row_height = max(row_height, wrapped_rect.height() + 10)

                if y + row_height > bottom:
                    writer.newPage()
                    painter.setFont(normal_font)
                    y = top
                    draw_header_row(f"{title} (continued)")

                x = left
                is_last = row_idx == len(rows_data) - 1
                if bold_last_row and is_last:
                    painter.setFont(bold_font)
                for col_idx, cell in enumerate(row_cells):
                    rect = QRect(x, y, widths[col_idx], row_height)
                    painter.drawRect(rect)
                    text_rect = rect.adjusted(5, 4, -5, -4)
                    if col_idx in wrap_columns:
                        painter.drawText(
                            text_rect,
                            int(alignments[col_idx] | Qt.AlignTop | Qt.TextWordWrap),
                            str(cell or ""),
                        )
                    else:
                        cell_text = painter.fontMetrics().elidedText(
                            str(cell or ""),
                            Qt.ElideRight,
                            max(0, rect.width() - 10),
                        )
                        painter.drawText(
                            text_rect,
                            int(alignments[col_idx] | Qt.AlignVCenter),
                            cell_text,
                        )
                    x += widths[col_idx]
                painter.setFont(normal_font)
                y += row_height
            y += 6

        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        draw_line(f"BudgetPal Bills Report - {month_label}", bold=True)
        draw_line(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        y += 6

        # Section 1 first: Category Sub-Totals
        subtotal_table_rows: list[list[str]] = []
        total_cents = 0
        for row in subtotal_rows:
            category = str(row.get("category_name") or "").strip()
            subtotal_display = str(row.get("subtotal_display") or "$0.00").strip() or "$0.00"
            cents = int(
                (Decimal(subtotal_display.replace("$", "").replace(",", "")) * 100).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )
            total_cents += cents
            subtotal_table_rows.append([category, subtotal_display])
        subtotal_table_rows.append(["Total", f"${total_cents / 100:.2f}"])

        draw_table(
            title="Section 1: Category Sub-Totals",
            columns=["Category", "Subtotal"],
            rows_data=subtotal_table_rows,
            width_ratios=[0.72, 0.28],
            alignments=[Qt.AlignLeft, Qt.AlignRight],
            bold_last_row=True,
        )

        # Section 2 second: Bill details.
        bill_rows = [
            [
                str(row.get("category_name") or ""),
                str(row.get("name") or ""),
                str(row.get("payment_due") or ""),
                str(row.get("interval_display") or ""),
                str(row.get("amount_display") or ""),
                str(row.get("notes") or ""),
            ]
            for row in rows
        ]
        draw_table(
            title="Section 2: Bills and Subscriptions (Month Occurrences)",
            columns=["Category", "Name", "Payment Due", "Interval", "Amount", "Note"],
            rows_data=bill_rows,
            width_ratios=[0.14, 0.24, 0.13, 0.11, 0.10, 0.28],
            alignments=[Qt.AlignLeft, Qt.AlignLeft, Qt.AlignLeft, Qt.AlignLeft, Qt.AlignRight, Qt.AlignLeft],
            wrap_columns={5},
        )

        painter.end()

    @staticmethod
    def _rtf_escape(value: str) -> str:
        text = str(value or "")
        escaped: list[str] = []
        for ch in text:
            if ch == "\\":
                escaped.append(r"\\")
            elif ch == "{":
                escaped.append(r"\{")
            elif ch == "}":
                escaped.append(r"\}")
            elif ch == "\n":
                escaped.append(r"\line ")
            elif ord(ch) > 127:
                escaped.append(f"\\u{ord(ch)}?")
            else:
                escaped.append(ch)
        return "".join(escaped)

    @staticmethod
    def _rtf_cell_edges(total_width_twips: int, width_ratios: list[float]) -> list[int]:
        widths = [int(total_width_twips * ratio) for ratio in width_ratios]
        widths[-1] = total_width_twips - sum(widths[:-1])
        edges: list[int] = []
        running = 0
        for width in widths:
            running += max(1, int(width))
            edges.append(running)
        return edges

    def _build_rtf_table(
        self,
        *,
        title: str,
        columns: list[str],
        rows_data: list[list[str]],
        width_ratios: list[float],
        alignments: list[str],
        total_width_twips: int,
        bold_last_row: bool = False,
    ) -> list[str]:
        lines: list[str] = []
        lines.append(rf"\b {self._rtf_escape(title)}\b0\par")
        edges = self._rtf_cell_edges(total_width_twips, width_ratios)

        def row_rtf(cells: list[str], *, header: bool = False, bold_row: bool = False) -> str:
            parts: list[str] = [r"\trowd\trgaph108\trleft0"]
            for edge in edges:
                parts.append(rf"\cellx{edge}")
            for idx, raw in enumerate(cells):
                align = r"\ql"
                if idx < len(alignments) and alignments[idx] == "right":
                    align = r"\qr"
                content = self._rtf_escape(raw)
                prefix = align + r"\intbl "
                if header or bold_row:
                    prefix += r"\b "
                    suffix = r"\b0 \cell"
                else:
                    suffix = r"\cell"
                parts.append(f"{prefix}{content}{suffix}")
            parts.append(r"\row")
            return "".join(parts)

        lines.append(row_rtf(columns, header=True))
        for idx, row in enumerate(rows_data):
            is_last = idx == (len(rows_data) - 1)
            lines.append(row_rtf([str(cell or "") for cell in row], bold_row=bold_last_row and is_last))
        lines.append(r"\par")
        return lines

    def _write_bills_report_rtf(self, save_path: Path, rows: list[dict], subtotal_rows: list[dict]) -> None:
        # Letter landscape in twips: 11in x 8.5in -> 15840 x 12240
        # 0.5in margins all around -> 720 twips each side.
        paper_width = 15840
        paper_height = 12240
        margin = 720
        content_width = paper_width - (margin * 2)

        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subtotal_table_rows: list[list[str]] = []
        total_cents = 0
        for row in subtotal_rows:
            category = str(row.get("category_name") or "").strip()
            subtotal_display = str(row.get("subtotal_display") or "$0.00").strip() or "$0.00"
            cents = int(
                (Decimal(subtotal_display.replace("$", "").replace(",", "")) * 100).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )
            total_cents += cents
            subtotal_table_rows.append([category, subtotal_display])
        subtotal_table_rows.append(["Total", f"${total_cents / 100:.2f}"])

        bill_rows = [
            [
                str(row.get("category_name") or ""),
                str(row.get("name") or ""),
                str(row.get("payment_due") or ""),
                str(row.get("interval_display") or ""),
                str(row.get("amount_display") or ""),
                str(row.get("notes") or ""),
            ]
            for row in rows
        ]

        lines: list[str] = [
            r"{\rtf1\ansi\deff0",
            r"{\fonttbl{\f0 Arial;}}",
            rf"\paperw{paper_width}\paperh{paper_height}\landscape",
            rf"\margl{margin}\margr{margin}\margt{margin}\margb{margin}",
            r"\fs24",
            rf"\b {self._rtf_escape(f'BudgetPal Bills Report - {month_label}')}\b0\par",
            rf"Generated: {self._rtf_escape(generated)}\par\par",
        ]

        lines.extend(
            self._build_rtf_table(
                title="Section 1: Category Sub-Totals",
                columns=["Category", "Subtotal"],
                rows_data=subtotal_table_rows,
                width_ratios=[0.72, 0.28],
                alignments=["left", "right"],
                total_width_twips=content_width,
                bold_last_row=True,
            )
        )
        lines.extend(
            self._build_rtf_table(
                title="Section 2: Bills and Subscriptions (Month Occurrences)",
                columns=["Category", "Name", "Payment Due", "Interval", "Amount", "Note"],
                rows_data=bill_rows,
                width_ratios=[0.14, 0.24, 0.13, 0.11, 0.10, 0.28],
                alignments=["left", "left", "left", "left", "right", "left"],
                total_width_twips=content_width,
            )
        )
        lines.append("}")
        save_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_bills_report_docx(self, save_path: Path, rows: list[dict], subtotal_rows: list[dict]) -> None:
        try:
            from docx import Document
            from docx.enum.section import WD_ORIENT
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Inches, Pt
        except ImportError as exc:
            raise OSError(
                "python-docx is not installed. Install it with: pip install python-docx"
            ) from exc

        doc = Document()
        section = doc.sections[0]
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
        margin = Inches(0.5)
        section.left_margin = margin
        section.right_margin = margin
        section.top_margin = margin
        section.bottom_margin = margin

        normal_style = doc.styles["Normal"]
        normal_style.font.name = "Arial"
        normal_style.font.size = Pt(12)

        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        title_p = doc.add_paragraph()
        title_run = title_p.add_run(f"BudgetPal Bills Report - {month_label}")
        title_run.bold = True
        title_run.font.name = "Arial"
        title_run.font.size = Pt(12)
        generated_p = doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        generated_p.runs[0].font.name = "Arial"
        generated_p.runs[0].font.size = Pt(12)

        def set_cell_text(cell, text: str, *, bold: bool = False, align_right: bool = False) -> None:
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(str(text or ""))
            run.font.name = "Arial"
            run.font.size = Pt(12)
            run.bold = bool(bold)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if align_right else WD_ALIGN_PARAGRAPH.LEFT

        def add_table(title: str, headers: list[str], data_rows: list[list[str]], right_cols: set[int]) -> None:
            heading = doc.add_paragraph()
            heading_run = heading.add_run(title)
            heading_run.bold = True
            heading_run.font.name = "Arial"
            heading_run.font.size = Pt(12)

            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            header_cells = table.rows[0].cells
            for idx, header in enumerate(headers):
                set_cell_text(header_cells[idx], header, bold=True, align_right=False)

            for row in data_rows:
                cells = table.add_row().cells
                for idx, value in enumerate(row):
                    set_cell_text(
                        cells[idx],
                        str(value or ""),
                        align_right=(idx in right_cols),
                    )
            doc.add_paragraph("")

        subtotal_table_rows: list[list[str]] = []
        total_cents = 0
        for row in subtotal_rows:
            category = str(row.get("category_name") or "").strip()
            subtotal_display = str(row.get("subtotal_display") or "$0.00").strip() or "$0.00"
            cents = int(
                (Decimal(subtotal_display.replace("$", "").replace(",", "")) * 100).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )
            total_cents += cents
            subtotal_table_rows.append([category, subtotal_display])
        subtotal_table_rows.append(["Total", f"${total_cents / 100:.2f}"])

        add_table(
            "Section 1: Category Sub-Totals",
            ["Category", "Subtotal"],
            subtotal_table_rows,
            right_cols={1},
        )

        bill_rows = [
            [
                str(row.get("category_name") or ""),
                str(row.get("name") or ""),
                str(row.get("payment_due") or ""),
                str(row.get("interval_display") or ""),
                str(row.get("amount_display") or ""),
                str(row.get("notes") or ""),
            ]
            for row in rows
        ]
        add_table(
            "Section 2: Bills and Subscriptions (Month Occurrences)",
            ["Category", "Name", "Payment Due", "Interval", "Amount", "Note"],
            bill_rows,
            right_cols={4},
        )

        doc.save(str(save_path))

    def export_bills_report(self) -> None:
        start_dir = self._bills_report_dialog_start_dir()
        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bills Report (DOCX)",
            str(Path(start_dir) / f"budgetpal_bills_report_{month_label}.docx"),
            "Word Document (*.docx)",
        )
        if not file_path:
            return

        save_path = Path(file_path)
        if save_path.suffix.lower() != ".docx":
            save_path = save_path.with_suffix(".docx")
        if not save_path.stem.endswith(f"_{month_label}"):
            save_path = save_path.with_name(f"{save_path.stem}_{month_label}{save_path.suffix}")
        self._persist_last_bills_report_dir(save_path.parent)

        rows = self.context.bills_service.list_month_bills(
            sort_by=self.bills_sort_key,
            year=self.bills_view_year,
            month=self.bills_view_month,
        )
        subtotal_rows = self._build_bill_category_subtotals(rows)

        try:
            self._write_bills_report_docx(save_path, rows, subtotal_rows)
        except OSError as exc:
            self.logger.error("Bills report export failed: %s", exc)
            QMessageBox.critical(self, "Bills Report Export Failed", str(exc))
            return

        self.logger.info("Exported bills report to %s (%s rows, %s subtotals)", save_path, len(rows), len(subtotal_rows))
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

        month_label = f"{self.bills_view_year:04d}-{self.bills_view_month:02d}"
        if self._is_subscriptions_month_dirty(self.bills_view_year, self.bills_view_month):
            answer = QMessageBox.warning(
                self,
                "Refresh Subscriptions",
                "Refreshing subscriptions will replace subscription bill instances for "
                f"{month_label} with current SubTracker values.\n\n"
                "Any edits made to monthly subscription instances for this month will be lost.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                self.statusBar().showMessage("Refresh Subscriptions canceled.", 3000)
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
            deleted, inserted = self.context.bills_service.regenerate_for_month(
                self.bills_view_year,
                self.bills_view_month,
                source_system="subtracker",
            )
            self._clear_bills_month_dirty(
                self.bills_view_year,
                self.bills_view_month,
                source_system="subtracker",
            )
            self.refresh_bills()
            self.logger.info("Refreshed %s active subscriptions from SubTracker", count)
            self.statusBar().showMessage(
                f"Refreshed subscriptions for {month_label}: definitions {count}, replaced {deleted}, generated {inserted}.",
                6000,
            )
        except SubTrackerIntegrationError as exc:
            self.logger.error("SubTracker integration failed: %s", exc)
            QMessageBox.critical(self, "SubTracker Integration Error", str(exc))

    def on_bill_definitions_changed(self) -> None:
        self.refresh_bills()
        self.statusBar().showMessage(
            "Bill definitions updated. Click Refresh Bills to regenerate the selected month.",
            6000,
        )

    def on_budget_definitions_changed(self) -> None:
        self.refresh_budget_allocations()
        self.statusBar().showMessage(
            "Budget category definitions updated. Click Refresh Category Budgets to regenerate the selected month.",
            6000,
        )

    def show_budget_definitions_dialog(self) -> None:
        if self.budget_definitions_dialog is None:
            self.budget_definitions_dialog = BudgetCategoryDefinitionsDialog(
                service=self.context.budget_allocations_service,
                categories_repo=self.context.categories_repo,
                logger=self.logger,
                on_changed=self.on_budget_definitions_changed,
                parent=self,
            )
            self.budget_definitions_dialog.setAttribute(Qt.WA_DeleteOnClose, False)

        self.budget_definitions_dialog.show()
        self.budget_definitions_dialog.raise_()
        self.budget_definitions_dialog.activateWindow()

    def show_bill_definitions_dialog(self) -> None:
        if self.bill_definitions_dialog is None:
            self.bill_definitions_dialog = RecurringDefinitionsDialog(
                bills_service=self.context.bills_service,
                categories_repo=self.context.categories_repo,
                logger=self.logger,
                on_changed=self.on_bill_definitions_changed,
                parent=self,
            )
            self.bill_definitions_dialog.setAttribute(Qt.WA_DeleteOnClose, False)

        self.bill_definitions_dialog.show()
        self.bill_definitions_dialog.raise_()
        self.bill_definitions_dialog.activateWindow()

    def on_income_definitions_changed(self) -> None:
        self.refresh_income()
        self.statusBar().showMessage(
            "Income definitions updated. Click Refresh Income to regenerate the selected month.",
            6000,
        )

    def show_income_definitions_dialog(self) -> None:
        if self.income_definitions_dialog is None:
            self.income_definitions_dialog = IncomeDefinitionsDialog(
                income_service=self.context.income_service,
                categories_repo=self.context.categories_repo,
                accounts_repo=self.context.accounts_repo,
                logger=self.logger,
                on_changed=self.on_income_definitions_changed,
                parent=self,
            )
            self.income_definitions_dialog.setAttribute(Qt.WA_DeleteOnClose, False)

        self.income_definitions_dialog.show()
        self.income_definitions_dialog.raise_()
        self.income_definitions_dialog.activateWindow()

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

    def _reports_selected_period(self) -> tuple[int, int | None]:
        year = int(self.reports_tab.year_picker.currentText())
        month_raw = self.reports_tab.month_picker.currentText().strip()
        month = int(month_raw) if month_raw else None
        return year, month

    @staticmethod
    def _reports_period_label(year: int, month: int | None) -> str:
        if month is None:
            return f"{year:04d}"
        return f"{year:04d}-{month:02d}"

    @staticmethod
    def _slugify_report_name(name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower())
        return slug.strip("_") or "report"

    def _build_report_content(self, report_key: str, year: int, month: int | None) -> tuple[str, str]:
        period_label = self._reports_period_label(year, month)

        if report_key == "tax_summary":
            title = f"Tax Deductible Summary - {period_label}"
            detail_rows = self.context.tax_service.detail(year)
            if month is not None:
                detail_rows = [
                    row for row in detail_rows
                    if str(row.get("txn_date") or "").startswith(f"{year:04d}-{month:02d}-")
                ]
            summary_by_category: dict[str, tuple[int, int]] = {}
            for row in detail_rows:
                category = str(row.get("tax_category") or "Uncategorized").strip() or "Uncategorized"
                amount_cents = abs(int(row.get("amount_cents") or 0))
                count, total = summary_by_category.get(category, (0, 0))
                summary_by_category[category] = (count + 1, total + amount_cents)
            lines = [title, ""]
            if not summary_by_category:
                lines.append("No tax-deductible transactions for this period.")
                return title, "\n".join(lines)
            lines.append("Category | Txn Count | Total")
            lines.append("----------------------------------------")
            for category in sorted(summary_by_category, key=str.casefold):
                count, total_cents = summary_by_category[category]
                lines.append(f"{category} | {count} | {self._format_currency(total_cents)}")
            return title, "\n".join(lines)

        if report_key == "tax_detail":
            title = f"Tax Deductible Detail - {period_label}"
            rows = self.context.tax_service.detail(year)
            if month is not None:
                rows = [
                    row for row in rows
                    if str(row.get("txn_date") or "").startswith(f"{year:04d}-{month:02d}-")
                ]
            lines = [title, ""]
            if not rows:
                lines.append("No tax-deductible transactions for this period.")
                return title, "\n".join(lines)
            lines.append("Date | Description | Amount | Tax Category")
            lines.append("---------------------------------------------------------------")
            for row in rows:
                amount_cents = abs(int(row.get("amount_cents") or 0))
                lines.append(
                    f"{row.get('txn_date') or ''} | "
                    f"{self._normalized_display_text(row.get('description'))} | "
                    f"{self._format_currency(amount_cents)} | "
                    f"{self._normalized_display_text(row.get('tax_category')) or '-'}"
                )
            return title, "\n".join(lines)

        if report_key == "budget_summary":
            title = f"Budget Summary - {period_label}"
            lines = [title, ""]
            months = [month] if month is not None else list(range(1, 13))
            annual_income = 0
            annual_expense = 0
            annual_net = 0
            lines.append("Period | Actual Income | Actual Expenses | Net")
            lines.append("--------------------------------------------------------------")
            for m in months:
                cashflow = self.context.budgeting_service.monthly_cashflow(
                    year=year,
                    month=int(m),
                    starting_balance_cents=0,
                )
                income_cents = int(cashflow.get("income_cents") or 0)
                expense_cents = int(cashflow.get("expense_cents") or 0)
                net_cents = int(cashflow.get("net_cents") or 0)
                annual_income += income_cents
                annual_expense += expense_cents
                annual_net += net_cents
                lines.append(
                    f"{year:04d}-{int(m):02d} | "
                    f"{self._format_currency(income_cents)} | "
                    f"{self._format_currency(expense_cents)} | "
                    f"{self._format_currency_signed(net_cents)}"
                )
            if month is None:
                lines.append("--------------------------------------------------------------")
                lines.append(
                    f"TOTAL {year:04d} | "
                    f"{self._format_currency(annual_income)} | "
                    f"{self._format_currency(annual_expense)} | "
                    f"{self._format_currency_signed(annual_net)}"
                )
            return title, "\n".join(lines)

        if report_key == "bills_summary":
            title = f"Bills and Category Sub-Totals - {period_label}"
            lines = [title, ""]
            months = [month] if month is not None else list(range(1, 13))
            all_rows: list[dict] = []
            for m in months:
                rows = self.context.bills_service.list_month_bills(
                    year=year,
                    month=int(m),
                    sort_by=self.bills_sort_key,
                )
                if month is None:
                    for row in rows:
                        row = dict(row)
                        row["period"] = f"{year:04d}-{int(m):02d}"
                        all_rows.append(row)
                else:
                    all_rows.extend(rows)

            if not all_rows:
                lines.append("No bills found for this period.")
                return title, "\n".join(lines)

            subtotal_by_category: dict[str, int] = {}
            for row in all_rows:
                category = str(row.get("category_name") or "Uncategorized").strip() or "Uncategorized"
                subtotal_by_category[category] = subtotal_by_category.get(category, 0) + int(
                    row.get("expected_amount_cents") or 0
                )

            lines.append("Category Sub-Totals")
            lines.append("----------------------------------------")
            grand_total = 0
            for category in sorted(subtotal_by_category, key=str.casefold):
                subtotal = int(subtotal_by_category[category])
                grand_total += subtotal
                lines.append(f"{category} | {self._format_currency(subtotal)}")
            lines.append(f"Total | {self._format_currency(grand_total)}")
            lines.append("")

            if month is None:
                lines.append("Bills Details")
                lines.append("Period | Category | Name | Due | Amount | Note")
                lines.append("--------------------------------------------------------------------------")
                for row in all_rows:
                    lines.append(
                        f"{row.get('period') or ''} | "
                        f"{self._normalized_display_text(row.get('category_name'))} | "
                        f"{self._normalized_display_text(row.get('name'))} | "
                        f"{self._normalized_display_text(row.get('payment_due'))} | "
                        f"{self._format_currency(int(row.get('expected_amount_cents') or 0))} | "
                        f"{self._normalized_display_text(row.get('notes'))}"
                    )
            else:
                lines.append("Bills Details")
                lines.append("Category | Name | Due | Amount | Note")
                lines.append("--------------------------------------------------------------")
                for row in all_rows:
                    lines.append(
                        f"{self._normalized_display_text(row.get('category_name'))} | "
                        f"{self._normalized_display_text(row.get('name'))} | "
                        f"{self._normalized_display_text(row.get('payment_due'))} | "
                        f"{self._format_currency(int(row.get('expected_amount_cents') or 0))} | "
                        f"{self._normalized_display_text(row.get('notes'))}"
                    )
            return title, "\n".join(lines)

        title = f"Report - {period_label}"
        return title, f"{title}\n\nNo report output."

    def _reports_export_start_dir(self) -> str:
        ui_settings = self.context.settings.get("ui", {})
        raw = str(ui_settings.get("last_reports_export_dir", "")).strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
        import_dir = str(ui_settings.get("last_import_dir", "")).strip()
        if import_dir:
            candidate = Path(import_dir).expanduser()
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
        return str(Path.home())

    def _persist_last_reports_export_dir(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
        except OSError:
            resolved = directory
        ui_settings = self.context.settings.setdefault("ui", {})
        new_value = str(resolved)
        if str(ui_settings.get("last_reports_export_dir", "")).strip() == new_value:
            return
        ui_settings["last_reports_export_dir"] = new_value
        try:
            get_settings_manager().save(self.context.settings)
        except OSError as exc:
            self.logger.error("Failed to persist reports export directory: %s", exc)

    @staticmethod
    def _write_report_docx(save_path: Path, title: str, body_text: str) -> None:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        title_paragraph = doc.add_paragraph()
        title_run = title_paragraph.add_run(title)
        title_run.bold = True
        title_run.font.name = "Arial"
        title_run.font.size = Pt(14)
        for line in body_text.splitlines():
            para = doc.add_paragraph(line)
            for run in para.runs:
                run.font.name = "Arial"
                run.font.size = Pt(12)
        doc.save(str(save_path))

    def run_selected_report(self) -> None:
        selected_reports = self.reports_tab.selected_reports()
        if not selected_reports:
            QMessageBox.information(self, "Reports", "Select one or more reports to run.")
            return

        year, month = self._reports_selected_period()
        period_label = self._reports_period_label(year, month)

        outputs: list[tuple[str, str, str]] = []
        for report_key, report_label in selected_reports:
            title, body = self._build_report_content(report_key, year, month)
            outputs.append((report_label, title, body))

        if self.reports_tab.preview_radio.isChecked():
            for _, title, body in outputs:
                dialog = ReportPreviewDialog(title=title, body=body, parent=self)
                dialog.setAttribute(Qt.WA_DeleteOnClose, True)
                self._open_report_previews.append(dialog)
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
            self.logger.info(
                "Previewed %s report(s) for %s",
                len(outputs),
                period_label,
            )
            return

        export_dir_raw = QFileDialog.getExistingDirectory(
            self,
            "Select Reports Export Directory",
            self._reports_export_start_dir(),
        )
        if not export_dir_raw:
            return
        export_dir = Path(export_dir_raw)
        self._persist_last_reports_export_dir(export_dir)

        exported_files: list[Path] = []
        for report_label, title, body in outputs:
            slug = self._slugify_report_name(report_label)
            output_file = export_dir / f"budgetpal_{slug}_{period_label}.docx"
            self._write_report_docx(output_file, title, body)
            exported_files.append(output_file)

        self.logger.info(
            "Exported %s report(s) to %s for %s",
            len(exported_files),
            export_dir,
            period_label,
        )
        self.statusBar().showMessage(
            f"Exported {len(exported_files)} report(s) to {export_dir}",
            6000,
        )

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
            backup_now_callback=self.backup_database_now,
            export_definitions_callback=self.export_global_definitions_now,
            logger=self.logger,
            parent=self,
        )
        accepted = bool(dialog.exec())

        if dialog.categories_dirty:
            self._refresh_transaction_form_choices()
            self._refresh_budget_form_choices()
            self._refresh_bill_form_choices()
            self.refresh_transactions()
            self.refresh_budget_allocations()
            self.refresh_bills()
            self.logger.info("Categories updated from Settings dialog")

        if not accepted:
            return

        new_settings = dialog.settings_value()
        old_db_path = str(self.context.settings.get("database", {}).get("path", "")).strip()
        old_subtracker_db_path = str(
            self.context.settings.get("subtracker", {}).get("database_path", "")
        ).strip()
        old_backup_cfg = dict(self.context.settings.get("backup", {}))
        old_categories_export_dir = str(
            self.context.settings.get("ui", {}).get("last_categories_export_dir", "")
        ).strip()
        old_definitions_export_dir = str(
            self.context.settings.get("ui", {}).get("last_definitions_export_dir", "")
        ).strip()
        old_window_cfg = self.context.settings.get("ui", {}).get("window", {})
        old_window_width = int(old_window_cfg.get("width", 1240))
        old_window_height = int(old_window_cfg.get("height", 820))
        old_logging_cfg = dict(self.context.settings.get("logging", {}))

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
        new_backup_cfg = dict(new_settings.get("backup", {}))
        restart_needed = old_db_path != new_db_path
        subtracker_changed = old_subtracker_db_path != new_subtracker_db_path

        self.logger.info("Settings saved to config file")
        if old_db_path != new_db_path:
            self.logger.info("Setting changed: database.path -> %s", new_db_path)
        if old_subtracker_db_path != new_subtracker_db_path:
            self.logger.info("Setting changed: subtracker.database_path -> %s", new_subtracker_db_path)
        if old_backup_cfg != new_backup_cfg:
            self.logger.info(
                "Setting changed: backup -> directory=%s, base_name=%s",
                str(new_backup_cfg.get("directory", "")),
                str(new_backup_cfg.get("base_name", "")),
            )
        new_categories_export_dir = str(
            new_settings.get("ui", {}).get("last_categories_export_dir", "")
        ).strip()
        if old_categories_export_dir != new_categories_export_dir:
            self.logger.info(
                "Setting changed: ui.last_categories_export_dir -> %s",
                new_categories_export_dir,
            )
        new_definitions_export_dir = str(
            new_settings.get("ui", {}).get("last_definitions_export_dir", "")
        ).strip()
        if old_definitions_export_dir != new_definitions_export_dir:
            self.logger.info(
                "Setting changed: ui.last_definitions_export_dir -> %s",
                new_definitions_export_dir,
            )
        if configured_width != old_window_width or configured_height != old_window_height:
            self.logger.info(
                "Setting changed: ui.window -> %sx%s",
                configured_width,
                configured_height,
            )
        if str(old_logging_cfg.get("level", "INFO")).upper() != level_name:
            self.logger.info("Setting changed: logging.level -> %s", level_name)
        new_max_bytes = int(new_settings.get("logging", {}).get("max_bytes", 1_000_000))
        new_backup_count = int(new_settings.get("logging", {}).get("backup_count", 5))
        if int(old_logging_cfg.get("max_bytes", 1_000_000)) != new_max_bytes:
            self.logger.info("Setting changed: logging.max_bytes -> %s", new_max_bytes)
        if int(old_logging_cfg.get("backup_count", 5)) != new_backup_count:
            self.logger.info("Setting changed: logging.backup_count -> %s", new_backup_count)
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

    @staticmethod
    def _sanitize_backup_base_name(base_name: str) -> str:
        raw = str(base_name or "").strip()
        if not raw:
            return "budgetpal_backup"
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
        return cleaned or "budgetpal_backup"

    def backup_database_now(self, directory: Path, base_name: str) -> Path:
        target_dir = Path(directory).expanduser()
        if not target_dir.exists() or not target_dir.is_dir():
            raise OSError("Backup location is not reachable.")
        safe_base = self._sanitize_backup_base_name(base_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = target_dir / f"{safe_base}_{timestamp}.sqlite"

        source = sqlite3.connect(str(self.context.db.db_path))
        dest = sqlite3.connect(str(output_path))
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

        self.logger.info("Database backup created: %s", output_path)
        self.statusBar().showMessage(f"Backup complete: {output_path.name}", 4000)
        return output_path

    def export_global_definitions_now(self, directory: Path) -> list[Path]:
        target_dir = Path(directory).expanduser()
        if not target_dir.exists() or not target_dir.is_dir():
            raise OSError("Definitions export location is not reachable.")
        outputs = self.reporting_service.export_global_definitions(target_dir)
        self.logger.info(
            "Global definitions exported to %s (%s files).",
            target_dir,
            len(outputs),
        )
        self.statusBar().showMessage(
            f"Exported global definitions to {target_dir}",
            5000,
        )
        return outputs

    def _backup_database_on_exit(self) -> None:
        backup_cfg = self.context.settings.get("backup", {})
        directory_raw = str(backup_cfg.get("directory", "")).strip()
        if not directory_raw:
            self.logger.info("Exit backup skipped: backup directory not configured.")
            return
        base_name = str(backup_cfg.get("base_name", "budgetpal_backup")).strip() or "budgetpal_backup"
        try:
            self.backup_database_now(Path(directory_raw), base_name)
            self.logger.info("Exit backup completed successfully.")
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Exit backup failed: %s", exc)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._backup_database_on_exit()
        super().closeEvent(event)

    def show_about_dialog(self) -> None:
        info = load_build_info()
        QMessageBox.about(
            self,
            "About BudgetPal",
            "BudgetPal\n"
            "Spend well!.\n\n"
            f"Version: {info.version}\n"
            f"Commit: {info.commit}\n"
            f"Built (UTC): {info.built_at_utc}",
        )

    def show_help(self) -> None:
        try:
            opened = self.help_service.open_main_help()
        except FileNotFoundError as exc:
            QMessageBox.warning(
                self,
                "Help Not Found",
                str(exc),
            )
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Help Error",
                f"Could not open help: {exc}",
            )
            return

        if not opened:
            try:
                path = self.help_service.get_topic_path("index")
                QMessageBox.information(
                    self,
                    "Help",
                    "Could not open the browser automatically.\n"
                    f"Open this file manually:\n{path}",
                )
            except Exception:  # noqa: BLE001
                pass
