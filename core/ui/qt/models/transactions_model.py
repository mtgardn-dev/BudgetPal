from __future__ import annotations

from core.ui.qt.models.dict_table_model import DictTableModel


class TransactionsTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Date",
                "Payee",
                "Amount (cents)",
                "Type",
                "Category",
                "Account",
                "Tax",
            ],
            key_order=[
                "txn_date",
                "payee",
                "amount_cents",
                "txn_type",
                "category_name",
                "account_name",
                "tax_category",
            ],
            rows=rows,
        )
