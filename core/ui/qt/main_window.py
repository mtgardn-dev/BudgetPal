from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_context import BudgetPalContext
from core.importers.subtracker_view import SubTrackerIntegrationError
from core.services.reporting import ReportingService
from core.ui.qt.tabs.bills import BillsTab
from core.ui.qt.tabs.buckets import BucketsTab
from core.ui.qt.tabs.budget_month import BudgetMonthTab
from core.ui.qt.tabs.dashboard import DashboardTab
from core.ui.qt.tabs.reports import ReportsTab
from core.ui.qt.tabs.transactions import TransactionsTab


class BudgetPalWindow(QMainWindow):
    def __init__(self, context: BudgetPalContext, logger: logging.Logger, log_emitter) -> None:
        super().__init__()
        self.context = context
        self.logger = logger
        self.log_emitter = log_emitter
        self.reporting_service = ReportingService(context.db)

        self.setWindowTitle("BudgetPal")
        self.resize(
            int(self.context.settings["ui"]["window"].get("width", 1240)),
            int(self.context.settings["ui"]["window"].get("height", 820)),
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
        self.setCentralWidget(self.tabs)

        self._init_log_dock()
        self.setStatusBar(QStatusBar())

        self._populate_month_selectors()
        self._wire_events()
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

        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(1000)
        layout.addWidget(self.log_area)

        dock.setWidget(holder)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

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
            self.bills_tab.month_picker,
        ]
        for selector in selectors:
            selector.clear()
            selector.addItems(month_labels)
            selector.setCurrentText(f"{current.year}-{current.month:02d}")

    def _wire_events(self) -> None:
        self.dashboard_tab.refresh_subs_button.clicked.connect(self.refresh_subscriptions)
        self.bills_tab.refresh_button.clicked.connect(self.refresh_subscriptions)
        self.dashboard_tab.import_button.clicked.connect(self._import_placeholder)
        self.transactions_tab.import_button.clicked.connect(self._import_placeholder)

        self.bills_tab.generate_button.clicked.connect(self.generate_bills_for_selected_month)
        self.bills_tab.month_picker.currentTextChanged.connect(lambda _: self.refresh_bills())
        self.reports_tab.run_button.clicked.connect(self.run_selected_report)
        self.reports_tab.export_button.clicked.connect(self.export_archive)

    def _import_placeholder(self) -> None:
        self.logger.info("Import requested (CSV workflow hook is ready for wiring in a dialog)")
        self.statusBar().showMessage("Import workflow not yet wired to file chooser", 5000)

    def _selected_year_month(self, selector) -> tuple[int, int]:
        raw = selector.currentText().strip()
        year_str, month_str = raw.split("-")
        return int(year_str), int(month_str)

    def refresh_transactions(self) -> None:
        rows = self.context.transactions_service.list_recent(limit=500)
        self.transactions_tab.model.replace_rows(rows)
        self.logger.info("Loaded %s transactions", len(rows))

    def generate_bills_for_selected_month(self) -> None:
        year, month = self._selected_year_month(self.bills_tab.month_picker)
        generated = self.context.bills_service.generate_for_month(year, month)
        self.logger.info("Generated/ensured bill occurrences for %s-%s (%s rows)", year, month, generated)
        self.refresh_bills()

    def refresh_bills(self) -> None:
        year, month = self._selected_year_month(self.bills_tab.month_picker)
        rows = self.context.bills_service.list_occurrences(year, month)
        self.bills_tab.model.replace_rows(rows)
        self.logger.info("Loaded %s bill occurrences for %s-%02d", len(rows), year, month)

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
            count = self.context.subscriptions_service.refresh_subtracker_bills()
            self.logger.info("Refreshed %s subscriptions from SubTracker", count)
            self.statusBar().showMessage(f"Refreshed {count} subscriptions", 4000)
            self.refresh_bills()
        except SubTrackerIntegrationError as exc:
            self.logger.error("SubTracker integration failed: %s", exc)
            QMessageBox.critical(self, "SubTracker Integration Error", str(exc))

    def run_selected_report(self) -> None:
        report_name = self.reports_tab.report_picker.currentText()
        year = int(self.reports_tab.year_picker.currentText())
        if report_name == "Tax deductible summary":
            rows = self.context.tax_service.summary(year)
            lines = [f"{r['tax_category']}: {r['total_cents']} cents ({r['txn_count']} txns)" for r in rows]
        elif report_name == "Tax deductible detail":
            rows = self.context.tax_service.detail(year)
            lines = [
                f"{r['txn_date']} | {r['payee']} | {r['amount_cents']} | {r['tax_category'] or '-'}"
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

    def append_log_message(self, message: str) -> None:
        self.log_area.appendPlainText(message)

    def _clear_log(self) -> None:
        self.log_area.clear()
        self.logger.info("Activity log cleared by user")
