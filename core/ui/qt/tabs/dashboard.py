from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.dict_table_model import DictTableModel


class DashboardTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self.month_picker = QComboBox()
        controls.addWidget(QLabel("Month:"))
        controls.addWidget(self.month_picker)
        controls.addStretch(1)

        self.import_button = QPushButton("Import Transactions")
        self.refresh_subs_button = QPushButton("Refresh Subscriptions")
        controls.addWidget(self.import_button)
        controls.addWidget(self.refresh_subs_button)

        root.addLayout(controls)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(8)
        summary_title = QLabel("Monthly Budget")
        summary_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #EA580C;")
        summary_layout.addWidget(summary_title)

        metrics_grid = QGridLayout()
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setHorizontalSpacing(16)
        metrics_grid.setVerticalSpacing(8)

        self.starting_balance_input = QLineEdit()
        self.starting_balance_input.setPlaceholderText("0.00")
        self.starting_balance_input.setFixedWidth(150)
        self.end_balance_value = QLabel("$0.00")
        self.end_balance_value.setStyleSheet("font-weight: 600;")
        self.planned_expenses_value = QLabel("$0.00")
        self.actual_expenses_value = QLabel("$0.00")
        self.planned_income_value = QLabel("$0.00")
        self.actual_income_value = QLabel("$0.00")

        metrics_grid.addWidget(QLabel("Starting Balance"), 0, 0)
        metrics_grid.addWidget(self.starting_balance_input, 0, 1)
        metrics_grid.addWidget(QLabel("End Balance"), 0, 2)
        metrics_grid.addWidget(self.end_balance_value, 0, 3)

        metrics_grid.addWidget(QLabel("Planned Expenses"), 1, 0)
        metrics_grid.addWidget(self.planned_expenses_value, 1, 1)
        metrics_grid.addWidget(QLabel("Planned Income"), 1, 2)
        metrics_grid.addWidget(self.planned_income_value, 1, 3)

        metrics_grid.addWidget(QLabel("Actual Expenses"), 2, 0)
        metrics_grid.addWidget(self.actual_expenses_value, 2, 1)
        metrics_grid.addWidget(QLabel("Actual Income"), 2, 2)
        metrics_grid.addWidget(self.actual_income_value, 2, 3)
        metrics_grid.setColumnStretch(4, 1)
        summary_layout.addLayout(metrics_grid)
        top_row.addWidget(summary_frame, 2)

        savings_frame = QFrame()
        savings_frame.setFrameShape(QFrame.StyledPanel)
        savings_layout = QVBoxLayout(savings_frame)
        savings_layout.setContentsMargins(10, 10, 10, 10)
        savings_layout.setSpacing(8)
        savings_layout.addWidget(QLabel("Savings (TBD)"))
        self.savings_placeholder_value = QLabel("TBD")
        self.savings_placeholder_value.setStyleSheet("font-size: 24px; font-weight: 700;")
        savings_layout.addWidget(self.savings_placeholder_value)
        self.savings_placeholder_note = QLabel("Reserved for future savings metrics")
        savings_layout.addWidget(self.savings_placeholder_note)
        savings_layout.addStretch(1)
        top_row.addWidget(savings_frame, 1)
        root.addLayout(top_row)

        tables_row = QHBoxLayout()
        tables_row.setContentsMargins(0, 0, 0, 0)
        tables_row.setSpacing(8)

        expenses_frame = QFrame()
        expenses_frame.setFrameShape(QFrame.StyledPanel)
        expenses_layout = QVBoxLayout(expenses_frame)
        expenses_layout.setContentsMargins(10, 10, 10, 10)
        expenses_layout.setSpacing(8)
        expenses_title = QLabel("Expenses")
        expenses_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #EA580C;")
        expenses_layout.addWidget(expenses_title)
        self.expenses_table = QTableView()
        self.expenses_model = DictTableModel(
            headers=["Category", "Planned", "Actual", "Diff"],
            key_order=["category_name", "planned_display", "actual_display", "diff_display"],
            rows=[],
        )
        self.expenses_table.setModel(self.expenses_model)
        self.expenses_table.setAlternatingRowColors(True)
        self.expenses_table.setSelectionMode(QTableView.NoSelection)
        self.expenses_table.setSelectionBehavior(QTableView.SelectRows)
        self.expenses_table.setEditTriggers(QTableView.NoEditTriggers)
        self.expenses_table.verticalHeader().setDefaultSectionSize(24)
        self.expenses_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.expenses_table.setColumnWidth(1, 110)
        self.expenses_table.setColumnWidth(2, 110)
        self.expenses_table.setColumnWidth(3, 110)
        expenses_layout.addWidget(self.expenses_table, 1)
        tables_row.addWidget(expenses_frame, 1)

        income_frame = QFrame()
        income_frame.setFrameShape(QFrame.StyledPanel)
        income_layout = QVBoxLayout(income_frame)
        income_layout.setContentsMargins(10, 10, 10, 10)
        income_layout.setSpacing(8)
        income_title = QLabel("Income")
        income_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #EA580C;")
        income_layout.addWidget(income_title)
        self.income_table = QTableView()
        self.income_model = DictTableModel(
            headers=["Category", "Planned", "Actual", "Diff"],
            key_order=["category_name", "planned_display", "actual_display", "diff_display"],
            rows=[],
        )
        self.income_table.setModel(self.income_model)
        self.income_table.setAlternatingRowColors(True)
        self.income_table.setSelectionMode(QTableView.NoSelection)
        self.income_table.setSelectionBehavior(QTableView.SelectRows)
        self.income_table.setEditTriggers(QTableView.NoEditTriggers)
        self.income_table.verticalHeader().setDefaultSectionSize(24)
        self.income_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.income_table.setColumnWidth(1, 110)
        self.income_table.setColumnWidth(2, 110)
        self.income_table.setColumnWidth(3, 110)
        income_layout.addWidget(self.income_table, 1)
        tables_row.addWidget(income_frame, 1)

        root.addLayout(tables_row, 1)
