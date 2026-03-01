from __future__ import annotations

from core.ui.qt.models.dict_table_model import DictTableModel


class BillsTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Bill",
                "Expected Date",
                "Expected Amount",
                "Status",
                "Paid Date",
                "Paid Amount",
                "Autopay",
                "Source",
            ],
            key_order=[
                "name",
                "expected_date",
                "expected_amount_cents",
                "status",
                "paid_date",
                "paid_amount_cents",
                "autopay",
                "source_system",
            ],
            rows=rows,
        )
