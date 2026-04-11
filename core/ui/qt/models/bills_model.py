from __future__ import annotations

from core.ui.qt.models.dict_table_model import DictTableModel


class BillsTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Category",
                "Name",
                "Payment Due",
                "Date Paid",
                "Interval",
                "Amount",
                "Note",
            ],
            key_order=[
                "category_name",
                "name",
                "payment_due",
                "paid_date",
                "interval_display",
                "amount_display",
                "notes",
            ],
            rows=rows,
        )
