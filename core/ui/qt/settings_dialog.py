from __future__ import annotations

import csv
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
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
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.persistence.repositories.accounts_repo import AccountsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository
from core.settings import get_settings_manager


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: dict,
        categories_repo: CategoriesRepository | None = None,
        accounts_repo: AccountsRepository | None = None,
        backup_now_callback: Callable[[Path, str], Path] | None = None,
        export_definitions_callback: Callable[[Path], list[Path]] | None = None,
        import_definitions_callback: Callable[[str, Path], dict[str, int | str]] | None = None,
        logger=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("BudgetPal Settings")
        self.resize(760, 560)
        self._settings = deepcopy(settings)
        self._categories_repo = categories_repo
        self._accounts_repo = accounts_repo
        self._selected_category_id: int | None = None
        self._categories_dirty = False
        self._selected_account_id: int | None = None
        self._accounts_dirty = False
        self._selected_transfer_rule_index: int | None = None
        self._transfer_rules: list[dict] = self._load_transfer_rules(self._settings)
        self._institution_names: list[str] = []
        self._institution_model = QStringListModel(self)
        self._transfer_account_rows: list[dict] = []
        self._transfer_account_by_number: dict[str, dict] = {}
        self._backup_now_callback = backup_now_callback
        self._export_definitions_callback = export_definitions_callback
        self._import_definitions_callback = import_definitions_callback
        self._logger = logger

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        info_label = QLabel(
            "Note: changing database path applies on next app launch. "
            "SubTracker path and logging settings apply after saving."
        )
        info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(info_label)
        tab_widget = QTabWidget()
        tab_widget.addTab(self._build_general_tab(), "General")
        tab_widget.addTab(self._build_categories_frame(), "Definitions")
        tab_widget.addTab(self._build_accounts_frame(), "Accounts")
        tab_widget.addTab(self._build_transfer_rules_frame(), "Transfer Rules")
        root.addWidget(tab_widget, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_general_tab(self) -> QWidget:
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
        return form_holder

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

    @staticmethod
    def _load_transfer_rules(settings: dict) -> list[dict]:
        raw_rules = settings.get("transfers", {}).get("rules", [])
        if not isinstance(raw_rules, list):
            return []
        normalized: list[dict] = []
        for idx, item in enumerate(raw_rules):
            if not isinstance(item, dict):
                continue
            match_category = str(item.get("match_category", "")).strip()
            if not match_category:
                continue
            match_description = str(item.get("match_description", "")).strip()
            from_account_type = str(item.get("from_account_type", "checking")).strip().lower() or "checking"
            to_account_type = str(item.get("to_account_type", "savings")).strip().lower() or "savings"
            if from_account_type not in {"cash", "checking", "credit", "savings"}:
                from_account_type = "checking"
            if to_account_type not in {"cash", "checking", "credit", "savings"}:
                to_account_type = "savings"
            from_account_number = str(item.get("from_account_number", "")).strip()
            to_account_number = str(item.get("to_account_number", "")).strip()
            from_account_alias = str(item.get("from_account_alias", "")).strip()
            to_account_alias = str(item.get("to_account_alias", "")).strip()
            normalized.append(
                {
                    "name": str(item.get("name", "")).strip() or f"Rule {idx + 1}",
                    "enabled": bool(item.get("enabled", True)),
                    "match_category": match_category,
                    "match_description": match_description,
                    "from_account_number": from_account_number,
                    "from_account_alias": from_account_alias,
                    "from_account_type": from_account_type,
                    "to_account_number": to_account_number,
                    "to_account_alias": to_account_alias,
                    "to_account_type": to_account_type,
                }
            )
        return normalized

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
            settings.setdefault("transfers", {})
            settings["transfers"]["rules"] = deepcopy(self._transfer_rules)
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

    @property
    def accounts_dirty(self) -> bool:
        return self._accounts_dirty

    def _build_categories_frame(self) -> QGroupBox:
        categories_frame = QGroupBox("Definitions")
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
        self.category_import_button = QPushButton("Import")
        self.definitions_export_button = QPushButton("Export Definitions")
        self.definitions_import_button = QPushButton("Import Definitions")
        self.category_new_button.clicked.connect(self._on_category_new_clicked)
        self.category_save_button.clicked.connect(self._on_category_save_clicked)
        self.category_delete_button.clicked.connect(self._on_category_delete_clicked)
        self.category_export_button.clicked.connect(self._on_category_export_clicked)
        self.category_import_button.clicked.connect(self._on_category_import_clicked)
        self.definitions_export_button.clicked.connect(self._on_export_definitions_clicked)
        self.definitions_import_button.clicked.connect(self._on_import_definitions_clicked)
        buttons_row.addWidget(self.category_new_button)
        buttons_row.addWidget(self.category_save_button)
        buttons_row.addWidget(self.category_delete_button)
        buttons_row.addWidget(self.category_export_button)
        buttons_row.addWidget(self.category_import_button)
        buttons_row.addStretch(1)
        new_layout.addLayout(buttons_row)

        global_defs_group = QGroupBox("Global Definitions")
        global_defs_layout = QVBoxLayout(global_defs_group)
        global_defs_layout.setContentsMargins(10, 10, 10, 10)
        global_defs_layout.setSpacing(8)
        global_defs_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        global_defs_row = QHBoxLayout()
        global_defs_row.setContentsMargins(0, 0, 0, 0)
        global_defs_row.setSpacing(8)
        global_defs_row.addWidget(self.definitions_export_button, 0, Qt.AlignLeft)
        self.definitions_export_label = QLabel("Exports global: bills, budget allocations, and income definitions.")
        self.definitions_export_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        global_defs_row.addWidget(self.definitions_export_label, 0, Qt.AlignLeft)
        global_defs_row.addStretch(1)
        global_defs_layout.addLayout(global_defs_row)

        import_row = QHBoxLayout()
        import_row.setContentsMargins(0, 0, 0, 0)
        import_row.setSpacing(8)
        import_row.addWidget(self.definitions_import_button, 0, Qt.AlignLeft)
        import_row.addWidget(QLabel("Type:"), 0, Qt.AlignLeft)
        self.definitions_import_type_group = QButtonGroup(self)
        self.definitions_import_bills_radio = QRadioButton("Bills")
        self.definitions_import_budget_radio = QRadioButton("Budget Allocations")
        self.definitions_import_income_radio = QRadioButton("Income")
        self.definitions_import_type_group.addButton(self.definitions_import_bills_radio)
        self.definitions_import_type_group.addButton(self.definitions_import_budget_radio)
        self.definitions_import_type_group.addButton(self.definitions_import_income_radio)
        self.definitions_import_bills_radio.setChecked(True)
        import_row.addWidget(self.definitions_import_bills_radio, 0, Qt.AlignLeft)
        import_row.addWidget(self.definitions_import_budget_radio, 0, Qt.AlignLeft)
        import_row.addWidget(self.definitions_import_income_radio, 0, Qt.AlignLeft)
        import_row.addStretch(1)
        global_defs_layout.addLayout(import_row)
        global_defs_layout.addStretch(1)

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

        left_column = QWidget()
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(8)
        left_column_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        left_column_layout.addWidget(new_group, 0, Qt.AlignTop)
        left_column_layout.addWidget(global_defs_group, 0, Qt.AlignTop)
        left_column_layout.addStretch(1)

        categories_layout.addWidget(left_column, 0, Qt.AlignTop)
        categories_layout.addWidget(defined_group, 1)

        if self._categories_repo is None:
            self.category_name_edit.setEnabled(False)
            self.category_new_button.setEnabled(False)
            self.category_save_button.setEnabled(False)
            self.category_delete_button.setEnabled(False)
            self.category_export_button.setEnabled(False)
            self.category_import_button.setEnabled(False)
            self.definitions_export_button.setEnabled(False)
            self.definitions_import_button.setEnabled(False)
            self.definitions_import_bills_radio.setEnabled(False)
            self.definitions_import_budget_radio.setEnabled(False)
            self.definitions_import_income_radio.setEnabled(False)
            self.definitions_export_label.setEnabled(False)
            self.categories_list.setEnabled(False)
            hint = QListWidgetItem("Categories repository unavailable.")
            self.categories_list.addItem(hint)
        else:
            self._refresh_categories_list()

        if self._import_definitions_callback is None:
            self.definitions_import_button.setEnabled(False)
            self.definitions_import_bills_radio.setEnabled(False)
            self.definitions_import_budget_radio.setEnabled(False)
            self.definitions_import_income_radio.setEnabled(False)

        return categories_frame

    def _build_accounts_frame(self) -> QGroupBox:
        accounts_frame = QGroupBox("Accounts")
        accounts_layout = QHBoxLayout(accounts_frame)
        accounts_layout.setContentsMargins(10, 10, 10, 10)
        accounts_layout.setSpacing(10)
        accounts_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        new_group = QGroupBox("Account Details")
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

        self.account_institution_edit = QLineEdit()
        self.account_institution_edit.setPlaceholderText("Institution Name")
        self.account_institution_edit.setMinimumWidth(260)
        institution_completer = QCompleter(self._institution_model, self)
        institution_completer.setCaseSensitivity(Qt.CaseInsensitive)
        institution_completer.setFilterMode(Qt.MatchContains)
        self.account_institution_edit.setCompleter(institution_completer)
        new_form.addRow("Institution", self.account_institution_edit)

        self.account_name_edit = QLineEdit()
        self.account_name_edit.setPlaceholderText("Account Alias")
        self.account_name_edit.setMinimumWidth(260)
        new_form.addRow("Account Alias", self.account_name_edit)

        self.account_type_combo = QComboBox()
        self.account_type_combo.addItems(["checking", "savings", "credit", "cash"])
        self.account_type_combo.setMinimumWidth(140)
        new_form.addRow("Account Class", self.account_type_combo)

        self.account_balance_edit = QLineEdit()
        self.account_balance_edit.setPlaceholderText("0.00")
        self.account_balance_edit.setFixedWidth(120)
        new_form.addRow("Balance", self.account_balance_edit)

        self.account_number_edit = QLineEdit()
        self.account_number_edit.setPlaceholderText("Account Number")
        self.account_number_edit.setMinimumWidth(220)
        new_form.addRow("Account Number", self.account_number_edit)

        self.account_cd_start_date_edit = QLineEdit()
        self.account_cd_start_date_edit.setPlaceholderText("YYYY-MM-DD (optional)")
        self.account_cd_start_date_edit.setMinimumWidth(180)
        new_form.addRow("CD Start Date", self.account_cd_start_date_edit)

        self.account_cd_interval_edit = QLineEdit()
        self.account_cd_interval_edit.setPlaceholderText("Months (optional)")
        self.account_cd_interval_edit.setFixedWidth(120)
        new_form.addRow("CD Interval", self.account_cd_interval_edit)

        self.account_cd_interest_rate_edit = QLineEdit()
        self.account_cd_interest_rate_edit.setPlaceholderText("Interest % (optional)")
        self.account_cd_interest_rate_edit.setFixedWidth(160)
        new_form.addRow("CD Interest Rate", self.account_cd_interest_rate_edit)

        self.account_notes_edit = QLineEdit()
        self.account_notes_edit.setPlaceholderText("Optional account notes")
        self.account_notes_edit.setMinimumWidth(260)
        new_form.addRow("Notes", self.account_notes_edit)
        new_layout.addLayout(new_form)

        account_buttons_row = QHBoxLayout()
        account_buttons_row.setContentsMargins(0, 0, 0, 0)
        account_buttons_row.setSpacing(8)
        self.account_save_button = QPushButton("Save")
        self.account_delete_button = QPushButton("Delete")
        self.account_save_button.clicked.connect(self._on_account_save_clicked)
        self.account_delete_button.clicked.connect(self._on_account_delete_clicked)
        account_buttons_row.addWidget(self.account_save_button)
        account_buttons_row.addWidget(self.account_delete_button)
        account_buttons_row.addStretch(1)
        new_layout.addLayout(account_buttons_row)

        defined_group = QGroupBox("Defined Accounts")
        defined_layout = QVBoxLayout(defined_group)
        defined_layout.setContentsMargins(10, 10, 10, 10)
        defined_layout.setSpacing(8)
        self.accounts_list = QListWidget()
        self.accounts_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.accounts_list.itemSelectionChanged.connect(self._on_account_selected)
        self.accounts_list.setMinimumHeight(180)
        self.accounts_list.setMinimumWidth(380)
        defined_layout.addWidget(self.accounts_list, 1)

        accounts_layout.addWidget(new_group, 0, Qt.AlignTop)
        accounts_layout.addWidget(defined_group, 1)

        if self._accounts_repo is None:
            self.account_institution_edit.setEnabled(False)
            self.account_name_edit.setEnabled(False)
            self.account_type_combo.setEnabled(False)
            self.account_balance_edit.setEnabled(False)
            self.account_number_edit.setEnabled(False)
            self.account_cd_start_date_edit.setEnabled(False)
            self.account_cd_interval_edit.setEnabled(False)
            self.account_cd_interest_rate_edit.setEnabled(False)
            self.account_notes_edit.setEnabled(False)
            self.account_save_button.setEnabled(False)
            self.account_delete_button.setEnabled(False)
            self.accounts_list.setEnabled(False)
            self.accounts_list.addItem(QListWidgetItem("Accounts repository unavailable."))
        else:
            self._refresh_institution_choices()
            self._refresh_accounts_list()
            self._clear_account_form()

        return accounts_frame

    def _build_transfer_rules_frame(self) -> QGroupBox:
        rules_frame = QGroupBox("Transfer Rules")
        rules_layout = QHBoxLayout(rules_frame)
        rules_layout.setContentsMargins(10, 10, 10, 10)
        rules_layout.setSpacing(10)
        rules_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        details_group = QGroupBox("Rule Details")
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        details_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        details_form = QFormLayout()
        details_form.setContentsMargins(0, 0, 0, 0)
        details_form.setHorizontalSpacing(10)
        details_form.setVerticalSpacing(8)
        details_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        details_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.transfer_rule_name_edit = QLineEdit()
        self.transfer_rule_name_edit.setPlaceholderText("Rule Name")
        self.transfer_rule_name_edit.setMinimumWidth(240)
        details_form.addRow("Rule Name", self.transfer_rule_name_edit)

        self.transfer_rule_enabled_checkbox = QCheckBox("Enabled")
        self.transfer_rule_enabled_checkbox.setChecked(True)
        details_form.addRow("", self.transfer_rule_enabled_checkbox)

        self.transfer_rule_match_category_edit = QLineEdit()
        self.transfer_rule_match_category_edit.setPlaceholderText("Category to match (exact)")
        self.transfer_rule_match_category_edit.setMinimumWidth(240)
        details_form.addRow("Match Category", self.transfer_rule_match_category_edit)

        self.transfer_rule_match_description_edit = QLineEdit()
        self.transfer_rule_match_description_edit.setPlaceholderText("Description contains (required)")
        self.transfer_rule_match_description_edit.setMinimumWidth(240)
        details_form.addRow("Match Description", self.transfer_rule_match_description_edit)

        self.transfer_rule_from_account_number_combo = QComboBox()
        self.transfer_rule_from_account_number_combo.setMinimumWidth(240)
        self.transfer_rule_from_account_number_combo.setEditable(False)
        details_form.addRow("From Account Number", self.transfer_rule_from_account_number_combo)

        self.transfer_rule_from_account_alias_edit = QLineEdit()
        self.transfer_rule_from_account_alias_edit.setReadOnly(True)
        self.transfer_rule_from_account_alias_edit.setPlaceholderText("Auto-filled from account number")
        self.transfer_rule_from_account_alias_edit.setMinimumWidth(240)
        details_form.addRow("From Account Alias", self.transfer_rule_from_account_alias_edit)

        self.transfer_rule_from_type_edit = QLineEdit()
        self.transfer_rule_from_type_edit.setReadOnly(True)
        self.transfer_rule_from_type_edit.setPlaceholderText("Auto-filled from account number")
        self.transfer_rule_from_type_edit.setFixedWidth(160)
        details_form.addRow("From Account Class", self.transfer_rule_from_type_edit)

        self.transfer_rule_to_account_number_combo = QComboBox()
        self.transfer_rule_to_account_number_combo.setMinimumWidth(240)
        self.transfer_rule_to_account_number_combo.setEditable(False)
        details_form.addRow("To Account Number", self.transfer_rule_to_account_number_combo)

        self.transfer_rule_to_account_alias_edit = QLineEdit()
        self.transfer_rule_to_account_alias_edit.setReadOnly(True)
        self.transfer_rule_to_account_alias_edit.setPlaceholderText("Auto-filled from account number")
        self.transfer_rule_to_account_alias_edit.setMinimumWidth(240)
        details_form.addRow("To Account Alias", self.transfer_rule_to_account_alias_edit)

        self.transfer_rule_to_type_edit = QLineEdit()
        self.transfer_rule_to_type_edit.setReadOnly(True)
        self.transfer_rule_to_type_edit.setPlaceholderText("Auto-filled from account number")
        self.transfer_rule_to_type_edit.setFixedWidth(160)
        details_form.addRow("To Account Class", self.transfer_rule_to_type_edit)
        details_layout.addLayout(details_form)

        self.transfer_rule_preview_label = QLabel("Rule Preview")
        self.transfer_rule_preview_label.setStyleSheet("font-weight: 600;")
        details_layout.addWidget(self.transfer_rule_preview_label, alignment=Qt.AlignLeft)

        self.transfer_rule_preview_body = QLabel("Preview appears here as you edit the rule.")
        self.transfer_rule_preview_body.setWordWrap(True)
        self.transfer_rule_preview_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.transfer_rule_preview_body.setMinimumWidth(320)
        details_layout.addWidget(self.transfer_rule_preview_body, alignment=Qt.AlignLeft)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        buttons_row.setSpacing(8)
        self.transfer_rule_new_button = QPushButton("New")
        self.transfer_rule_save_button = QPushButton("Save")
        self.transfer_rule_delete_button = QPushButton("Delete")
        self.transfer_rule_new_button.clicked.connect(self._on_transfer_rule_new_clicked)
        self.transfer_rule_save_button.clicked.connect(self._on_transfer_rule_save_clicked)
        self.transfer_rule_delete_button.clicked.connect(self._on_transfer_rule_delete_clicked)
        buttons_row.addWidget(self.transfer_rule_new_button)
        buttons_row.addWidget(self.transfer_rule_save_button)
        buttons_row.addWidget(self.transfer_rule_delete_button)
        buttons_row.addStretch(1)
        details_layout.addLayout(buttons_row)

        list_group = QGroupBox("Defined Rules")
        list_layout = QVBoxLayout(list_group)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)
        self.transfer_rules_list = QListWidget()
        self.transfer_rules_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.transfer_rules_list.itemSelectionChanged.connect(self._on_transfer_rule_selected)
        self.transfer_rules_list.setMinimumHeight(180)
        self.transfer_rules_list.setMinimumWidth(360)
        list_layout.addWidget(self.transfer_rules_list, 1)

        rules_layout.addWidget(details_group, 0, Qt.AlignTop)
        rules_layout.addWidget(list_group, 1)

        self.transfer_rule_name_edit.textChanged.connect(self._update_transfer_rule_preview_from_form)
        self.transfer_rule_enabled_checkbox.toggled.connect(self._update_transfer_rule_preview_from_form)
        self.transfer_rule_match_category_edit.textChanged.connect(self._update_transfer_rule_preview_from_form)
        self.transfer_rule_match_description_edit.textChanged.connect(self._update_transfer_rule_preview_from_form)
        self.transfer_rule_from_account_number_combo.currentIndexChanged.connect(
            self._on_transfer_rule_from_account_number_changed
        )
        self.transfer_rule_to_account_number_combo.currentIndexChanged.connect(
            self._on_transfer_rule_to_account_number_changed
        )

        self._refresh_transfer_account_choices()
        self._refresh_transfer_rules_list()
        self._update_transfer_rule_preview()
        return rules_frame

    @staticmethod
    def _transfer_rule_list_label(rule: dict) -> str:
        enabled = "On" if bool(rule.get("enabled", True)) else "Off"
        name = str(rule.get("name", "")).strip()
        match_category = str(rule.get("match_category", "")).strip()
        match_description = str(rule.get("match_description", "")).strip()
        from_account_number = str(rule.get("from_account_number", "")).strip()
        to_account_number = str(rule.get("to_account_number", "")).strip()
        from_alias = str(rule.get("from_account_alias", "")).strip()
        to_alias = str(rule.get("to_account_alias", "")).strip()
        from_text = from_account_number or "<from account>"
        to_text = to_account_number or "<to account>"
        if from_alias:
            from_text = f"{from_text} ({from_alias})"
        if to_alias:
            to_text = f"{to_text} ({to_alias})"
        return (
            f"[{enabled}] {name} | {match_category} + contains '{match_description}'"
            f" -> {from_text} to {to_text}"
        )

    @staticmethod
    def _normalize_account_number(value: str) -> str:
        return str(value or "").strip().casefold()

    def _build_transfer_account_maps(self) -> None:
        self._transfer_account_rows = []
        self._transfer_account_by_number = {}
        if self._accounts_repo is None:
            return
        rows = self._accounts_repo.list_active()
        self._transfer_account_rows = [dict(row) for row in rows]
        for row in self._transfer_account_rows:
            account_number = str(row.get("account_number") or "").strip()
            if not account_number:
                continue
            key = self._normalize_account_number(account_number)
            if key not in self._transfer_account_by_number:
                self._transfer_account_by_number[key] = row

    def _refresh_transfer_account_choices(
        self,
        *,
        select_from_number: str | None = None,
        select_to_number: str | None = None,
    ) -> None:
        if not hasattr(self, "transfer_rule_from_account_number_combo"):
            return
        self._build_transfer_account_maps()

        from_current = (
            str(select_from_number).strip()
            if select_from_number is not None
            else str(self.transfer_rule_from_account_number_combo.currentData() or "").strip()
        )
        to_current = (
            str(select_to_number).strip()
            if select_to_number is not None
            else str(self.transfer_rule_to_account_number_combo.currentData() or "").strip()
        )

        self.transfer_rule_from_account_number_combo.blockSignals(True)
        self.transfer_rule_to_account_number_combo.blockSignals(True)
        try:
            self.transfer_rule_from_account_number_combo.clear()
            self.transfer_rule_to_account_number_combo.clear()
            self.transfer_rule_from_account_number_combo.addItem("", "")
            self.transfer_rule_to_account_number_combo.addItem("", "")
            for row in self._transfer_account_rows:
                account_number = str(row.get("account_number") or "").strip()
                if not account_number:
                    continue
                institution = str(row.get("institution_name") or "").strip()
                alias = str(row.get("name") or "").strip()
                account_type = str(row.get("account_type") or "").strip()
                label = f"{account_number} | {alias} ({account_type})"
                if institution:
                    label = f"{label} - {institution}"
                self.transfer_rule_from_account_number_combo.addItem(label, account_number)
                self.transfer_rule_to_account_number_combo.addItem(label, account_number)

            from_idx = self.transfer_rule_from_account_number_combo.findData(from_current)
            to_idx = self.transfer_rule_to_account_number_combo.findData(to_current)
            self.transfer_rule_from_account_number_combo.setCurrentIndex(from_idx if from_idx >= 0 else 0)
            self.transfer_rule_to_account_number_combo.setCurrentIndex(to_idx if to_idx >= 0 else 0)
        finally:
            self.transfer_rule_from_account_number_combo.blockSignals(False)
            self.transfer_rule_to_account_number_combo.blockSignals(False)

        self._sync_transfer_account_detail_fields()

    def _transfer_account_row_by_number(self, account_number: str) -> dict | None:
        if not account_number:
            return None
        return self._transfer_account_by_number.get(self._normalize_account_number(account_number))

    def _sync_transfer_account_detail_fields(self) -> None:
        from_number = str(self.transfer_rule_from_account_number_combo.currentData() or "").strip()
        to_number = str(self.transfer_rule_to_account_number_combo.currentData() or "").strip()

        from_row = self._transfer_account_row_by_number(from_number)
        to_row = self._transfer_account_row_by_number(to_number)

        self.transfer_rule_from_account_alias_edit.setText(str((from_row or {}).get("name") or ""))
        self.transfer_rule_to_account_alias_edit.setText(str((to_row or {}).get("name") or ""))
        self.transfer_rule_from_type_edit.setText(str((from_row or {}).get("account_type") or ""))
        self.transfer_rule_to_type_edit.setText(str((to_row or {}).get("account_type") or ""))

    def _on_transfer_rule_from_account_number_changed(self) -> None:
        self._sync_transfer_account_detail_fields()
        self._update_transfer_rule_preview_from_form()

    def _on_transfer_rule_to_account_number_changed(self) -> None:
        self._sync_transfer_account_detail_fields()
        self._update_transfer_rule_preview_from_form()

    def _refresh_transfer_rules_list(self, select_index: int | None = None) -> None:
        self.transfer_rules_list.clear()
        selected_row = None
        for idx, rule in enumerate(self._transfer_rules):
            item = QListWidgetItem(self._transfer_rule_list_label(rule))
            item.setData(Qt.UserRole, idx)
            self.transfer_rules_list.addItem(item)
            if select_index is not None and idx == select_index:
                selected_row = idx

        if selected_row is not None:
            self.transfer_rules_list.setCurrentRow(selected_row)
        else:
            self._clear_transfer_rule_form()

    def _clear_transfer_rule_form(self) -> None:
        self._selected_transfer_rule_index = None
        self.transfer_rules_list.clearSelection()
        self.transfer_rule_name_edit.clear()
        self.transfer_rule_enabled_checkbox.setChecked(True)
        self.transfer_rule_match_category_edit.clear()
        self.transfer_rule_match_description_edit.clear()
        self._refresh_transfer_account_choices(select_from_number="", select_to_number="")
        self._update_transfer_rule_preview()

    def _on_transfer_rule_new_clicked(self) -> None:
        self._clear_transfer_rule_form()
        self.transfer_rule_name_edit.setFocus()

    def _on_transfer_rule_selected(self) -> None:
        items = self.transfer_rules_list.selectedItems()
        if not items:
            self._selected_transfer_rule_index = None
            return
        idx = int(items[0].data(Qt.UserRole))
        if idx < 0 or idx >= len(self._transfer_rules):
            self._selected_transfer_rule_index = None
            return
        self._selected_transfer_rule_index = idx
        rule = self._transfer_rules[idx]
        self.transfer_rule_name_edit.setText(str(rule.get("name", "")))
        self.transfer_rule_enabled_checkbox.setChecked(bool(rule.get("enabled", True)))
        self.transfer_rule_match_category_edit.setText(str(rule.get("match_category", "")))
        self.transfer_rule_match_description_edit.setText(str(rule.get("match_description", "")))
        self._refresh_transfer_account_choices(
            select_from_number=str(rule.get("from_account_number", "")),
            select_to_number=str(rule.get("to_account_number", "")),
        )
        self._update_transfer_rule_preview(rule)

    def _on_transfer_rule_save_clicked(self) -> None:
        name = self.transfer_rule_name_edit.text().strip()
        match_category = self.transfer_rule_match_category_edit.text().strip()
        match_description = self.transfer_rule_match_description_edit.text().strip()
        if not match_category:
            QMessageBox.warning(self, "Transfer Rule", "Match Category is required.")
            return
        if not match_description:
            QMessageBox.warning(self, "Transfer Rule", "Match Description is required.")
            return
        from_account_number = str(self.transfer_rule_from_account_number_combo.currentData() or "").strip()
        to_account_number = str(self.transfer_rule_to_account_number_combo.currentData() or "").strip()
        if not from_account_number:
            QMessageBox.warning(self, "Transfer Rule", "From Account Number is required.")
            return
        if not to_account_number:
            QMessageBox.warning(self, "Transfer Rule", "To Account Number is required.")
            return
        from_row = self._transfer_account_row_by_number(from_account_number)
        to_row = self._transfer_account_row_by_number(to_account_number)
        if from_row is None:
            QMessageBox.warning(self, "Transfer Rule", "From Account Number could not be resolved.")
            return
        if to_row is None:
            QMessageBox.warning(self, "Transfer Rule", "To Account Number could not be resolved.")
            return
        if not name:
            name = f"Rule {len(self._transfer_rules) + 1}"

        from_type = str(from_row.get("account_type") or "").strip().lower() or "checking"
        to_type = str(to_row.get("account_type") or "").strip().lower() or "savings"

        rule = {
            "name": name,
            "enabled": self.transfer_rule_enabled_checkbox.isChecked(),
            "match_category": match_category,
            "match_description": match_description,
            "from_account_number": from_account_number,
            "from_account_alias": str(from_row.get("name") or "").strip(),
            "from_account_type": from_type,
            "to_account_number": to_account_number,
            "to_account_alias": str(to_row.get("name") or "").strip(),
            "to_account_type": to_type,
        }

        if self._selected_transfer_rule_index is None:
            self._transfer_rules.append(rule)
            selected_index = len(self._transfer_rules) - 1
        else:
            self._transfer_rules[self._selected_transfer_rule_index] = rule
            selected_index = self._selected_transfer_rule_index

        self._refresh_transfer_rules_list(select_index=selected_index)
        self._update_transfer_rule_preview(rule)

    def _on_transfer_rule_delete_clicked(self) -> None:
        if self._selected_transfer_rule_index is None:
            QMessageBox.information(self, "Delete Rule", "Select a transfer rule to delete.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Transfer Rule",
            "Delete selected transfer rule?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        del self._transfer_rules[self._selected_transfer_rule_index]
        self._refresh_transfer_rules_list()
        self._update_transfer_rule_preview()

    @staticmethod
    def _normalized_account_type(value: str, default: str) -> str:
        text = str(value or "").strip().lower()
        if text in {"cash", "checking", "credit", "savings"}:
            return text
        return default

    def _draft_transfer_rule_from_form(self) -> dict | None:
        match_category = self.transfer_rule_match_category_edit.text().strip()
        match_description = self.transfer_rule_match_description_edit.text().strip()
        from_account_number = str(self.transfer_rule_from_account_number_combo.currentData() or "").strip()
        to_account_number = str(self.transfer_rule_to_account_number_combo.currentData() or "").strip()
        from_row = self._transfer_account_row_by_number(from_account_number)
        to_row = self._transfer_account_row_by_number(to_account_number)
        from_type = self._normalized_account_type(str((from_row or {}).get("account_type") or ""), "checking")
        to_type = self._normalized_account_type(str((to_row or {}).get("account_type") or ""), "savings")
        name = self.transfer_rule_name_edit.text().strip()
        if not any(
            [
                name,
                match_category,
                match_description,
                from_account_number,
                to_account_number,
            ]
        ):
            return None
        return {
            "name": name or "Draft Rule",
            "enabled": self.transfer_rule_enabled_checkbox.isChecked(),
            "match_category": match_category,
            "match_description": match_description,
            "from_account_number": from_account_number,
            "from_account_alias": str((from_row or {}).get("name") or "").strip(),
            "from_account_type": from_type,
            "to_account_number": to_account_number,
            "to_account_alias": str((to_row or {}).get("name") or "").strip(),
            "to_account_type": to_type,
        }

    def _resolve_account_for_preview(
        self,
        *,
        account_number: str,
        account_type: str,
        accounts: list[dict],
    ) -> tuple[dict | None, str]:
        normalized_number = self._normalize_account_number(account_number)
        normalized_type = self._normalized_account_type(account_type, "checking")

        if not normalized_number:
            return None, "account number is blank"
        for row in accounts:
            row_number = self._normalize_account_number(str(row.get("account_number") or ""))
            if row_number != normalized_number:
                continue
            row_type = str(row.get("account_type") or "").strip().lower()
            label = (
                f"{row.get('institution_name', '')} | {row.get('name', '')}"
                f" ({row.get('account_type', '')})"
            ).strip()
            if row_type and row_type != normalized_type:
                return row, f"{account_number} -> {label} [type mismatch]"
            return row, f"{account_number} -> {label}"
        return None, f"account number '{account_number}' not found"

    def _update_transfer_rule_preview(self, rule: dict | None = None) -> None:
        if self._accounts_repo is None:
            self.transfer_rule_preview_body.setText("Preview unavailable (accounts repository not loaded).")
            return

        active_rule = rule or self._draft_transfer_rule_from_form()
        if active_rule is None:
            self.transfer_rule_preview_body.setText("Preview appears here as you edit the rule.")
            return

        accounts = self._accounts_repo.list_active()
        from_row, from_resolution = self._resolve_account_for_preview(
            account_number=str(active_rule.get("from_account_number", "")),
            account_type=str(active_rule.get("from_account_type", "checking")),
            accounts=accounts,
        )
        to_row, to_resolution = self._resolve_account_for_preview(
            account_number=str(active_rule.get("to_account_number", "")),
            account_type=str(active_rule.get("to_account_type", "savings")),
            accounts=accounts,
        )

        name = str(active_rule.get("name", "")).strip() or "Draft Rule"
        category = str(active_rule.get("match_category", "")).strip() or "<blank>"
        description_contains = str(active_rule.get("match_description", "")).strip() or "<blank>"
        enabled = bool(active_rule.get("enabled", True))

        if not enabled:
            status = "Status: Disabled (rule will not run)"
        elif not description_contains or description_contains == "<blank>":
            status = "Status: Unresolved (Match Description is required)"
        elif from_row is None or to_row is None:
            status = "Status: Unresolved (import will fall back to normal expense row)"
        elif int(from_row.get("account_id") or 0) == int(to_row.get("account_id") or 0):
            status = "Status: Invalid (from/to resolve to the same account)"
        else:
            status = "Status: Ready (will convert matching expense rows into transfer postings)"

        preview_lines = [
            f"Rule: {name}",
            f"Match Category: {category}",
            f"Match Description Contains: {description_contains}",
            f"From Resolution: {from_resolution}",
            f"To Resolution: {to_resolution}",
            status,
        ]
        self.transfer_rule_preview_body.setText("\n".join(preview_lines))

    def _update_transfer_rule_preview_from_form(self) -> None:
        self._update_transfer_rule_preview()

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

    def _refresh_institution_choices(self, select_name: str | None = None) -> None:
        if self._accounts_repo is None:
            return
        selected_text = (
            str(select_name).strip()
            if select_name is not None
            else str(self.account_institution_edit.text()).strip()
        )
        rows = self._accounts_repo.list_institutions_active()
        self._institution_names = [str(row["name"]).strip() for row in rows if str(row["name"]).strip()]
        self._institution_model.setStringList(self._institution_names)

        if selected_text:
            self.account_institution_edit.setText(selected_text)
        elif self._institution_names:
            self.account_institution_edit.setText(self._institution_names[0])
        else:
            self.account_institution_edit.clear()

    @staticmethod
    def _format_cents(cents: int) -> str:
        return f"{int(cents) / 100:.2f}"

    @staticmethod
    def _parse_cents(value: str) -> int:
        text = str(value or "").strip().replace("$", "").replace(",", "")
        if not text:
            return 0
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Balance must be numeric (example: 1000.00).") from exc
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _parse_optional_positive_int(value: str, field_name: str) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        if not text.isdigit():
            raise ValueError(f"{field_name} must be a positive integer.")
        parsed = int(text)
        if parsed < 1:
            raise ValueError(f"{field_name} must be at least 1.")
        return parsed

    @staticmethod
    def _parse_optional_interest_rate_bps(value: str) -> int | None:
        text = str(value or "").strip().replace("%", "")
        if not text:
            return None
        try:
            pct = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("CD interest rate must be numeric (example: 4.25).") from exc
        if pct < 0:
            raise ValueError("CD interest rate must be >= 0.")
        return int((pct * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _format_interest_rate_percent(value_bps: object) -> str:
        if value_bps is None:
            return ""
        try:
            bps = int(value_bps)
        except (TypeError, ValueError):
            return ""
        return f"{bps / 100:.2f}"

    def _account_item_label(self, row: dict) -> str:
        institution_name = str(row.get("institution_name") or "").strip()
        account_name = str(row.get("name") or "").strip()
        account_type = str(row.get("account_type") or "").strip()
        balance_cents = int(row.get("balance_cents") or row.get("opening_balance_cents") or 0)
        return f"{institution_name} | {account_name} | {account_type} | ${balance_cents / 100:.2f}"

    def _refresh_accounts_list(self, select_id: int | None = None) -> None:
        if self._accounts_repo is None:
            return

        rows = self._accounts_repo.list_active()
        self.accounts_list.clear()
        selected_row = None
        for row in rows:
            item = QListWidgetItem(self._account_item_label(row))
            item.setData(Qt.UserRole, int(row["account_id"]))
            item.setData(Qt.UserRole + 1, dict(row))
            self.accounts_list.addItem(item)
            if select_id is not None and int(row["account_id"]) == int(select_id):
                selected_row = self.accounts_list.count() - 1

        if selected_row is not None:
            self.accounts_list.setCurrentRow(selected_row)
        else:
            self._clear_account_form()

    def _on_account_selected(self) -> None:
        items = self.accounts_list.selectedItems()
        if not items:
            self._clear_account_form()
            return
        item = items[0]
        self._selected_account_id = int(item.data(Qt.UserRole))
        row = dict(item.data(Qt.UserRole + 1) or {})
        self._refresh_institution_choices(select_name=str(row.get("institution_name") or ""))
        self.account_name_edit.setText(str(row.get("name") or ""))
        account_type = str(row.get("account_type") or "").strip().lower()
        type_idx = self.account_type_combo.findText(account_type)
        if type_idx >= 0:
            self.account_type_combo.setCurrentIndex(type_idx)
        self.account_balance_edit.setText(
            self._format_cents(int(row.get("balance_cents") or row.get("opening_balance_cents") or 0))
        )
        self.account_number_edit.setText(str(row.get("account_number") or ""))
        self.account_cd_start_date_edit.setText(str(row.get("cd_start_date") or ""))
        self.account_cd_interval_edit.setText(
            "" if row.get("cd_interval_count") is None else str(row.get("cd_interval_count"))
        )
        self.account_cd_interest_rate_edit.setText(
            self._format_interest_rate_percent(row.get("cd_interest_rate_bps"))
        )
        self.account_notes_edit.setText(str(row.get("notes") or ""))

    def _clear_account_form(self, *, focus_name: bool = False) -> None:
        self._selected_account_id = None
        self.accounts_list.clearSelection()
        self.account_institution_edit.clear()
        self.account_name_edit.clear()
        self.account_balance_edit.clear()
        self.account_number_edit.clear()
        self.account_cd_start_date_edit.clear()
        self.account_cd_interval_edit.clear()
        self.account_cd_interest_rate_edit.clear()
        self.account_notes_edit.clear()
        self.account_type_combo.setCurrentText("checking")
        if focus_name:
            self.account_name_edit.setFocus()

    def _on_account_save_clicked(self) -> None:
        if self._accounts_repo is None:
            return

        institution_name = self.account_institution_edit.text().strip()
        account_name = self.account_name_edit.text().strip()
        account_type = self.account_type_combo.currentText().strip().lower()
        balance_cents = 0
        account_number = self.account_number_edit.text().strip() or None
        cd_start_date = self.account_cd_start_date_edit.text().strip() or None
        cd_interval_count: int | None = None
        cd_interest_rate_bps: int | None = None
        notes = self.account_notes_edit.text().strip() or None

        if not institution_name:
            QMessageBox.warning(self, "Account", "Institution is required.")
            return
        if not account_name:
            QMessageBox.warning(self, "Account", "Account name is required.")
            return
        if not account_type:
            QMessageBox.warning(self, "Account", "Account type is required.")
            return
        try:
            balance_cents = self._parse_cents(self.account_balance_edit.text())
            cd_interval_count = self._parse_optional_positive_int(
                self.account_cd_interval_edit.text(),
                "CD interval",
            )
            cd_interest_rate_bps = self._parse_optional_interest_rate_bps(
                self.account_cd_interest_rate_edit.text()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Account", str(exc))
            return

        try:
            institution_id = self._accounts_repo.upsert_institution(institution_name)
            if self._selected_account_id is None:
                self._accounts_repo.upsert(
                    account_name,
                    account_type,
                    balance_cents,
                    institution_id=institution_id,
                    account_number=account_number,
                    balance_cents=balance_cents,
                    notes=notes,
                    cd_start_date=cd_start_date,
                    cd_interval_count=cd_interval_count,
                    cd_interval_unit="months" if cd_interval_count is not None else None,
                    cd_interest_rate_bps=cd_interest_rate_bps,
                )
            else:
                updated = self._accounts_repo.update(
                    account_id=self._selected_account_id,
                    institution_id=institution_id,
                    name=account_name,
                    account_type=account_type,
                    opening_balance_cents=balance_cents,
                    account_number=account_number,
                    balance_cents=balance_cents,
                    notes=notes,
                    cd_start_date=cd_start_date,
                    cd_interval_count=cd_interval_count,
                    cd_interval_unit="months" if cd_interval_count is not None else None,
                    cd_interest_rate_bps=cd_interest_rate_bps,
                )
                if updated == 0:
                    QMessageBox.warning(self, "Account", "Selected account no longer exists.")
                    self._refresh_accounts_list()
                    return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Account", f"Could not save account: {exc}")
            return

        self._accounts_dirty = True
        self._refresh_institution_choices(select_name=institution_name)
        self._refresh_accounts_list()
        self._refresh_transfer_account_choices()
        self._clear_account_form(focus_name=True)
        self._update_transfer_rule_preview()

    def _on_account_delete_clicked(self) -> None:
        if self._accounts_repo is None:
            return
        if self._selected_account_id is None:
            QMessageBox.information(self, "Delete Account", "Select an account to delete.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Account",
            "Delete selected account?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        ref_counts = self._accounts_repo.get_reference_counts(self._selected_account_id)
        total_refs = sum(int(value) for value in ref_counts.values())
        if total_refs > 0:
            refs_msg = (
                f"Transactions: {ref_counts['transactions']}\n"
                f"Income Definitions: {ref_counts['income_definitions']}\n"
                f"Checking Month Settings: {ref_counts['checking_month_settings']}"
            )
            confirm = QMessageBox.question(
                self,
                "Account In Use",
                "This account is referenced by existing records and cannot be hard-deleted.\n\n"
                f"{refs_msg}\n\n"
                "Deactivate this account instead?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                return
        try:
            result = self._accounts_repo.delete_or_deactivate(self._selected_account_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Delete Account", f"Could not delete account: {exc}")
            return

        if result == "missing":
            QMessageBox.warning(self, "Delete Account", "Selected account no longer exists.")
            self._refresh_accounts_list()
            return
        if result == "deactivated":
            QMessageBox.information(
                self,
                "Account Deactivated",
                "This account is in use by existing records, so it was deactivated instead of deleted.",
            )

        self._accounts_dirty = True
        self._refresh_accounts_list()
        self._refresh_transfer_account_choices()
        self._clear_account_form()
        self._update_transfer_rule_preview()

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

    @staticmethod
    def _parse_category_names_from_csv(csv_path: Path) -> tuple[list[str], int, int]:
        names: list[str] = []
        seen: set[str] = set()
        skipped_blank = 0
        skipped_duplicates = 0
        with csv_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            dict_reader = csv.DictReader(csv_file)
            field_lookup = {
                str(field or "").strip().lower(): str(field or "")
                for field in (dict_reader.fieldnames or [])
                if str(field or "").strip()
            }
            preferred_keys = ("category name", "category", "name")
            source_key = next((field_lookup[key] for key in preferred_keys if key in field_lookup), None)
            for row in dict_reader:
                raw = ""
                if source_key is not None:
                    raw = str(row.get(source_key, "") or "").strip()
                if not raw:
                    for value in row.values():
                        candidate = str(value or "").strip()
                        if candidate:
                            raw = candidate
                            break
                if not raw:
                    skipped_blank += 1
                    continue
                dedupe_key = raw.casefold()
                if dedupe_key in seen:
                    skipped_duplicates += 1
                    continue
                seen.add(dedupe_key)
                names.append(raw)
        return names, skipped_blank, skipped_duplicates

    def _on_category_import_clicked(self) -> None:
        if self._categories_repo is None:
            return

        start_dir = self._categories_export_start_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Categories CSV",
            str(start_dir),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        csv_path = Path(file_path)
        try:
            names, skipped_blank, skipped_duplicates = self._parse_category_names_from_csv(csv_path)
        except (OSError, csv.Error, UnicodeError) as exc:
            QMessageBox.warning(self, "Import Categories", f"Could not read categories CSV: {exc}")
            return

        if not names:
            QMessageBox.information(
                self,
                "Import Categories",
                "No category names were found in the selected file.",
            )
            self._persist_last_categories_export_dir(csv_path.parent)
            self.categories_export_dir_edit.setText(str(csv_path.parent))
            return

        matched_count = 0
        created_count = 0
        try:
            for name in names:
                existing = self._categories_repo.find_by_name(name)
                self._categories_repo.upsert(name, is_income=False)
                if existing is None:
                    created_count += 1
                else:
                    matched_count += 1
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import Categories", f"Could not import categories: {exc}")
            return

        self._categories_dirty = True
        self._on_category_new_clicked()
        self._refresh_categories_list()
        self._persist_last_categories_export_dir(csv_path.parent)
        self.categories_export_dir_edit.setText(str(csv_path.parent))
        QMessageBox.information(
            self,
            "Import Categories",
            "Category import complete.\n\n"
            f"Matched existing: {matched_count}\n"
            f"Created new: {created_count}\n"
            f"Skipped blanks: {skipped_blank}\n"
            f"Skipped duplicates: {skipped_duplicates}\n\n"
            f"File:\n{csv_path}",
        )
        if self._logger is not None:
            self._logger.info(
                "Imported categories from %s (matched=%s created=%s skipped_blank=%s skipped_duplicates=%s)",
                csv_path,
                matched_count,
                created_count,
                skipped_blank,
                skipped_duplicates,
            )

    def _on_export_definitions_clicked(self) -> None:
        if self._export_definitions_callback is None:
            QMessageBox.warning(
                self,
                "Export Definitions",
                "Definitions export is unavailable in this build context.",
            )
            return

        start_dir = self._definitions_export_start_dir()
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Definitions Export Directory",
            start_dir,
        )
        if not selected_dir:
            return

        export_dir = Path(selected_dir)
        try:
            files = self._export_definitions_callback(export_dir)
        except Exception as exc:  # noqa: BLE001
            if self._logger is not None:
                self._logger.error("Export definitions failed: %s", exc)
            QMessageBox.warning(self, "Export Definitions", f"Could not export definitions: {exc}")
            return

        self._persist_last_definitions_export_dir(export_dir)
        file_names = "\n".join(f"- {path.name}" for path in files)
        QMessageBox.information(
            self,
            "Export Definitions",
            "Exported global definitions:\n\n"
            f"{file_names}\n\n"
            f"Location:\n{export_dir}",
        )
        if self._logger is not None:
            self._logger.info(
                "Exported global definitions snapshot to %s (%s files)",
                export_dir,
                len(files),
            )

    def _on_import_definitions_clicked(self) -> None:
        if self._import_definitions_callback is None:
            QMessageBox.warning(
                self,
                "Import Definitions",
                "Definitions import is unavailable in this build context.",
            )
            return

        definition_type = self._selected_definition_import_type()
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {definition_type.replace('_', ' ').title()} Definitions CSV",
            self._definitions_import_start_path(),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not selected_file:
            return

        csv_path = Path(selected_file)
        try:
            result = self._import_definitions_callback(definition_type, csv_path)
        except Exception as exc:  # noqa: BLE001
            if self._logger is not None:
                self._logger.error(
                    "Import definitions failed for %s from %s: %s",
                    definition_type,
                    csv_path,
                    exc,
                )
            QMessageBox.warning(self, "Import Definitions", f"Could not import definitions: {exc}")
            return

        self._persist_last_definitions_import_path(csv_path)
        QMessageBox.information(
            self,
            "Import Definitions",
            "Definitions import complete.\n\n"
            f"Type: {result.get('definition_type', definition_type)}\n"
            f"Inserted: {result.get('inserted', 0)}\n"
            f"Updated: {result.get('updated', 0)}\n"
            f"Skipped blank rows: {result.get('skipped_blank', 0)}\n"
            f"Rows in file: {result.get('rows_total', 0)}\n\n"
            f"File:\n{csv_path}",
        )
        if self._logger is not None:
            self._logger.info(
                "Imported %s definitions from %s (inserted=%s updated=%s skipped_blank=%s)",
                result.get("definition_type", definition_type),
                csv_path,
                result.get("inserted", 0),
                result.get("updated", 0),
                result.get("skipped_blank", 0),
            )

    def _selected_definition_import_type(self) -> str:
        if self.definitions_import_budget_radio.isChecked():
            return "budget_allocations"
        if self.definitions_import_income_radio.isChecked():
            return "income"
        return "bills"

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

    def _definitions_export_start_dir(self) -> str:
        ui_settings = self._settings.setdefault("ui", {})
        raw = str(ui_settings.get("last_definitions_export_dir", "")).strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                return str(candidate)

        fallback = str(ui_settings.get("last_categories_export_dir", "")).strip()
        if fallback:
            candidate = Path(fallback).expanduser()
            if candidate.exists():
                return str(candidate)
        return str(Path.home())

    def _persist_last_definitions_export_dir(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
        except OSError:
            resolved = directory

        ui_settings = self._settings.setdefault("ui", {})
        new_value = str(resolved)
        if str(ui_settings.get("last_definitions_export_dir", "")).strip() == new_value:
            return
        ui_settings["last_definitions_export_dir"] = new_value
        try:
            get_settings_manager().save(self._settings)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export Definitions",
                f"Export succeeded, but could not persist picker location: {exc}",
            )

    def _definitions_import_start_path(self) -> str:
        ui_settings = self._settings.setdefault("ui", {})
        file_raw = str(ui_settings.get("last_definitions_import_file", "")).strip()
        if file_raw:
            file_candidate = Path(file_raw).expanduser()
            if file_candidate.exists() and file_candidate.is_file():
                return str(file_candidate)

        dir_raw = str(ui_settings.get("last_definitions_import_dir", "")).strip()
        if dir_raw:
            dir_candidate = Path(dir_raw).expanduser()
            if dir_candidate.exists() and dir_candidate.is_dir():
                return str(dir_candidate)

        export_dir_raw = str(ui_settings.get("last_definitions_export_dir", "")).strip()
        if export_dir_raw:
            export_dir = Path(export_dir_raw).expanduser()
            if export_dir.exists() and export_dir.is_dir():
                return str(export_dir)
        return str(Path.home())

    def _persist_last_definitions_import_path(self, file_path: Path) -> None:
        try:
            resolved = file_path.expanduser().resolve()
        except OSError:
            resolved = file_path.expanduser()

        ui_settings = self._settings.setdefault("ui", {})
        new_file = str(resolved)
        new_dir = str(resolved.parent)
        unchanged = (
            str(ui_settings.get("last_definitions_import_file", "")).strip() == new_file
            and str(ui_settings.get("last_definitions_import_dir", "")).strip() == new_dir
        )
        if unchanged:
            return

        ui_settings["last_definitions_import_file"] = new_file
        ui_settings["last_definitions_import_dir"] = new_dir
        try:
            get_settings_manager().save(self._settings)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Import Definitions",
                f"Import succeeded, but could not persist picker location: {exc}",
            )
