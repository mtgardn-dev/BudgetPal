from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
        controls.addWidget(QLabel("Year/Month:"))
        controls.addWidget(self.month_picker)
        controls.addStretch(1)

        root.addLayout(controls)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(4)
        summary_title = QLabel("Monthly Budget")
        summary_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #EA580C;")
        summary_layout.addWidget(summary_title)

        metrics_grid = QGridLayout()
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setHorizontalSpacing(16)
        metrics_grid.setVerticalSpacing(2)
        metrics_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

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
        summary_layout.addStretch(1)
        top_row.addWidget(summary_frame, 2)

        account_status_frame = QFrame()
        account_status_frame.setFrameShape(QFrame.StyledPanel)
        account_status_layout = QVBoxLayout(account_status_frame)
        account_status_layout.setContentsMargins(10, 10, 10, 10)
        account_status_layout.setSpacing(8)
        self.account_status_title = QLabel("Account Status")
        self.account_status_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F766E;")
        account_status_layout.addWidget(self.account_status_title, alignment=Qt.AlignLeft)
        self.account_status_table = QTableView()
        self.account_status_model = DictTableModel(
            headers=["Account", "Beginning", "Activity (W/D)", "Ending"],
            key_order=[
                "account_name",
                "beginning_display",
                "activity_display",
                "ending_display",
            ],
            rows=[],
            column_alignments={
                1: Qt.AlignRight | Qt.AlignVCenter,
                3: Qt.AlignRight | Qt.AlignVCenter,
            },
        )
        self.account_status_table.setModel(self.account_status_model)
        self.account_status_table.setAlternatingRowColors(True)
        self.account_status_table.setSelectionMode(QTableView.NoSelection)
        self.account_status_table.setSelectionBehavior(QTableView.SelectRows)
        self.account_status_table.setEditTriggers(QTableView.NoEditTriggers)
        self.account_status_table.verticalHeader().setVisible(False)
        self.account_status_table.verticalHeader().setDefaultSectionSize(24)
        self.account_status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.account_status_table.setColumnWidth(1, 120)
        self.account_status_table.setColumnWidth(2, 180)
        self.account_status_table.setColumnWidth(3, 120)
        account_status_layout.addWidget(self.account_status_table, 1)

        account_total_row = QHBoxLayout()
        account_total_row.setContentsMargins(0, 0, 0, 0)
        account_total_row.setSpacing(8)
        account_total_row.addStretch(1)
        self.account_status_total_label = QLabel("Total")
        self.account_status_total_label.setStyleSheet("font-weight: 600;")
        self.account_status_total_value = QLabel("$0.00")
        self.account_status_total_value.setStyleSheet("font-weight: 700;")
        account_total_row.addWidget(self.account_status_total_label, alignment=Qt.AlignRight)
        account_total_row.addWidget(self.account_status_total_value, alignment=Qt.AlignRight)
        account_status_layout.addLayout(account_total_row)

        top_row.addWidget(account_status_frame, 2)
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
