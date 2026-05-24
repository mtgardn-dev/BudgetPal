from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor

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

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if index.isValid() and role == Qt.ForegroundRole:
            row = self.row_dict(index.row())
            if row is not None and bool(row.get("_is_modified_month_entry")):
                return QColor("#006400")
        return super().data(index, role)
