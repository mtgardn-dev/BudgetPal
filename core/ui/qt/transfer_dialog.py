from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.domain import TransferInput


class TransferDialog(QDialog):
    def __init__(
        self,
        *,
        accounts: list[dict],
        default_from_account_id: int | None = None,
        default_to_account_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Transfer")
        self.resize(560, 280)
        self._transfer_input: TransferInput | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        subtitle = QLabel("Create an account-to-account transfer posting.")
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.txn_date_input = QLineEdit(date.today().isoformat())
        self.txn_date_input.setPlaceholderText("YYYY-MM-DD")
        self.txn_date_input.setFixedWidth(130)
        form.addRow("Date", self.txn_date_input)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(130)
        form.addRow("Amount", self.amount_input)

        self.from_account_combo = QComboBox()
        self.to_account_combo = QComboBox()
        self.from_account_combo.setMinimumWidth(320)
        self.to_account_combo.setMinimumWidth(320)
        self._populate_accounts(
            accounts=accounts,
            default_from_account_id=default_from_account_id,
            default_to_account_id=default_to_account_id,
        )
        form.addRow("From Account", self.from_account_combo)
        form.addRow("To Account", self.to_account_combo)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description")
        self.description_input.setMinimumWidth(420)
        form.addRow("Description", self.description_input)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        form.addRow("Note", self.note_input)

        self.payment_type_input = QLineEdit()
        self.payment_type_input.setPlaceholderText("Type (check, ach, online, etc.)")
        form.addRow("Type", self.payment_type_input)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save_clicked)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate_accounts(
        self,
        *,
        accounts: list[dict],
        default_from_account_id: int | None,
        default_to_account_id: int | None,
    ) -> None:
        self.from_account_combo.clear()
        self.to_account_combo.clear()
        for row in accounts:
            account_id = int(row["account_id"])
            label = str(row.get("display_label") or row.get("name") or f"Account #{account_id}")
            self.from_account_combo.addItem(label, account_id)
            self.to_account_combo.addItem(label, account_id)

        if self.from_account_combo.count() == 0:
            return

        from_idx = 0
        if default_from_account_id is not None:
            lookup = self.from_account_combo.findData(int(default_from_account_id))
            if lookup >= 0:
                from_idx = lookup
        self.from_account_combo.setCurrentIndex(from_idx)

        to_idx = 0
        if default_to_account_id is not None:
            lookup = self.to_account_combo.findData(int(default_to_account_id))
            if lookup >= 0:
                to_idx = lookup
        elif self.to_account_combo.count() > 1:
            to_idx = 1 if from_idx == 0 else 0
        self.to_account_combo.setCurrentIndex(to_idx)

    @staticmethod
    def _parse_positive_cents(amount_text: str) -> int:
        cleaned = amount_text.strip().replace("$", "").replace(",", "")
        if not cleaned:
            raise ValueError("Amount is required.")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric (example: 1100.00).") from exc

        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents <= 0:
            raise ValueError("Amount must be greater than 0.")
        return cents

    def _on_save_clicked(self) -> None:
        try:
            txn_date = self.txn_date_input.text().strip()
            if not txn_date:
                raise ValueError("Date is required.")
            datetime.strptime(txn_date, "%Y-%m-%d")

            amount_cents = self._parse_positive_cents(self.amount_input.text())
            from_account_id = int(self.from_account_combo.currentData() or 0)
            to_account_id = int(self.to_account_combo.currentData() or 0)
            if from_account_id <= 0 or to_account_id <= 0:
                raise ValueError("From and To accounts are required.")
            if from_account_id == to_account_id:
                raise ValueError("From and To accounts must be different.")

            description = self.description_input.text().strip()
            note = self.note_input.text().strip()
            payment_type = self.payment_type_input.text().strip()
            payee = description or "Transfer"

            self._transfer_input = TransferInput(
                txn_date=txn_date,
                amount_cents=amount_cents,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                payee=payee,
                description=description or None,
                note=note or None,
                payment_type=payment_type or None,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Transfer", str(exc))
            return

        self.accept()

    def transfer_input(self) -> TransferInput | None:
        return self._transfer_input
