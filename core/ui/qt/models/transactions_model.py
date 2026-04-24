from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt

from core.ui.qt.models.dict_table_model import DictTableModel


class TransactionsTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Date",
                "Description",
                "Amount",
                "Category",
                "Account",
                "Payment Type",
                "Sub",
                "Tax",
            ],
            key_order=[
                "txn_date",
                "description_display",
                "display_amount_cents",
                "category_name",
                "account_name",
                "payment_type",
                "is_subscription",
                "tax_deductible",
            ],
            rows=rows,
        )

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        row = self.row_dict(index.row())
        if row is None:
            return None
        if bool(row.get("_is_spacer_row")):
            if role == Qt.DisplayRole:
                return ""
            return None

        if role == Qt.TextAlignmentRole and index.column() == 2:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.TextAlignmentRole and index.column() in (6, 7):
            return int(Qt.AlignCenter | Qt.AlignVCenter)

        if role != Qt.DisplayRole:
            return None

        key = self._keys[index.column()]
        if key == "display_amount_cents":
            cents = int(row.get("display_amount_cents", 0))
            return f"${cents / 100:,.2f}"
        if key == "is_subscription":
            return "✓" if bool(row.get("is_subscription")) else ""
        if key == "tax_deductible":
            return "✓" if bool(row.get("tax_deductible")) else ""

        value = row.get(key, "")
        return "" if value is None else str(value)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        base_flags = super().flags(index)
        row = self.row_dict(index.row())
        if row is not None and bool(row.get("_is_spacer_row")):
            return Qt.ItemIsEnabled
        return base_flags
