from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ManualTransferDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Transfer Details")
        self.setModal(False)
        self.resize(620, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("Transfer Details")
        title.setStyleSheet("font-weight: 600;")
        header.addWidget(title, 0, Qt.AlignLeft)
        header.addStretch(1)
        self.close_button = QPushButton("Close")
        header.addWidget(self.close_button, 0, Qt.AlignRight)
        root.addLayout(header)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.transfer_date_input = QLineEdit()
        self.transfer_date_input.setPlaceholderText("YYYY-MM-DD")
        self.transfer_date_input.setFixedWidth(130)
        form.addRow("Date", self.transfer_date_input)

        self.transfer_amount_input = QLineEdit()
        self.transfer_amount_input.setPlaceholderText("0.00")
        self.transfer_amount_input.setFixedWidth(130)
        form.addRow("Amount", self.transfer_amount_input)

        self.transfer_from_account_combo = QComboBox()
        self.transfer_from_account_combo.setMinimumWidth(360)
        form.addRow("From", self.transfer_from_account_combo)

        self.transfer_to_account_combo = QComboBox()
        self.transfer_to_account_combo.setMinimumWidth(360)
        form.addRow("To", self.transfer_to_account_combo)

        self.transfer_description_input = QLineEdit()
        self.transfer_description_input.setPlaceholderText("Description")
        self.transfer_description_input.setMinimumWidth(420)
        form.addRow("Description", self.transfer_description_input)

        self.transfer_note_input = QLineEdit()
        self.transfer_note_input.setPlaceholderText("Note")
        self.transfer_note_input.setMinimumWidth(420)
        form.addRow("Note", self.transfer_note_input)

        root.addLayout(form)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.transfer_new_button = QPushButton("New")
        self.transfer_save_button = QPushButton("Save")
        self.transfer_delete_button = QPushButton("Delete")
        actions.addWidget(self.transfer_new_button, 0, Qt.AlignLeft)
        actions.addWidget(self.transfer_save_button, 0, Qt.AlignLeft)
        actions.addWidget(self.transfer_delete_button, 0, Qt.AlignLeft)
        actions.addStretch(1)
        root.addLayout(actions)

