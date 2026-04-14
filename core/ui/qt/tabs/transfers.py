from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.transfers_model import TransfersTableModel


class TransfersTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(QLabel("Year/Month"), alignment=Qt.AlignLeft)
        self.month_filter = QComboBox()
        self.month_filter.setMinimumWidth(130)
        header_row.addWidget(self.month_filter, alignment=Qt.AlignLeft)
        header_row.addSpacing(12)
        self.view_heading = QLabel("Transfers")
        self.view_heading.setStyleSheet("font-weight: 600;")
        header_row.addWidget(self.view_heading, alignment=Qt.AlignLeft)
        header_row.addStretch(1)
        root.addLayout(header_row)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(8)

        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.StyledPanel)
        details_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(4)
        details_layout.addWidget(QLabel("New Transfer"), alignment=Qt.AlignLeft)

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)

        self.transfer_date_input = QLineEdit()
        self.transfer_date_input.setPlaceholderText("YYYY-MM-DD")
        self.transfer_date_input.setFixedWidth(130)

        self.transfer_amount_input = QLineEdit()
        self.transfer_amount_input.setPlaceholderText("0.00")
        self.transfer_amount_input.setFixedWidth(130)

        self.transfer_from_account_combo = QComboBox()
        self.transfer_from_account_combo.setMinimumWidth(300)

        self.transfer_to_account_combo = QComboBox()
        self.transfer_to_account_combo.setMinimumWidth(300)

        self.transfer_description_input = QLineEdit()
        self.transfer_description_input.setPlaceholderText("Description")

        self.transfer_note_input = QLineEdit()
        self.transfer_note_input.setPlaceholderText("Note")

        form.addWidget(QLabel("Date"), 0, 0, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_date_input, 0, 1, alignment=Qt.AlignLeft)
        form.addWidget(QLabel("Amount"), 0, 2, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_amount_input, 0, 3, alignment=Qt.AlignLeft)

        form.addWidget(QLabel("From"), 1, 0, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_from_account_combo, 1, 1, 1, 3)

        form.addWidget(QLabel("To"), 2, 0, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_to_account_combo, 2, 1, 1, 3)

        form.addWidget(QLabel("Description"), 3, 0, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_description_input, 3, 1, 1, 3)

        form.addWidget(QLabel("Note"), 4, 0, alignment=Qt.AlignLeft)
        form.addWidget(self.transfer_note_input, 4, 1, 1, 3)
        form.setColumnStretch(4, 1)
        details_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.transfer_save_button = QPushButton("Save")
        self.transfer_delete_button = QPushButton("Delete")
        action_row.addWidget(self.transfer_save_button)
        action_row.addWidget(self.transfer_delete_button)
        action_row.addStretch(1)
        details_layout.addLayout(action_row)

        list_frame = QFrame()
        list_frame.setFrameShape(QFrame.StyledPanel)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)
        list_layout.addWidget(QLabel("Transfers"), alignment=Qt.AlignLeft)

        self.transfers_table = QTableView()
        self.transfers_model = TransfersTableModel([])
        self.transfers_table.setModel(self.transfers_model)
        self.transfers_table.setAlternatingRowColors(True)
        self.transfers_table.setSelectionBehavior(QTableView.SelectRows)
        self.transfers_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.transfers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.transfers_table.setMinimumHeight(420)
        self.transfers_table.verticalHeader().setDefaultSectionSize(26)
        self.transfers_table.horizontalHeader().setStretchLastSection(False)
        self.transfers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.transfers_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.transfers_table.setColumnWidth(0, 70)
        self.transfers_table.setColumnWidth(1, 90)
        self.transfers_table.setColumnWidth(2, 95)
        self.transfers_table.setColumnWidth(5, 105)
        list_layout.addWidget(self.transfers_table, 1)

        left_holder = QWidget()
        left_layout = QVBoxLayout(left_holder)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(details_frame, 0, Qt.AlignTop)
        left_layout.addStretch(1)

        content_row.addWidget(left_holder, 1)
        content_row.addWidget(list_frame, 1)
        root.addLayout(content_row, 1)
