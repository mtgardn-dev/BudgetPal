from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.balance_checking_model import BalanceCheckingTableModel


class BalanceCheckingTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(QLabel("Year/Month"), alignment=Qt.AlignLeft)
        self.month_filter = QComboBox()
        self.month_filter.setMinimumWidth(130)
        header_row.addWidget(self.month_filter, alignment=Qt.AlignLeft)
        header_row.addSpacing(12)
        header_row.addWidget(QLabel("Checking Account"), alignment=Qt.AlignLeft)
        self.account_filter = QComboBox()
        self.account_filter.setMinimumWidth(280)
        header_row.addWidget(self.account_filter, alignment=Qt.AlignLeft)
        header_row.addSpacing(12)
        self.view_heading = QLabel("Balance Checking")
        self.view_heading.setStyleSheet("font-weight: 600;")
        header_row.addWidget(self.view_heading, alignment=Qt.AlignLeft)
        header_row.addStretch(1)
        root.addLayout(header_row)

        balance_row = QHBoxLayout()
        balance_row.setContentsMargins(0, 0, 0, 0)
        balance_row.setSpacing(8)
        balance_row.addWidget(QLabel("Beginning Balance"), alignment=Qt.AlignLeft)
        self.beginning_balance_input = QLineEdit()
        self.beginning_balance_input.setPlaceholderText("0.00")
        self.beginning_balance_input.setFixedWidth(140)
        balance_row.addWidget(self.beginning_balance_input, alignment=Qt.AlignLeft)
        self.save_beginning_balance_button = QPushButton("Save")
        balance_row.addWidget(self.save_beginning_balance_button, alignment=Qt.AlignLeft)
        balance_row.addStretch(1)
        root.addLayout(balance_row)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(8)
        frame_layout.addWidget(QLabel("Checking Transactions and Running Balance"), alignment=Qt.AlignLeft)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addStretch(1)
        self.clear_all_button = QPushButton("Clear All")
        self.reset_all_button = QPushButton("Reset All")
        action_row.addWidget(self.clear_all_button)
        action_row.addWidget(self.reset_all_button)
        frame_layout.addLayout(action_row)

        self.table = QTableView()
        self.model = BalanceCheckingTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(380)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 92)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 74)
        frame_layout.addWidget(self.table, 1)

        root.addWidget(frame, 1)
