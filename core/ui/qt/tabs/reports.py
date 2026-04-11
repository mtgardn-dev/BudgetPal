from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ReportPreviewDialog(QDialog):
    def __init__(self, title: str, body: str, parent=None) -> None:
        super().__init__(parent)
        self.setModal(False)
        self.resize(1000, 700)
        self.setWindowTitle(title)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 700;")
        header.addWidget(heading)
        header.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(body)
        root.addWidget(self.text, 1)


class ReportsTab(QWidget):
    REPORT_DEFS = [
        ("tax_summary", "Tax Deductible Summary"),
        ("tax_detail", "Tax Deductible Detail"),
        ("budget_summary", "Budget Summary"),
        ("bills_summary", "Bills and Category Sub-Totals"),
    ]

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        controls.addWidget(QLabel("Year/Month"), alignment=Qt.AlignLeft)
        controls.addWidget(QLabel("Year"), alignment=Qt.AlignLeft)
        self.year_picker = QComboBox()
        current_year = date.today().year
        for year in range(current_year - 5, current_year + 2):
            self.year_picker.addItem(str(year))
        self.year_picker.setCurrentText(str(current_year))
        self.year_picker.setMinimumWidth(90)
        controls.addWidget(self.year_picker, alignment=Qt.AlignLeft)

        controls.addWidget(QLabel("Month"), alignment=Qt.AlignLeft)
        self.month_picker = QComboBox()
        self.month_picker.addItem("")
        for month in range(1, 13):
            self.month_picker.addItem(f"{month:02d}")
        self.month_picker.setMinimumWidth(80)
        controls.addWidget(self.month_picker, alignment=Qt.AlignLeft)

        controls.addSpacing(14)
        mode_label = QLabel("Mode")
        controls.addWidget(mode_label, alignment=Qt.AlignLeft)
        self.preview_radio = QRadioButton("Preview")
        self.export_radio = QRadioButton("Export")
        self.preview_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.preview_radio)
        self.mode_group.addButton(self.export_radio)
        controls.addWidget(self.preview_radio, alignment=Qt.AlignLeft)
        controls.addWidget(self.export_radio, alignment=Qt.AlignLeft)

        self.run_button = QPushButton("Run")
        controls.addWidget(self.run_button)
        controls.addStretch(1)
        root.addLayout(controls)

        reports_frame = QTableWidget(0, 1, self)
        reports_frame.setHorizontalHeaderLabels(["Available Reports"])
        reports_frame.setSelectionBehavior(QAbstractItemView.SelectRows)
        reports_frame.setSelectionMode(QAbstractItemView.MultiSelection)
        reports_frame.verticalHeader().setDefaultSectionSize(26)
        reports_frame.horizontalHeader().setStretchLastSection(True)
        reports_frame.setMinimumHeight(340)
        self.reports_table = reports_frame
        root.addWidget(self.reports_table, 1)

        self._load_report_rows()

    def _load_report_rows(self) -> None:
        self.reports_table.setRowCount(0)
        self.reports_table.setRowCount(len(self.REPORT_DEFS))
        for idx, (key, label) in enumerate(self.REPORT_DEFS):
            item = QTableWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.reports_table.setItem(idx, 0, item)

    def selected_reports(self) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        seen_rows = set()
        for item in self.reports_table.selectedItems():
            row = int(item.row())
            if row in seen_rows:
                continue
            seen_rows.add(row)
            report_item = self.reports_table.item(row, 0)
            if report_item is None:
                continue
            key = str(report_item.data(Qt.UserRole) or "").strip()
            label = str(report_item.text() or "").strip()
            if key:
                selected.append((key, label))
        return selected
