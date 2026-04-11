from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(QLabel("Year/Month"))
        self.month_picker = QComboBox()
        self.month_picker.setMinimumWidth(130)
        header_row.addWidget(self.month_picker)
        self.view_heading = QLabel("Budget Allocations for")
        header_row.addWidget(self.view_heading)
        header_row.addStretch(1)
        root.addLayout(header_row)

        top_content_row = QHBoxLayout()
        top_content_row.setContentsMargins(0, 0, 0, 0)
        top_content_row.setSpacing(8)

        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(4)
        details_layout.addWidget(QLabel("Budget Allocation Details"))

        self.category_input = QComboBox()
        self.category_input.setEditable(False)
        self.category_input.setMinimumWidth(260)
        self.category_input.setMaximumWidth(360)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(130)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMinimumWidth(420)
        self.note_input.setMaximumWidth(760)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(4)
        row1.addWidget(QLabel("Category"))
        row1.addWidget(self.category_input)
        row1.addWidget(QLabel("Amount"))
        row1.addWidget(self.amount_input)
        row1.addStretch(1)
        details_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(4)
        row2.addWidget(QLabel("Note"))
        row2.addWidget(self.note_input)
        row2.addStretch(1)
        details_layout.addLayout(row2)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        details_layout.addLayout(action_row)
        details_layout.addStretch(1)

        self.editing_budget_line_id: int | None = None
        top_content_row.addWidget(details_frame, 1, Qt.AlignTop)

        totals_frame = QFrame()
        totals_frame.setFrameShape(QFrame.StyledPanel)
        totals_layout = QVBoxLayout(totals_frame)
        totals_layout.setContentsMargins(10, 10, 10, 10)
        totals_layout.setSpacing(4)
        totals_layout.addWidget(QLabel("Budget Allocation Totals"))

        self.totals_table = QTableView()
        self.totals_model = DictTableModel(
            headers=["Metric", "Value"],
            key_order=["metric", "value_display"],
            rows=[],
            column_alignments={1: Qt.AlignRight | Qt.AlignVCenter},
        )
        self.totals_table.setModel(self.totals_model)
        self.totals_table.setAlternatingRowColors(True)
        self.totals_table.setSelectionMode(QTableView.NoSelection)
        self.totals_table.setSelectionBehavior(QTableView.SelectRows)
        self.totals_table.setEditTriggers(QTableView.NoEditTriggers)
        self.totals_table.verticalHeader().setVisible(False)
        self.totals_table.verticalHeader().setDefaultSectionSize(26)
        self.totals_table.horizontalHeader().setStretchLastSection(False)
        self.totals_table.setColumnWidth(0, 220)
        self.totals_table.setColumnWidth(1, 205)
        self.totals_table.setFixedWidth(450)
        totals_layout.addWidget(self.totals_table, 0, Qt.AlignLeft)

        totals_layout.addStretch(1)
        top_content_row.addWidget(totals_frame, 1, Qt.AlignTop)
        root.addLayout(top_content_row, 0)

        list_frame = QFrame()
        list_frame.setFrameShape(QFrame.StyledPanel)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)
        list_layout.addWidget(QLabel("Monthly Budget Category Allocations"))

        self.table = QTableView()
        self.model = DictTableModel(
            headers=["Category", "Allocation", "Planned Bills", "Diff", "Note"],
            key_order=[
                "category_name",
                "allocation_display",
                "planned_bills_display",
                "diff_display",
                "note",
            ],
            rows=[],
        )
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(320)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 120)
        self.table.horizontalHeader().setStretchLastSection(True)
        list_layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self.definitions_button = QPushButton("Define Global Budget Categories")
        self.refresh_button = QPushButton("Refresh Budget Categories")
        controls.addWidget(self.definitions_button)
        controls.addWidget(self.refresh_button)
        controls.addStretch(1)
        list_layout.addLayout(controls)

        root.addWidget(list_frame, 1)
