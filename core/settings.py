from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.path_registry import BudgetPalPathRegistry

DEFAULT_SETTINGS: dict[str, Any] = {
    "database": {"path": ""},
    "subtracker": {"database_path": ""},
    "logging": {
        "level": "INFO",
        "max_bytes": 1_000_000,
        "backup_count": 5,
    },
    "backup": {
        "directory": "",
        "base_name": "budgetpal_backup",
    },
    "transfers": {
        "rules": [
            {
                "name": "Budget Savings to Savings",
                "enabled": False,
                "match_category": "Budget Savings",
                "match_description": "",
                "from_account_number": "",
                "from_account_alias": "",
                "from_account_type": "checking",
                "to_account_number": "",
                "to_account_alias": "",
                "to_account_type": "savings",
            },
            {
                "name": "Pocket Change to Pocket Change",
                "enabled": False,
                "match_category": "Pocket Change",
                "match_description": "",
                "from_account_number": "",
                "from_account_alias": "",
                "from_account_type": "checking",
                "to_account_number": "",
                "to_account_alias": "",
                "to_account_type": "savings",
            },
        ]
    },
    "ui": {
        "last_import_dir": "",
        "last_bills_report_dir": "",
        "last_categories_export_dir": "",
        "last_definitions_export_dir": "",
        "last_definitions_import_dir": "",
        "last_definitions_import_file": "",
        "last_reports_export_dir": "",
        "window": {
            "width": 1240,
            "height": 820,
            "x": None,
            "y": None,
        }
    },
}


@dataclass
class BudgetPalSettings:
    path: Path | None = None

    def __post_init__(self) -> None:
        self.path = self.path or BudgetPalPathRegistry.config_file()

    def _seed_defaults(self) -> dict[str, Any]:
        seeded = copy.deepcopy(DEFAULT_SETTINGS)
        template_path = BudgetPalPathRegistry.bundled_config_template_file()
        if template_path:
            try:
                incoming = json.loads(template_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                incoming = None
            if isinstance(incoming, dict):
                self._deep_merge(seeded, incoming)
        return seeded

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            seeded = self._seed_defaults()
            try:
                self.save(seeded)
            except OSError:
                # Non-fatal: app can continue with in-memory defaults.
                pass
            return seeded

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            seeded = self._seed_defaults()
            try:
                self.save(seeded)
            except OSError:
                # Non-fatal: app can continue with in-memory defaults.
                pass
            return seeded

        merged = copy.deepcopy(DEFAULT_SETTINGS)
        self._deep_merge(merged, data)
        try:
            # Best-effort normalization writeback so new keys appear in file.
            self.save(merged)
        except OSError:
            # Non-fatal: keep running with merged in-memory settings.
            pass
        return merged

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

    def _deep_merge(self, base: dict[str, Any], incoming: dict[str, Any]) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_merge(base[key], value)  # type: ignore[index]
            else:
                base[key] = value


def get_settings_manager() -> BudgetPalSettings:
    return BudgetPalSettings()
