from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ReportsTab(QWidget):
    DEFAULT_REPORT_COLUMN_WIDTH = 340
    DEFAULT_DESCRIPTION_COLUMN_WIDTH = 620

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
        self.preview_after_export_checkbox = QCheckBox("Preview After Export")
        self.preview_after_export_checkbox.setChecked(False)
        controls.addWidget(self.preview_after_export_checkbox, alignment=Qt.AlignLeft)

        self.run_button = QPushButton("Run")
        controls.addWidget(self.run_button)
        controls.addStretch(1)
        root.addLayout(controls)

        reports_frame = QTableWidget(0, 2, self)
        reports_frame.setHorizontalHeaderLabels(["Report", "Description"])
        reports_frame.setSelectionBehavior(QAbstractItemView.SelectRows)
        reports_frame.setSelectionMode(QAbstractItemView.MultiSelection)
        reports_frame.verticalHeader().setDefaultSectionSize(26)
        header = reports_frame.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(120)
        header.resizeSection(0, self.DEFAULT_REPORT_COLUMN_WIDTH)
        header.resizeSection(1, self.DEFAULT_DESCRIPTION_COLUMN_WIDTH)
        reports_frame.setMinimumHeight(340)
        self.reports_table = reports_frame
        root.addWidget(self.reports_table, 1)

    def set_report_rows(self, rows: list[dict]) -> None:
        self.reports_table.setRowCount(0)
        self.reports_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            key = str(row.get("engine_key") or "").strip()
            name = str(row.get("display_name") or "").strip()
            description = str(row.get("description") or "").strip()
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, key)
            desc_item = QTableWidgetItem(description)
            self.reports_table.setItem(idx, 0, name_item)
            self.reports_table.setItem(idx, 1, desc_item)

    def selected_reports(self) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        seen_rows = set()
        for index in self.reports_table.selectionModel().selectedRows():
            row = int(index.row())
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

    def set_column_widths(self, report_width: int, description_width: int) -> None:
        report = max(120, int(report_width))
        description = max(120, int(description_width))
        header = self.reports_table.horizontalHeader()
        header.resizeSection(0, report)
        header.resizeSection(1, description)

    def column_widths(self) -> tuple[int, int]:
        return (
            int(self.reports_table.columnWidth(0)),
            int(self.reports_table.columnWidth(1)),
        )
