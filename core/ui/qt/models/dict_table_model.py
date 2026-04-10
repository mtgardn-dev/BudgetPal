from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DictTableModel(QAbstractTableModel):
    def __init__(
        self,
        headers: list[str],
        key_order: list[str],
        rows: list[dict[str, Any]] | None = None,
        column_alignments: dict[int, Qt.AlignmentFlag] | None = None,
    ):
        super().__init__()
        self._headers = headers
        self._keys = key_order
        self._rows = rows or []
        self._column_alignments = column_alignments or {}

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._keys)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        if role == Qt.TextAlignmentRole:
            return int(self._column_alignments.get(index.column(), Qt.AlignLeft | Qt.AlignVCenter))
        if role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        value = row.get(self._keys[index.column()], "")
        return "" if value is None else str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._headers[section]
        return section + 1

    def replace_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_dict(self, row_index: int) -> dict[str, Any] | None:
        if row_index < 0 or row_index >= len(self._rows):
            return None
        return self._rows[row_index]
