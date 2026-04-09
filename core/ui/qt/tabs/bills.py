from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.bills_model import BillsTableModel
from core.ui.qt.models.dict_table_model import DictTableModel


class BillsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(QLabel("Month/Year"))
        self.month_filter = QComboBox()
        self.month_filter.setMinimumWidth(130)
        header_row.addWidget(self.month_filter)
        self.view_heading = QLabel("Bills for")
        header_row.addWidget(self.view_heading)
        header_row.addStretch(1)
        root.addLayout(header_row)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(8)

        left_holder = QWidget()
        left_layout = QVBoxLayout(left_holder)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        details_layout.addWidget(QLabel("Bill Details"))

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)

        self.bill_name_input = QLineEdit()
        self.bill_name_input.setPlaceholderText("Name")
        name_chars_width = self.bill_name_input.fontMetrics().horizontalAdvance("X" * 50) + 20
        self.bill_name_input.setFixedWidth(name_chars_width)

        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        self.start_date_input.setFixedWidth(140)

        self.interval_count_input = QLineEdit("1")
        self.interval_count_input.setFixedWidth(60)
        self.interval_unit_combo = QComboBox()
        self.interval_unit_combo.addItems(["days", "weeks", "months", "years"])
        self.interval_unit_combo.setCurrentText("months")
        self.interval_unit_combo.setFixedWidth(120)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(120)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.setInsertPolicy(QComboBox.NoInsert)
        self.category_input.setMinimumWidth(220)
        self.category_input.setMaximumWidth(320)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMinimumWidth(260)
        self.note_input.setMaximumWidth(460)

        form.addWidget(QLabel("Name"), 0, 0)
        form.addWidget(self.bill_name_input, 0, 1)
        form.addWidget(QLabel("Start Date"), 0, 2)
        form.addWidget(self.start_date_input, 0, 3)

        form.addWidget(QLabel("Interval"), 1, 0)
        interval_holder = QWidget()
        interval_row = QHBoxLayout(interval_holder)
        interval_row.setContentsMargins(0, 0, 0, 0)
        interval_row.setSpacing(6)
        interval_row.addWidget(self.interval_count_input)
        interval_row.addWidget(self.interval_unit_combo)
        form.addWidget(interval_holder, 1, 1)

        form.addWidget(QLabel("Amount (USD)"), 1, 2)
        form.addWidget(self.amount_input, 1, 3)

        form.addWidget(QLabel("Category"), 2, 0)
        form.addWidget(self.category_input, 2, 1, 1, 2)
        form.addWidget(QLabel("Note"), 3, 0)
        form.addWidget(self.note_input, 3, 1, 1, 2)
        form.setColumnStretch(4, 1)
        details_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.new_button = QPushButton("New")
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        action_row.addWidget(self.new_button)
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        details_layout.addLayout(action_row)

        self.editing_bill_id: int | None = None
        left_layout.addWidget(details_frame, 0)

        list_frame = QFrame()
        list_frame.setFrameShape(QFrame.StyledPanel)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)
        list_layout.addWidget(QLabel("Bills"))

        self.table = QTableView()
        self.model = BillsTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(300)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 105)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 95)
        self.table.horizontalHeader().setStretchLastSection(True)
        list_layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self.sort_name_button = QPushButton("Sort by Name")
        self.sort_category_button = QPushButton("Sort by Category")
        self.sort_due_button = QPushButton("Sort by Payment Due")
        self.refresh_subtracker_button = QPushButton("Refresh SubTracker")
        self.report_button = QPushButton("Report")
        controls.addWidget(self.sort_name_button)
        controls.addWidget(self.sort_category_button)
        controls.addWidget(self.sort_due_button)
        controls.addWidget(self.refresh_subtracker_button)
        controls.addWidget(self.report_button)
        controls.addStretch(1)
        list_layout.addLayout(controls)

        left_layout.addWidget(list_frame, 1)

        right_holder = QWidget()
        right_layout = QVBoxLayout(right_holder)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        totals_frame = QFrame()
        totals_frame.setFrameShape(QFrame.StyledPanel)
        totals_layout = QVBoxLayout(totals_frame)
        totals_layout.setContentsMargins(10, 10, 10, 10)
        totals_layout.setSpacing(6)
        totals_layout.addWidget(QLabel("Totals"))
        total_row = QHBoxLayout()
        total_row.setContentsMargins(0, 0, 0, 0)
        total_row.setSpacing(8)
        total_row.addWidget(QLabel("All Categories"))
        self.total_subtotals_value_label = QLabel("$0.00")
        total_row.addWidget(self.total_subtotals_value_label)
        total_row.addStretch(1)
        totals_layout.addLayout(total_row)
        right_layout.addWidget(totals_frame, 0)

        subtotals_frame = QFrame()
        subtotals_frame.setFrameShape(QFrame.StyledPanel)
        subtotals_layout = QVBoxLayout(subtotals_frame)
        subtotals_layout.setContentsMargins(10, 10, 10, 10)
        subtotals_layout.setSpacing(8)
        subtotals_layout.addWidget(QLabel("Category Sub-Totals"))

        self.category_totals_table = QTableView()
        self.category_totals_model = DictTableModel(
            headers=["Category", "Subtotal"],
            key_order=["category_name", "subtotal_display"],
            rows=[],
        )
        self.category_totals_table.setModel(self.category_totals_model)
        self.category_totals_table.setAlternatingRowColors(True)
        self.category_totals_table.setSelectionMode(QTableView.NoSelection)
        self.category_totals_table.setSelectionBehavior(QTableView.SelectRows)
        self.category_totals_table.verticalHeader().setDefaultSectionSize(26)
        self.category_totals_table.setMinimumHeight(300)
        self.category_totals_table.setColumnWidth(0, 220)
        self.category_totals_table.setColumnWidth(1, 110)
        self.category_totals_table.horizontalHeader().setStretchLastSection(True)
        subtotals_layout.addWidget(self.category_totals_table, 1)

        right_layout.addWidget(subtotals_frame, 1)

        content_row.addWidget(left_holder, 2)
        content_row.addWidget(right_holder, 1)
        root.addLayout(content_row, 1)
