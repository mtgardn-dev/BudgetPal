from __future__ import annotations

from core.ui.qt.models.dict_table_model import DictTableModel


class IncomeTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Category",
                "Description",
                "Payment Due",
                "Interval",
                "Amount",
                "Account",
                "Note",
            ],
            key_order=[
                "category_name",
                "description",
                "payment_due",
                "interval_display",
                "amount_display",
                "account_name",
                "notes",
            ],
            rows=rows,
        )
