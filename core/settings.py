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
    "ui": {
        "last_import_dir": "",
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

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            try:
                self.save(DEFAULT_SETTINGS)
            except OSError:
                # Non-fatal: app can continue with in-memory defaults.
                pass
            return copy.deepcopy(DEFAULT_SETTINGS)

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            try:
                self.save(DEFAULT_SETTINGS)
            except OSError:
                # Non-fatal: app can continue with in-memory defaults.
                pass
            return copy.deepcopy(DEFAULT_SETTINGS)

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
