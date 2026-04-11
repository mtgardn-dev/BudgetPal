from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Dict

from core.path_registry import BudgetPalPathRegistry


class HelpService:
    """Local static-help launcher for BudgetPal."""

    HELP_TOPICS: Dict[str, str] = {
        "index": "index.html",
        "getting_started": "getting_started.html",
        "ui_reference": "ui_reference.html",
        "global_month_model": "global_month_model.html",
        "subtracker_integration": "subtracker_integration.html",
        "architecture": "architecture.html",
        "settings_reference": "settings_reference.html",
        "troubleshooting": "troubleshooting.html",
        "about": "about_help.html",
    }

    def __init__(self) -> None:
        self.help_root = BudgetPalPathRegistry.help_root()

    def get_help_path(self, filename: str) -> Path:
        if self.help_root is None:
            raise FileNotFoundError("Help directory not found.")
        clean_name = str(filename or "").strip()
        if not clean_name:
            raise ValueError("Help filename is required.")
        if Path(clean_name).is_absolute() or ".." in Path(clean_name).parts:
            raise ValueError("Help filename must be a relative path inside the help folder.")
        return (self.help_root / clean_name).resolve()

    def help_file_exists(self, filename: str) -> bool:
        path = self.get_help_path(filename)
        return path.exists() and path.is_file()

    def get_topic_path(self, topic_name: str) -> Path:
        topic = str(topic_name or "").strip().lower()
        if topic not in self.HELP_TOPICS:
            raise ValueError(f"Unknown help topic: {topic_name}")
        return self.get_help_path(self.HELP_TOPICS[topic])

    def open_main_help(self) -> bool:
        return self.open_topic("index")

    def open_topic(self, topic_name: str) -> bool:
        path = self.get_topic_path(topic_name)
        if not path.exists():
            raise FileNotFoundError(f"Missing help file: {path}")
        return bool(webbrowser.open(path.as_uri()))
