from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.dict_table_model import DictTableModel


class BudgetMonthTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.month_picker = QComboBox()
        self.copy_button = QPushButton("Copy Planned From Prior Month")
        self.export_button = QPushButton("Export Monthly Report")
        controls.addWidget(QLabel("Month:"))
        controls.addWidget(self.month_picker)
        controls.addStretch(1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.export_button)
        root.addLayout(controls)

        summary = QHBoxLayout()
        self.start_label = QLabel("Starting: 0")
        self.end_label = QLabel("End: 0")
        self.net_label = QLabel("Net: 0")
        summary.addWidget(self.start_label)
        summary.addWidget(self.net_label)
        summary.addWidget(self.end_label)
        summary.addStretch(1)
        root.addLayout(summary)

        self.income_table = QTableView()
        self.expense_table = QTableView()

        columns = ["Category", "Planned", "Actual", "Variance"]
        keys = ["category_name", "planned_cents", "actual_cents", "variance_cents"]
        self.income_model = DictTableModel(columns, keys, [])
        self.expense_model = DictTableModel(columns, keys, [])
        self.income_table.setModel(self.income_model)
        self.expense_table.setModel(self.expense_model)

        root.addWidget(QLabel("Income"))
        root.addWidget(self.income_table)
        root.addWidget(QLabel("Expenses"))
        root.addWidget(self.expense_table)
