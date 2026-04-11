from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.persistence.repositories.categories_repo import CategoriesRepository
from core.settings import get_settings_manager


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: dict,
        categories_repo: CategoriesRepository | None = None,
        backup_now_callback: Callable[[Path, str], Path] | None = None,
        logger=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("BudgetPal Settings")
        self.resize(760, 560)
        self._settings = deepcopy(settings)
        self._categories_repo = categories_repo
        self._selected_category_id: int | None = None
        self._categories_dirty = False
        self._backup_now_callback = backup_now_callback
        self._logger = logger

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

        self.backup_dir_edit, backup_browse = self._path_row(
            self._settings.get("backup", {}).get("directory", "")
        )
        backup_browse.clicked.connect(
            lambda: self._pick_directory(self.backup_dir_edit, "Select Backup Directory")
        )
        form.addRow(
            "Backup Location",
            self._row_widget(self.backup_dir_edit, backup_browse),
        )

        self.backup_base_name_edit = QLineEdit(
            str(self._settings.get("backup", {}).get("base_name", "budgetpal_backup"))
        )
        form.addRow("Backup Base Name", self.backup_base_name_edit)

        self.categories_export_dir_edit, categories_export_browse = self._path_row(
            str(self._settings.get("ui", {}).get("last_categories_export_dir", ""))
        )
        categories_export_browse.clicked.connect(
            lambda: self._pick_directory(
                self.categories_export_dir_edit,
                "Select Categories Export Directory",
            )
        )
        form.addRow(
            "Categories Export Location",
            self._row_widget(self.categories_export_dir_edit, categories_export_browse),
        )

        backup_button_holder = QWidget()
        backup_button_layout = QHBoxLayout(backup_button_holder)
        backup_button_layout.setContentsMargins(0, 0, 0, 0)
        backup_button_layout.setSpacing(8)
        self.backup_now_button = QPushButton("Backup Now")
        self.backup_now_button.clicked.connect(self._on_backup_now_clicked)
        backup_button_layout.addWidget(self.backup_now_button, alignment=Qt.AlignLeft)
        backup_button_layout.addStretch(1)
        form.addRow("", backup_button_holder)

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
        root.addWidget(self._build_categories_frame())

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

    def _pick_directory(self, target: QLineEdit, title: str) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            title,
            target.text().strip() or str(Path.home()),
        )
        if selected:
            target.setText(selected)

    def _save_and_accept(self) -> None:
        try:
            settings = deepcopy(self._settings)
            settings["database"]["path"] = self.database_path_edit.text().strip()
            settings["subtracker"]["database_path"] = self.subtracker_path_edit.text().strip()
            backup_dir = self.backup_dir_edit.text().strip()
            backup_base = self.backup_base_name_edit.text().strip()
            settings.setdefault("backup", {})
            settings["backup"]["directory"] = backup_dir
            settings["backup"]["base_name"] = backup_base or "budgetpal_backup"
            settings.setdefault("ui", {})
            categories_export_dir = self.categories_export_dir_edit.text().strip()
            settings["ui"]["last_categories_export_dir"] = categories_export_dir
            settings["logging"]["level"] = self.log_level_combo.currentText().strip().upper()
            settings["logging"]["max_bytes"] = int(self.max_bytes_edit.text().strip())
            settings["logging"]["backup_count"] = int(self.backup_count_edit.text().strip())
            settings["ui"]["window"]["width"] = int(self.window_width_edit.text().strip())
            settings["ui"]["window"]["height"] = int(self.window_height_edit.text().strip())
            if backup_dir:
                backup_path = Path(backup_dir).expanduser()
                if not backup_path.exists() or not backup_path.is_dir():
                    raise ValueError("Backup location must be an existing directory.")
            if categories_export_dir:
                categories_export_path = Path(categories_export_dir).expanduser()
                if not categories_export_path.exists() or not categories_export_path.is_dir():
                    raise ValueError("Categories export location must be an existing directory.")
            self._settings = settings
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid Settings", f"Could not parse settings: {exc}")
            return

        self.accept()

    def _on_backup_now_clicked(self) -> None:
        if self._backup_now_callback is None:
            QMessageBox.warning(self, "Backup", "Backup service is unavailable.")
            return

        backup_dir_raw = self.backup_dir_edit.text().strip()
        if not backup_dir_raw:
            QMessageBox.warning(self, "Backup", "Backup location is required.")
            return
        backup_dir = Path(backup_dir_raw).expanduser()
        if not backup_dir.exists() or not backup_dir.is_dir():
            QMessageBox.warning(self, "Backup", "Backup location must be an existing directory.")
            return

        base_name = self.backup_base_name_edit.text().strip() or "budgetpal_backup"
        try:
            output_path = self._backup_now_callback(backup_dir, base_name)
        except Exception as exc:  # noqa: BLE001
            if self._logger is not None:
                self._logger.error("Backup now failed from Settings: %s", exc)
            QMessageBox.warning(self, "Backup", f"Backup failed: {exc}")
            return

        QMessageBox.information(self, "Backup", f"Backup complete:\n{output_path}")
        if self._logger is not None:
            self._logger.info("Backup now completed from Settings: %s", output_path)

    def settings_value(self) -> dict:
        return deepcopy(self._settings)

    @property
    def categories_dirty(self) -> bool:
        return self._categories_dirty

    def _build_categories_frame(self) -> QGroupBox:
        categories_frame = QGroupBox("Categories")
        categories_layout = QHBoxLayout(categories_frame)
        categories_layout.setContentsMargins(10, 10, 10, 10)
        categories_layout.setSpacing(10)
        categories_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        new_group = QGroupBox("New Category")
        new_layout = QVBoxLayout(new_group)
        new_layout.setContentsMargins(10, 10, 10, 10)
        new_layout.setSpacing(8)
        new_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        new_form = QFormLayout()
        new_form.setContentsMargins(0, 0, 0, 0)
        new_form.setHorizontalSpacing(10)
        new_form.setVerticalSpacing(8)
        new_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        new_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.category_name_edit = QLineEdit()
        self.category_name_edit.setPlaceholderText("Category")
        self.category_name_edit.setMinimumWidth(260)
        new_form.addRow("Category", self.category_name_edit)
        new_layout.addLayout(new_form)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        buttons_row.setSpacing(8)
        self.category_new_button = QPushButton("New")
        self.category_save_button = QPushButton("Save")
        self.category_delete_button = QPushButton("Delete")
        self.category_export_button = QPushButton("Export")
        self.category_new_button.clicked.connect(self._on_category_new_clicked)
        self.category_save_button.clicked.connect(self._on_category_save_clicked)
        self.category_delete_button.clicked.connect(self._on_category_delete_clicked)
        self.category_export_button.clicked.connect(self._on_category_export_clicked)
        buttons_row.addWidget(self.category_new_button)
        buttons_row.addWidget(self.category_save_button)
        buttons_row.addWidget(self.category_delete_button)
        buttons_row.addWidget(self.category_export_button)
        buttons_row.addStretch(1)
        new_layout.addLayout(buttons_row)

        defined_group = QGroupBox("Defined Categories")
        defined_layout = QVBoxLayout(defined_group)
        defined_layout.setContentsMargins(10, 10, 10, 10)
        defined_layout.setSpacing(8)
        self.categories_list = QListWidget()
        self.categories_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.categories_list.itemSelectionChanged.connect(self._on_category_selected)
        self.categories_list.setMinimumHeight(180)
        self.categories_list.setMinimumWidth(280)
        defined_layout.addWidget(self.categories_list, 1)

        categories_layout.addWidget(new_group, 0, Qt.AlignTop)
        categories_layout.addWidget(defined_group, 1)

        if self._categories_repo is None:
            self.category_name_edit.setEnabled(False)
            self.category_new_button.setEnabled(False)
            self.category_save_button.setEnabled(False)
            self.category_delete_button.setEnabled(False)
            self.category_export_button.setEnabled(False)
            self.categories_list.setEnabled(False)
            hint = QListWidgetItem("Categories repository unavailable.")
            self.categories_list.addItem(hint)
        else:
            self._refresh_categories_list()

        return categories_frame

    def _refresh_categories_list(self, select_id: int | None = None) -> None:
        if self._categories_repo is None:
            return

        rows = self._categories_repo.list_active()
        self.categories_list.clear()
        selected_row = None
        for row in rows:
            item = QListWidgetItem(str(row["name"]))
            item.setData(Qt.UserRole, int(row["category_id"]))
            self.categories_list.addItem(item)
            if select_id is not None and int(row["category_id"]) == int(select_id):
                selected_row = self.categories_list.count() - 1

        if selected_row is not None:
            self.categories_list.setCurrentRow(selected_row)
        else:
            self._selected_category_id = None
            self.category_name_edit.clear()

    def _on_category_selected(self) -> None:
        items = self.categories_list.selectedItems()
        if not items:
            self._selected_category_id = None
            return
        item = items[0]
        self._selected_category_id = int(item.data(Qt.UserRole))
        self.category_name_edit.setText(item.text())
        self.category_name_edit.setFocus()
        self.category_name_edit.selectAll()

    def _on_category_new_clicked(self) -> None:
        self._selected_category_id = None
        self.categories_list.clearSelection()
        self.category_name_edit.clear()
        self.category_name_edit.setFocus()

    def _on_category_save_clicked(self) -> None:
        if self._categories_repo is None:
            return

        name = self.category_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Category", "Category is required.")
            return

        try:
            existing_by_name = self._categories_repo.find_by_name(name)
            if self._selected_category_id is None:
                if existing_by_name:
                    category_id = self._categories_repo.upsert(
                        name,
                        is_income=bool(existing_by_name.get("is_income")),
                    )
                else:
                    category_id = self._categories_repo.upsert(name, is_income=False)
            else:
                if existing_by_name and int(existing_by_name["category_id"]) != int(self._selected_category_id):
                    QMessageBox.warning(
                        self,
                        "Category",
                        f"Category '{name}' already exists.",
                    )
                    return
                updated = self._categories_repo.update_name(self._selected_category_id, name)
                if updated == 0:
                    QMessageBox.warning(
                        self,
                        "Category",
                        "Selected category no longer exists.",
                    )
                    self._refresh_categories_list()
                    return
                category_id = self._selected_category_id
        except Exception as exc:
            QMessageBox.warning(self, "Category", f"Could not save category: {exc}")
            return

        self._categories_dirty = True
        self._refresh_categories_list(select_id=int(category_id))

    def _on_category_delete_clicked(self) -> None:
        if self._categories_repo is None:
            return
        if self._selected_category_id is None:
            QMessageBox.information(self, "Delete Category", "Select a category to delete.")
            return

        selected = self._categories_repo.get_by_id(self._selected_category_id)
        if not selected:
            QMessageBox.warning(self, "Delete Category", "Selected category no longer exists.")
            self._refresh_categories_list()
            return

        selected_name = str(selected.get("name") or "").strip()
        case_variants = self._categories_repo.find_case_variants(
            selected_name,
            exclude_category_id=self._selected_category_id,
        )
        if case_variants:
            if len(case_variants) > 1:
                QMessageBox.warning(
                    self,
                    "Delete Category",
                    "Multiple case-variant categories were found. "
                    "Please rename categories so only one target remains, then retry.",
                )
                return

            target = case_variants[0]
            target_id = int(target["category_id"])
            target_name = str(target["name"])
            answer = QMessageBox.question(
                self,
                "Merge Duplicate Category",
                f"'{selected_name}' has a case-variant duplicate '{target_name}'.\n\n"
                "Merge all references into the duplicate and delete the selected category?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

            try:
                merged = self._categories_repo.merge_category_into(
                    self._selected_category_id,
                    target_id,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Merge Category", f"Could not merge category: {exc}")
                return

            if merged == 0:
                QMessageBox.warning(
                    self,
                    "Merge Category",
                    "Selected category no longer exists.",
                )
                self._refresh_categories_list()
                return

            self._categories_dirty = True
            self._selected_category_id = target_id
            self._refresh_categories_list(select_id=target_id)
            QMessageBox.information(
                self,
                "Merge Category",
                f"Merged '{selected_name}' into '{target_name}'.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Category",
            "Delete selected category?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            deleted = self._categories_repo.delete(self._selected_category_id)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Category", f"Could not delete category: {exc}")
            return

        if deleted == 0:
            QMessageBox.warning(self, "Delete Category", "Selected category no longer exists.")
            self._refresh_categories_list()
            return

        self._categories_dirty = True
        self._on_category_new_clicked()
        self._refresh_categories_list()

    def _on_category_export_clicked(self) -> None:
        if self._categories_repo is None:
            return

        start_dir = self._categories_export_start_dir()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Categories CSV",
            str(Path(start_dir) / "budgetpal_categories.csv"),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        save_path = Path(file_path)
        rows = [
            row
            for row in self._categories_repo.list_active()
            if str(row.get("name") or "").strip().lower() != "uncategorized"
        ]
        try:
            with save_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["Category ID", "Category Name"])
                for row in rows:
                    writer.writerow(
                        [
                            int(row["category_id"]),
                            str(row["name"]),
                        ]
                    )
        except OSError as exc:
            QMessageBox.warning(self, "Export Categories", f"Could not export categories: {exc}")
            return

        self._persist_last_categories_export_dir(save_path.parent)
        self.categories_export_dir_edit.setText(str(save_path.parent))
        QMessageBox.information(
            self,
            "Export Categories",
            f"Exported {len(rows)} categories to:\n{save_path}",
        )

    def _categories_export_start_dir(self) -> str:
        raw_from_form = self.categories_export_dir_edit.text().strip()
        if raw_from_form:
            candidate = Path(raw_from_form).expanduser()
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return str(candidate)

        ui_settings = self._settings.setdefault("ui", {})
        raw = str(ui_settings.get("last_categories_export_dir", "")).strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return str(candidate)

        import_dir = str(ui_settings.get("last_import_dir", "")).strip()
        if import_dir:
            candidate = Path(import_dir).expanduser()
            if candidate.exists():
                return str(candidate)
        return str(Path.home())

    def _persist_last_categories_export_dir(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
        except OSError:
            resolved = directory

        ui_settings = self._settings.setdefault("ui", {})
        new_value = str(resolved)
        if str(ui_settings.get("last_categories_export_dir", "")).strip() == new_value:
            return
        ui_settings["last_categories_export_dir"] = new_value
        try:
            get_settings_manager().save(self._settings)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export Categories",
                f"Export succeeded, but could not persist picker location: {exc}",
            )
