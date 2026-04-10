from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt, Signal

from core.ui.qt.models.dict_table_model import DictTableModel


class BalanceCheckingTableModel(DictTableModel):
    txn_cleared_toggled = Signal(int, bool)

    def __init__(self, rows: list[dict] | None = None):
        super().__init__(
            headers=[
                "Type",
                "Date",
                "Description",
                "Note",
                "Amount",
                "Balance",
                "Cleared",
            ],
            key_order=[
                "payment_type_display",
                "txn_date",
                "description_display",
                "note_display",
                "amount_display",
                "running_balance_display",
                "is_cleared",
            ],
            rows=rows,
        )

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        row = self.row_dict(index.row())
        if row is None:
            return None

        if index.column() == 6 and role == Qt.CheckStateRole:
            return Qt.Checked if bool(row.get("is_cleared")) else Qt.Unchecked
        if index.column() == 6 and role == Qt.DisplayRole:
            return ""
        if role == Qt.TextAlignmentRole and index.column() in (4, 5):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role != Qt.DisplayRole:
            return None

        key = self._keys[index.column()]
        value = row.get(key, "")
        return "" if value is None else str(value)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        base_flags = super().flags(index)
        if index.isValid() and index.column() == 6:
            return base_flags | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
        return base_flags

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if not index.isValid() or index.column() != 6 or role != Qt.CheckStateRole:
            return False
        row = self.row_dict(index.row())
        if row is None:
            return False

        new_value = value == Qt.Checked
        if bool(row.get("is_cleared")) == new_value:
            return False

        row["is_cleared"] = new_value
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])

        txn_id = int(row.get("txn_id") or 0)
        if txn_id > 0:
            self.txn_cleared_toggled.emit(txn_id, new_value)
        return True
