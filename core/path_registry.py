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
    def writable_root() -> Path:
        if getattr(sys, "frozen", False):
            path = BudgetPalPathRegistry._frozen_writable_root()
            path.mkdir(parents=True, exist_ok=True)
            return path
        return BudgetPalPathRegistry.project_root()

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
