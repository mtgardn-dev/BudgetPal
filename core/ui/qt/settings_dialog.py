from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BudgetPal Settings")
        self.resize(700, 360)
        self._settings = deepcopy(settings)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignTop)

        info_label = QLabel(
            "Note: changing database path applies on next app launch. "
            "SubTracker path and logging settings apply after saving."
        )
        info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(info_label)

        form_holder = QWidget()
        form = QFormLayout(form_holder)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.database_path_edit, db_browse = self._path_row(
            self._settings.get("database", {}).get("path", "")
        )
        db_browse.clicked.connect(lambda: self._pick_file(self.database_path_edit, "Select BudgetPal DB"))
        form.addRow("BudgetPal DB Path", self._row_widget(self.database_path_edit, db_browse))

        self.subtracker_path_edit, sub_browse = self._path_row(
            self._settings.get("subtracker", {}).get("database_path", "")
        )
        sub_browse.clicked.connect(
            lambda: self._pick_file(self.subtracker_path_edit, "Select SubTracker DB")
        )
        form.addRow(
            "SubTracker DB Path",
            self._row_widget(self.subtracker_path_edit, sub_browse),
        )

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText(
            str(self._settings.get("logging", {}).get("level", "INFO")).upper()
        )
        form.addRow("Log Level", self.log_level_combo)

        self.max_bytes_edit = self._int_line_edit(
            int(self._settings.get("logging", {}).get("max_bytes", 1_000_000)),
            100_000,
            50_000_000,
        )
        form.addRow("Log Max Bytes", self.max_bytes_edit)

        self.backup_count_edit = self._int_line_edit(
            int(self._settings.get("logging", {}).get("backup_count", 5)),
            1,
            100,
        )
        form.addRow("Log Backup Count", self.backup_count_edit)

        self.window_width_edit = self._int_line_edit(
            int(self._settings.get("ui", {}).get("window", {}).get("width", 1240)),
            640,
            4000,
        )
        form.addRow("Window Width", self.window_width_edit)

        self.window_height_edit = self._int_line_edit(
            int(self._settings.get("ui", {}).get("window", {}).get("height", 820)),
            480,
            4000,
        )
        form.addRow("Window Height", self.window_height_edit)

        root.addWidget(form_holder)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _path_row(initial_value: str) -> tuple[QLineEdit, QPushButton]:
        edit = QLineEdit(initial_value)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        browse = QPushButton("Browse")
        browse.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return edit, browse

    @staticmethod
    def _row_widget(edit: QLineEdit, button: QPushButton) -> QWidget:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(button)
        row_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return row_widget

    @staticmethod
    def _int_line_edit(value: int, min_value: int, max_value: int) -> QLineEdit:
        edit = QLineEdit(str(value))
        edit.setValidator(QIntValidator(min_value, max_value, edit))
        return edit

    def _pick_file(self, target: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            target.text(),
            "DB Files (*.db *.sqlite *.sqlite3);;All Files (*)",
        )
        if path:
            target.setText(path)

    def _save_and_accept(self) -> None:
        try:
            settings = deepcopy(self._settings)
            settings["database"]["path"] = self.database_path_edit.text().strip()
            settings["subtracker"]["database_path"] = self.subtracker_path_edit.text().strip()
            settings["logging"]["level"] = self.log_level_combo.currentText().strip().upper()
            settings["logging"]["max_bytes"] = int(self.max_bytes_edit.text().strip())
            settings["logging"]["backup_count"] = int(self.backup_count_edit.text().strip())
            settings["ui"]["window"]["width"] = int(self.window_width_edit.text().strip())
            settings["ui"]["window"]["height"] = int(self.window_height_edit.text().strip())
            self._settings = settings
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid Settings", f"Could not parse settings: {exc}")
            return

        self.accept()

    def settings_value(self) -> dict:
        return deepcopy(self._settings)
