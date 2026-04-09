from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
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

        self.new_txn_frame = QFrame()
        self.new_txn_frame.setFrameShape(QFrame.StyledPanel)
        form_layout = QVBoxLayout(self.new_txn_frame)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(8)

        heading = QLabel("New Transaction")
        heading.setStyleSheet("font-weight: 600;")
        form_layout.addWidget(heading, alignment=Qt.AlignLeft)

        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(8)

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
        self.type_group_box.setMaximumWidth(250)
        type_layout = QHBoxLayout()
        type_layout.setContentsMargins(8, 4, 8, 4)
        type_layout.setSpacing(8)
        type_layout.addWidget(self.expense_radio)
        type_layout.addWidget(self.income_radio)
        type_layout.addStretch(1)
        self.type_group_box.setLayout(type_layout)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setFixedWidth(120)
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description")
        self.description_input.setMaximumWidth(620)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Note")
        self.note_input.setMaximumWidth(620)
        self.payment_type_input = QLineEdit()
        self.payment_type_input.setPlaceholderText("Type")
        self.payment_type_input.setFixedWidth(220)
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
        self.category_input.setMaximumWidth(280)
        self.account_group = QButtonGroup(self)
        self.account_radios: dict[str, QRadioButton] = {}
        self.account_group_box = QGroupBox("Account")
        self.account_group_box.setMaximumWidth(500)
        account_layout = QHBoxLayout()
        account_layout.setContentsMargins(8, 4, 8, 4)
        account_layout.setSpacing(8)
        for account_type, label in (
            ("cash", "Cash"),
            ("checking", "Checking"),
            ("credit", "Credit"),
            ("savings", "Savings"),
        ):
            radio = QRadioButton(label)
            self.account_group.addButton(radio)
            self.account_radios[account_type] = radio
            account_layout.addWidget(radio)
        account_layout.addStretch(1)
        self.account_radios["checking"].setChecked(True)
        self.subscription_checkbox = QCheckBox("Subscription")
        self.tax_checkbox = QCheckBox("Tax")
        self.account_group_box.setLayout(account_layout)

        self.payment_type_holder = QWidget()
        payment_type_layout = QHBoxLayout(self.payment_type_holder)
        payment_type_layout.setContentsMargins(0, 0, 0, 0)
        payment_type_layout.setSpacing(6)
        payment_type_layout.addWidget(QLabel("Type"), alignment=Qt.AlignLeft)
        payment_type_layout.addWidget(self.payment_type_input, alignment=Qt.AlignLeft)
        payment_type_layout.addStretch(1)

        fields.setColumnStretch(7, 1)
        fields.addWidget(QLabel("Date"), 0, 0, alignment=Qt.AlignLeft)
        fields.addWidget(self.txn_date_input, 0, 1)
        fields.addWidget(QLabel("Amount"), 0, 2, alignment=Qt.AlignLeft)
        fields.addWidget(self.amount_input, 0, 3)
        fields.addWidget(self.type_group_box, 0, 4, alignment=Qt.AlignLeft)
        fields.addWidget(self.subscription_checkbox, 0, 5, alignment=Qt.AlignLeft)
        fields.addWidget(self.tax_checkbox, 0, 6, alignment=Qt.AlignLeft)

        fields.addWidget(QLabel("Description"), 1, 0, alignment=Qt.AlignLeft)
        fields.addWidget(self.description_input, 1, 1, 1, 4)

        fields.addWidget(QLabel("Category"), 2, 0, alignment=Qt.AlignLeft)
        fields.addWidget(self.category_input, 2, 1, 1, 2, alignment=Qt.AlignLeft)
        fields.addWidget(self.account_group_box, 2, 3, 1, 2, alignment=Qt.AlignLeft)
        fields.addWidget(self.payment_type_holder, 2, 5, 1, 2, alignment=Qt.AlignLeft)
        fields.addWidget(QLabel("Note"), 3, 0, alignment=Qt.AlignLeft)
        fields.addWidget(self.note_input, 3, 1, 1, 4, alignment=Qt.AlignLeft)

        form_layout.addLayout(fields)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.save_button = QPushButton("Save")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import")
        actions.addWidget(self.add_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.import_button)
        actions.addStretch(1)
        form_layout.addLayout(actions)

        self.editing_txn_id: int | None = None

        self.view_frame = QFrame()
        self.view_frame.setFrameShape(QFrame.StyledPanel)
        view_layout = QVBoxLayout(self.view_frame)
        view_layout.setContentsMargins(10, 10, 10, 10)
        view_layout.setSpacing(8)

        self.view_heading = QLabel("Transactions")
        self.view_heading.setStyleSheet("font-weight: 600;")
        view_header = QHBoxLayout()
        view_header.addWidget(QLabel("Month/Year"), alignment=Qt.AlignLeft)
        self.month_filter = QComboBox()
        self.month_filter.setMinimumWidth(130)
        view_header.addWidget(self.month_filter, alignment=Qt.AlignLeft)
        view_header.addSpacing(12)
        view_header.addWidget(self.view_heading, alignment=Qt.AlignLeft)
        view_header.addStretch(1)
        view_layout.addLayout(view_header)

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
