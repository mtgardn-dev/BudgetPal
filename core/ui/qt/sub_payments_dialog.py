from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.services.subscription_payments import SubscriptionPaymentsService


class SubPaymentsDialog(QDialog):
    def __init__(
        self,
        service: SubscriptionPaymentsService,
        logger: logging.Logger,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.logger = logger
        self.year = 0
        self.month = 0
        self.subscriptions: list[dict] = []

        self.setWindowTitle("Subscription Payments")
        self.setModal(False)
        self.resize(1220, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.heading_label = QLabel("Subscription payments")
        self.heading_label.setStyleSheet("font-weight: 600;")
        root.addWidget(self.heading_label, alignment=Qt.AlignLeft)

        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(
            ["Send", "Txn ID", "Date", "Description", "Amount", "Account", "Subscription", "Status"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 340)
        self.table.setColumnWidth(7, 250)
        self.table.setColumnHidden(1, True)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.reload_button = QPushButton("Reload")
        self.select_all_button = QPushButton("Select All")
        self.reset_all_button = QPushButton("Reset All")
        self.process_button = QPushButton("Process Payments")
        self.close_button = QPushButton("Close")
        buttons.addWidget(self.reload_button)
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.reset_all_button)
        buttons.addWidget(self.process_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)

        self.reload_button.clicked.connect(self.reload_rows)
        self.select_all_button.clicked.connect(self.select_all_rows_for_processing)
        self.reset_all_button.clicked.connect(self.reset_all_rows_for_processing)
        self.process_button.clicked.connect(self.process_payments)
        self.close_button.clicked.connect(self.close)

    def open_month(self, year: int, month: int) -> None:
        self.year = year
        self.month = month
        self.heading_label.setText(f"Subscription payments for {year}-{month:02d}")
        self.reload_rows()

    @staticmethod
    def _amount_item(amount_cents: int) -> QTableWidgetItem:
        item = QTableWidgetItem(f"${abs(amount_cents) / 100:,.2f}")
        item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

    @staticmethod
    def _send_item(checked: bool) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        item.setFlags(
            Qt.ItemIsSelectable
            | Qt.ItemIsEnabled
            | Qt.ItemIsUserCheckable
        )
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return item

    @staticmethod
    def _parse_amount_cents(text: str) -> int:
        cleaned = text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            raise ValueError("Amount is required.")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid amount '{text}'.") from exc
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents <= 0:
            raise ValueError("Amount must be greater than 0.")
        return cents

    @staticmethod
    def _status_text(row: dict) -> str:
        status = str(row.get("last_post_status") or "unposted")
        payment_id = row.get("subtracker_payment_id")
        if status == "posted":
            if payment_id is not None:
                return f"Posted (payment #{int(payment_id)})"
            return "Posted"
        if status == "error":
            err = str(row.get("last_error") or "").strip()
            return f"Error: {err}" if err else "Error"
        return "Unposted"

    def _build_subscription_combo(self, selected_sub_id: int | None) -> QComboBox:
        combo = QComboBox(self.table)
        combo.setEditable(False)
        combo.addItem("", None)
        for sub in self.subscriptions:
            sub_id = int(sub["sub_id"])
            vendor = str(sub.get("vendor") or "")
            combo.addItem(f"{vendor} ({sub_id})", sub_id)
        if selected_sub_id is not None:
            index = combo.findData(int(selected_sub_id))
            if index >= 0:
                combo.setCurrentIndex(index)
        return combo

    def reload_rows(self) -> None:
        if self.year <= 0 or self.month <= 0:
            return

        payload = self.service.load_month_candidates(self.year, self.month)
        self.subscriptions = list(payload["subscriptions"])
        candidates = list(payload["candidates"])

        self.table.setRowCount(0)
        self.table.setRowCount(len(candidates))

        for idx, row in enumerate(candidates):
            txn_id = int(row["txn_id"])
            self.table.setItem(idx, 0, self._send_item(True))
            self.table.setItem(idx, 1, QTableWidgetItem(str(txn_id)))
            self.table.setItem(idx, 2, QTableWidgetItem(str(row.get("txn_date") or "")))
            self.table.setItem(idx, 3, QTableWidgetItem(str(row.get("description") or "")))
            self.table.setItem(idx, 4, self._amount_item(int(row.get("display_amount_cents") or 0)))
            self.table.setItem(idx, 5, QTableWidgetItem(str(row.get("account_name") or "")))
            combo = self._build_subscription_combo(
                int(row["selected_sub_id"]) if row.get("selected_sub_id") is not None else None
            )
            self.table.setCellWidget(idx, 6, combo)
            self.table.setItem(idx, 7, QTableWidgetItem(self._status_text(row)))

        self.logger.info(
            "Loaded %s subscription expense candidates for %s-%02d",
            len(candidates),
            self.year,
            self.month,
        )

    def select_all_rows_for_processing(self) -> None:
        for row in range(self.table.rowCount()):
            send_item = self.table.item(row, 0)
            if send_item is not None:
                send_item.setCheckState(Qt.Checked)

    def reset_all_rows_for_processing(self) -> None:
        for row in range(self.table.rowCount()):
            send_item = self.table.item(row, 0)
            if send_item is not None:
                send_item.setCheckState(Qt.Unchecked)

    def _collect_selections(self) -> dict[int, dict[str, int | None]]:
        selections: dict[int, dict[str, int | None]] = {}
        for row in range(self.table.rowCount()):
            send_item = self.table.item(row, 0)
            if send_item is None or send_item.checkState() != Qt.Checked:
                continue
            txn_item = self.table.item(row, 1)
            amount_item = self.table.item(row, 4)
            combo = self.table.cellWidget(row, 6)
            if txn_item is None or amount_item is None or not isinstance(combo, QComboBox):
                continue
            txn_id = int(txn_item.text())
            selected = combo.currentData()
            amount_cents = self._parse_amount_cents(amount_item.text())
            selections[txn_id] = {
                "sub_id": int(selected) if selected is not None else None,
                "amount_cents": amount_cents,
            }
        return selections

    def process_payments(self) -> None:
        try:
            selections = self._collect_selections()
        except ValueError as exc:
            QMessageBox.warning(self, "Sub Payments Validation Error", str(exc))
            return
        selected_count = len(selections)
        result = self.service.process_month(self.year, self.month, selections)
        self.reload_rows()

        summary = (
            f"Processed {selected_count} selected rows "
            f"(out of {result['total_candidates']} candidates).\n\n"
            f"New payments: {result['posted_count']}\n"
            f"Updated payments: {result['updated_count']}\n"
            f"Unmapped skipped: {result['unmapped_count']}\n"
            f"Errors: {result['error_count']}"
        )

        if result["error_count"] > 0:
            QMessageBox.warning(self, "Sub Payments Completed With Errors", summary)
            return
        if result["unmapped_count"] > 0:
            QMessageBox.warning(self, "Sub Payments Completed", summary)
            return
        QMessageBox.information(self, "Sub Payments Completed", summary)
