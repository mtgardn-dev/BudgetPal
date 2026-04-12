from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt

from core.ui.qt.models.dict_table_model import DictTableModel


class TransfersTableModel(DictTableModel):
    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "ID",
                "Type",
                "Date",
                "From Account",
                "To Account",
                "Amount",
            ],
            key_order=[
                "transfer_id_suffix",
                "transfer_type",
                "txn_date",
                "from_account_alias",
                "to_account_alias",
                "amount_cents",
            ],
            rows=rows,
            column_alignments={
                0: Qt.AlignCenter | Qt.AlignVCenter,
                5: Qt.AlignRight | Qt.AlignVCenter,
            },
        )

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        if role == Qt.TextAlignmentRole and index.column() == 5:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.TextAlignmentRole and index.column() == 0:
            return int(Qt.AlignCenter | Qt.AlignVCenter)
        if role != Qt.DisplayRole:
            return super().data(index, role)

        row = self.row_dict(index.row())
        if row is None:
            return None
        key = self._keys[index.column()]
        if key == "amount_cents":
            cents = int(row.get("amount_cents") or 0)
            return f"${cents / 100:,.2f}"

        value = row.get(key, "")
        return "" if value is None else str(value)
