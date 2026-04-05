from __future__ import annotations

import copy
import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from core.app_context import BudgetPalContext
from core.importers.subtracker_view import (
    SubTrackerIntegrationError,
    SubTrackerViewImporter,
)
from core.logging_utils import configure_logging
from core.persistence.db import BudgetPalDatabase
from core.settings import DEFAULT_SETTINGS, get_settings_manager
from core.ui.qt.main_window import BudgetPalWindow


def _preflight_subtracker(settings: dict) -> str | None:
    db_path = str(settings.get("subtracker", {}).get("database_path", "")).strip()
    if not db_path:
        return None
    try:
        importer = SubTrackerViewImporter(db_path)
        importer.load_active_subscriptions()
    except SubTrackerIntegrationError as exc:
        return str(exc)
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BudgetPal")

    settings_mgr = get_settings_manager()
    try:
        settings = settings_mgr.load()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Settings Load Error",
            "BudgetPal could not load settings.\n\n"
            f"{exc}\n\n"
            "The app will continue with default in-memory settings for this session.",
        )
        settings = copy.deepcopy(DEFAULT_SETTINGS)

    try:
        logger, log_emitter = configure_logging(settings)
    except Exception as exc:
        fallback_logger = logging.getLogger("budgetpal")
        fallback_logger.setLevel(logging.INFO)
        if not fallback_logger.handlers:
            fallback_logger.addHandler(logging.StreamHandler())
        logger = fallback_logger
        from core.logging_utils import QtLogEmitter

        log_emitter = QtLogEmitter()
        QMessageBox.warning(
            None,
            "Logging Setup Warning",
            "BudgetPal could not initialize file logging.\n\n"
            f"{exc}\n\n"
            "The app will continue with reduced logging for this session.",
        )

    preflight_error = _preflight_subtracker(settings)
    if preflight_error:
        logger.warning("SubTracker preflight warning: %s", preflight_error)

    db_path = str(settings.get("database", {}).get("path", "")).strip()
    try:
        db = BudgetPalDatabase(db_path=db_path or None)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Database Startup Error",
            "BudgetPal could not open the configured database path.\n\n"
            f"{exc}\n\n"
            "Fix Settings > BudgetPal DB Path and restart.",
        )
        return

    context = BudgetPalContext(db=db, settings=settings)
    try:
        window = BudgetPalWindow(context=context, logger=logger, log_emitter=log_emitter)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "UI Startup Error",
            f"BudgetPal failed to initialize the main window:\n\n{exc}",
        )
        return
    window.show()
    if preflight_error:
        # Show after main window exists so the dialog is parented and visible.
        QTimer.singleShot(
            0,
            lambda: QMessageBox.warning(
                window,
                "SubTracker Integration Warning",
                "BudgetPal detected a SubTracker integration issue.\n"
                "The app will still start, but subscription sync may fail.\n\n"
                f"{preflight_error}\n\n"
                "Fix the SubTracker DB/view contract in Settings when ready.",
            ),
        )
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
