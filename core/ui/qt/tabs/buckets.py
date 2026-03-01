from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.dict_table_model import DictTableModel


class BucketsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.add_bucket_button = QPushButton("Add Bucket")
        self.add_movement_button = QPushButton("Add Movement")
        actions.addWidget(self.add_bucket_button)
        actions.addWidget(self.add_movement_button)
        actions.addStretch(1)
        root.addLayout(actions)

        splitter = QSplitter()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Buckets"))
        self.bucket_list = QListWidget()
        left_layout.addWidget(self.bucket_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Movements"))
        self.ledger_table = QTableView()
        self.ledger_model = DictTableModel(
            headers=["Date", "Amount", "Note", "Linked Txn"],
            key_order=["movement_date", "amount_cents", "note", "linked_txn_id"],
            rows=[],
        )
        self.ledger_table.setModel(self.ledger_model)
        right_layout.addWidget(self.ledger_table)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])
        root.addWidget(splitter)
