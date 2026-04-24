from __future__ import annotations

import os
import sys
from pathlib import Path


class BudgetPalPathRegistry:
    """Central registry for all BudgetPal filesystem locations."""

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def runtime_root() -> Path:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                return Path(meipass).resolve()
            return Path(sys.executable).resolve().parent
        return BudgetPalPathRegistry.project_root()

    @staticmethod
    def _frozen_writable_root() -> Path:
        if sys.platform.startswith("win"):
            base = Path(
                os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or (Path.home() / "AppData" / "Local")
            )
            return base / "BudgetPal"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "BudgetPal"

        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        return base / "budgetpal"

    @staticmethod
    def _first_existing_path(candidates: list[Path]) -> Path | None:
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    @staticmethod
    def writable_root() -> Path:
        if getattr(sys, "frozen", False):
            path = BudgetPalPathRegistry._frozen_writable_root()
            path.mkdir(parents=True, exist_ok=True)
            return path
        return BudgetPalPathRegistry.project_root()

    @classmethod
    def bundled_config_template_file(cls) -> Path | None:
        if not getattr(sys, "frozen", False):
            return None

        runtime = cls.runtime_root()
        candidates = [
            runtime / "config" / "budgetpal_config.json",
            runtime / "config" / "budgetpal_config.example.json",
            runtime / "bootstrap_data" / "config" / "budgetpal_config.json",
            runtime / "bootstrap_data" / "config" / "budgetpal_config.example.json",
        ]
        return cls._first_existing_path(candidates)

    @classmethod
    def build_metadata_file(cls) -> Path | None:
        runtime = cls.runtime_root()
        candidates = [
            runtime / "bootstrap_data" / "version.json",
            runtime / "version.json",
            cls.project_root() / "bootstrap_data" / "version.json",
        ]
        return cls._first_existing_path(candidates)

    @classmethod
    def logo_image_file(cls) -> Path | None:
        runtime = cls.runtime_root()
        candidates = [
            runtime / "images" / "BudgetPal_Logo_Lg.png",
            runtime / "bootstrap_data" / "images" / "BudgetPal_Logo_Lg.png",
            cls.project_root() / "images" / "BudgetPal_Logo_Lg.png",
        ]
        return cls._first_existing_path(candidates)

    @classmethod
    def help_root(cls) -> Path | None:
        runtime = cls.runtime_root()
        candidates = [
            runtime / "help",
            runtime / "bootstrap_data" / "help",
            cls.project_root() / "help",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()
        return None

    @classmethod
    def transactions_template_file(cls) -> Path | None:
        runtime = cls.runtime_root()
        candidates = [
            runtime / "templates" / "BudgetPal Transactions Template.xlsx",
            runtime / "bootstrap_data" / "templates" / "BudgetPal Transactions Template.xlsx",
            cls.project_root() / "templates" / "BudgetPal Transactions Template.xlsx",
        ]
        return cls._first_existing_path(candidates)

    @classmethod
    def config_dir(cls) -> Path:
        path = cls.writable_root() / "config"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def config_file(cls) -> Path:
        return cls.config_dir() / "budgetpal_config.json"

    @classmethod
    def database_dir(cls) -> Path:
        path = cls.writable_root() / "database"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def database_file(cls) -> Path:
        return cls.database_dir() / "budgetpal.sqlite"

    @classmethod
    def logs_dir(cls) -> Path:
        path = cls.writable_root() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def log_file(cls) -> Path:
        return cls.logs_dir() / "budgetpal.log"

    @classmethod
    def exports_dir(cls) -> Path:
        path = cls.writable_root() / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path
