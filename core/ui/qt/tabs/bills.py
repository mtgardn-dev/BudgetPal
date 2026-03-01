from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.bills_model import BillsTableModel


class BillsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.month_picker = QComboBox()
        self.auto_match_toggle = QCheckBox("Auto-match to transactions")
        self.auto_match_toggle.setEnabled(False)
        controls.addWidget(QLabel("Month:"))
        controls.addWidget(self.month_picker)
        controls.addStretch(1)
        controls.addWidget(self.auto_match_toggle)
        root.addLayout(controls)

        actions = QHBoxLayout()
        self.mark_paid_button = QPushButton("Mark Paid")
        self.adjust_button = QPushButton("Adjust Amount")
        self.refresh_button = QPushButton("Refresh SubTracker")
        self.generate_button = QPushButton("Generate Month")
        for button in [
            self.mark_paid_button,
            self.adjust_button,
            self.refresh_button,
            self.generate_button,
        ]:
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.table = QTableView()
        self.model = BillsTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)
