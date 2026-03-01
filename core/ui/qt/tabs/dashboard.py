from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DashboardTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.month_picker = QComboBox()
        controls.addWidget(QLabel("Month:"))
        controls.addWidget(self.month_picker)
        controls.addStretch(1)

        self.import_button = QPushButton("Import Transactions")
        self.refresh_subs_button = QPushButton("Refresh Subscriptions")
        controls.addWidget(self.import_button)
        controls.addWidget(self.refresh_subs_button)

        root.addLayout(controls)

        cards_layout = QGridLayout()
        self.metric_labels: dict[str, QLabel] = {}
        metrics = [
            ("starting", "Starting Balance"),
            ("income", "Actual Income"),
            ("expenses", "Actual Expenses"),
            ("ending", "End Balance"),
            ("due", "Bills Due This Week"),
            ("over", "Overspent Categories"),
        ]

        for idx, (key, title) in enumerate(metrics):
            box = QGroupBox(title)
            form = QFormLayout(box)
            label = QLabel("0")
            form.addRow("Value", label)
            self.metric_labels[key] = label
            cards_layout.addWidget(box, idx // 3, idx % 3)

        root.addLayout(cards_layout)
        root.addStretch(1)
