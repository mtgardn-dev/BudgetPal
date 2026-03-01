from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.transactions_model import TransactionsTableModel


class TransactionsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.end_date = QDateEdit(QDate.currentDate())
        self.category_filter = QComboBox()
        self.account_filter = QComboBox()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search payee/description")
        self.tax_only = QCheckBox("Tax Deductible")

        filters.addWidget(QLabel("From"))
        filters.addWidget(self.start_date)
        filters.addWidget(QLabel("To"))
        filters.addWidget(self.end_date)
        filters.addWidget(QLabel("Category"))
        filters.addWidget(self.category_filter)
        filters.addWidget(QLabel("Account"))
        filters.addWidget(self.account_filter)
        filters.addWidget(self.search_input)
        filters.addWidget(self.tax_only)
        root.addLayout(filters)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import")
        self.reconcile_button = QPushButton("Mark Reconciled")
        for button in [
            self.add_button,
            self.edit_button,
            self.delete_button,
            self.import_button,
            self.reconcile_button,
        ]:
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.table = QTableView()
        self.model = TransactionsTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)
