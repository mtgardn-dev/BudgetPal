from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.transactions_model import TransactionsTableModel


class TransactionsTab(QWidget):
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
        self.view_heading = QLabel("Transactions")
        self.view_heading.setStyleSheet("font-weight: 600;")
        header_row.addWidget(self.view_heading, alignment=Qt.AlignLeft)
        header_row.addStretch(1)
        root.addLayout(header_row)

        self.new_txn_frame = QFrame()
        self.new_txn_frame.setFrameShape(QFrame.StyledPanel)
        form_layout = QVBoxLayout(self.new_txn_frame)
        form_layout.setContentsMargins(6, 6, 6, 6)
        form_layout.setSpacing(4)

        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(8)
        heading = QLabel("New Transaction")
        heading.setStyleSheet("font-weight: 600;")
        heading_row.addWidget(heading, alignment=Qt.AlignLeft)
        heading_row.addStretch(1)
        self.transfer_semantics_badge = QLabel(
            "Transfer note: Outgoing transfer legs appear in Expenses only. "
            "See the Transfers tab for complete transfer pairs."
        )
        self.transfer_semantics_badge.setWordWrap(True)
        self.transfer_semantics_badge.setStyleSheet(
            "padding: 4px 8px; border: 1px solid #4B5563; border-radius: 4px;"
        )
        self.transfer_semantics_badge.setMaximumWidth(520)
        heading_row.addWidget(self.transfer_semantics_badge, alignment=Qt.AlignRight | Qt.AlignTop)
        form_layout.addLayout(heading_row)

        fields = QVBoxLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(4)

        self.txn_date_input = QLineEdit()
        self.txn_date_input.setPlaceholderText("yyyy-mm-dd")
        self.txn_date_input.setFixedWidth(130)
        self.txn_type_group = QButtonGroup(self)
        self.expense_radio = QRadioButton("Expense")
        self.income_radio = QRadioButton("Income")
        self.expense_radio.setChecked(True)
        self.txn_type_group.addButton(self.expense_radio)
        self.txn_type_group.addButton(self.income_radio)
        self.type_group_box = QGroupBox("Txn Type")
        self.type_group_box.setMaximumWidth(200)
        type_layout = QHBoxLayout()
        type_layout.setContentsMargins(8, 4, 8, 4)
        type_layout.setSpacing(8)
        type_layout.addWidget(self.expense_radio)
        type_layout.addWidget(self.income_radio)
        type_layout.addStretch(1)
        self.type_group_box.setLayout(type_layout)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(110)
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description")
        self.description_input.setMaximumWidth(560)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMinimumWidth(560)
        self.note_input.setMaximumWidth(560)
        self.payment_type_input = QLineEdit()
        self.payment_type_input.setPlaceholderText("Type")
        self.payment_type_input.setFixedWidth(150)
        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.setInsertPolicy(QComboBox.NoInsert)
        self.category_input.setMaxVisibleItems(24)
        category_completer = QCompleter(self.category_input.model(), self.category_input)
        category_completer.setCaseSensitivity(Qt.CaseInsensitive)
        category_completer.setFilterMode(Qt.MatchContains)
        category_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.category_input.setCompleter(category_completer)
        self.category_input.setMinimumWidth(220)
        self.category_input.setMaximumWidth(220)
        self.account_input = QComboBox()
        self.account_input.setEditable(False)
        self.account_input.setMinimumWidth(230)
        self.account_input.setMaximumWidth(230)
        self.account_input.addItem("", None)
        self.subscription_checkbox = QCheckBox("Subscription")
        self.tax_checkbox = QCheckBox("Tax")

        self.payment_type_holder = QWidget()
        payment_type_layout = QHBoxLayout(self.payment_type_holder)
        payment_type_layout.setContentsMargins(0, 0, 0, 0)
        payment_type_layout.setSpacing(6)
        payment_type_layout.addWidget(QLabel("Type"), alignment=Qt.AlignLeft)
        payment_type_layout.addWidget(self.payment_type_input, alignment=Qt.AlignLeft)
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        row1.addWidget(QLabel("Date"), alignment=Qt.AlignLeft)
        row1.addWidget(self.txn_date_input, alignment=Qt.AlignLeft)
        row1.addWidget(QLabel("Amount"), alignment=Qt.AlignLeft)
        row1.addWidget(self.amount_input, alignment=Qt.AlignLeft)
        row1.addWidget(self.type_group_box, alignment=Qt.AlignLeft)
        row1.addWidget(self.subscription_checkbox, alignment=Qt.AlignLeft)
        row1.addWidget(self.tax_checkbox, alignment=Qt.AlignLeft)
        row1.addStretch(1)
        fields.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        row2.addWidget(QLabel("Description"), alignment=Qt.AlignLeft)
        row2.addWidget(self.description_input, alignment=Qt.AlignLeft)
        row2.addStretch(1)
        fields.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)
        row3.addWidget(QLabel("Category"), alignment=Qt.AlignLeft)
        row3.addWidget(self.category_input, alignment=Qt.AlignLeft)
        row3.addWidget(QLabel("Account"), alignment=Qt.AlignLeft)
        row3.addWidget(self.account_input, alignment=Qt.AlignLeft)
        row3.addWidget(self.payment_type_holder, alignment=Qt.AlignLeft)
        row3.addStretch(1)
        fields.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setContentsMargins(0, 0, 0, 0)
        row4.setSpacing(6)
        row4.addWidget(QLabel("Note"), alignment=Qt.AlignLeft)
        row4.addWidget(self.note_input, alignment=Qt.AlignLeft)
        row4.addStretch(1)
        fields.addLayout(row4)

        form_layout.addLayout(fields)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.add_button = QPushButton("Add")
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import Transactions")
        self.sub_payments_button = QPushButton("Send Subscription Payments")
        actions.addWidget(self.add_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.import_button)
        actions.addWidget(self.sub_payments_button)
        actions.addStretch(1)
        form_layout.addLayout(actions)

        self.editing_txn_id: int | None = None

        self.view_frame = QFrame()
        self.view_frame.setFrameShape(QFrame.StyledPanel)
        view_layout = QVBoxLayout(self.view_frame)
        view_layout.setContentsMargins(10, 10, 10, 10)
        view_layout.setSpacing(8)

        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(10)

        expenses_col = QVBoxLayout()
        expenses_col.addWidget(QLabel("Expenses"), alignment=Qt.AlignLeft)
        self.expenses_table = QTableView()
        self.expense_model = TransactionsTableModel([])
        self.expenses_table.setModel(self.expense_model)
        self.expenses_table.setAlternatingRowColors(True)
        self.expenses_table.setSelectionBehavior(QTableView.SelectRows)
        self.expenses_table.setSelectionMode(QTableView.SingleSelection)
        self.expenses_table.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.expenses_table.setMinimumHeight(300)
        self.expenses_table.verticalHeader().setDefaultSectionSize(26)
        self.expenses_table.horizontalHeader().setStretchLastSection(False)
        self.expenses_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.expenses_table.setColumnWidth(0, 100)
        self.expenses_table.setColumnWidth(2, 77)
        self.expenses_table.setColumnWidth(3, 130)
        self.expenses_table.setColumnWidth(4, 91)
        self.expenses_table.setColumnWidth(5, 81)
        self.expenses_table.setColumnWidth(6, 55)
        self.expenses_table.setColumnWidth(7, 55)
        expenses_col.addWidget(self.expenses_table, 1)

        income_col = QVBoxLayout()
        income_col.addWidget(QLabel("Income"), alignment=Qt.AlignLeft)
        self.income_table = QTableView()
        self.income_model = TransactionsTableModel([])
        self.income_table.setModel(self.income_model)
        self.income_table.setAlternatingRowColors(True)
        self.income_table.setSelectionBehavior(QTableView.SelectRows)
        self.income_table.setSelectionMode(QTableView.SingleSelection)
        self.income_table.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.income_table.setMinimumHeight(300)
        self.income_table.verticalHeader().setDefaultSectionSize(26)
        self.income_table.horizontalHeader().setStretchLastSection(False)
        self.income_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.income_table.setColumnWidth(0, 100)
        self.income_table.setColumnWidth(2, 77)
        self.income_table.setColumnWidth(3, 130)
        self.income_table.setColumnWidth(4, 91)
        self.income_table.setColumnWidth(5, 81)
        self.income_table.setColumnWidth(6, 55)
        self.income_table.setColumnWidth(7, 55)
        income_col.addWidget(self.income_table, 1)

        tables_layout.addLayout(expenses_col, 1)
        tables_layout.addLayout(income_col, 1)
        view_layout.addLayout(tables_layout, 1)

        root.addWidget(self.new_txn_frame, 0)
        root.addWidget(self.view_frame, 1)

        self.expenses_table.horizontalScrollBar().rangeChanged.connect(
            lambda *_: self._apply_table_bottom_padding(self.expenses_table)
        )
        self.income_table.horizontalScrollBar().rangeChanged.connect(
            lambda *_: self._apply_table_bottom_padding(self.income_table)
        )
        self.ensure_bottom_rows_visible()

    @staticmethod
    def _apply_table_bottom_padding(table: QTableView) -> None:
        hbar = table.horizontalScrollBar()
        scrollbar_height = int(hbar.sizeHint().height() or 0)
        # Reserve enough bottom space even when macOS overlay scrollbars are hidden until scroll.
        # This keeps the last row fully visible at scroll-bottom without resizing the window.
        bottom_padding = max(24, scrollbar_height + 10)
        table.setViewportMargins(0, 0, 0, bottom_padding)
        table.doItemsLayout()
        table.updateGeometries()
        table.viewport().update()

    def ensure_bottom_rows_visible(self) -> None:
        self._apply_table_bottom_padding(self.expenses_table)
        self._apply_table_bottom_padding(self.income_table)
        QTimer.singleShot(0, lambda: self._apply_table_bottom_padding(self.expenses_table))
        QTimer.singleShot(0, lambda: self._apply_table_bottom_padding(self.income_table))
