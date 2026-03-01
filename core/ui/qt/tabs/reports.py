from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ReportsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.report_picker = QComboBox()
        self.report_picker.addItems(
            [
                "Tax deductible summary",
                "Tax deductible detail",
                "Monthly budget summary",
            ]
        )
        self.year_picker = QComboBox()
        current_year = date.today().year
        for year in range(current_year - 5, current_year + 2):
            self.year_picker.addItem(str(year))
        self.year_picker.setCurrentText(str(current_year))

        self.run_button = QPushButton("Run")
        self.export_button = QPushButton("Export CSV/PDF")
        controls.addWidget(QLabel("Report"))
        controls.addWidget(self.report_picker)
        controls.addWidget(QLabel("Year"))
        controls.addWidget(self.year_picker)
        controls.addWidget(self.run_button)
        controls.addWidget(self.export_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)
