from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from core.app_context import BudgetPalContext
from core.importers.subtracker_view import (
    SubTrackerIntegrationError,
    SubTrackerViewImporter,
)
from core.logging_utils import configure_logging
from core.persistence.db import BudgetPalDatabase
from core.settings import get_settings_manager
from core.ui.qt.main_window import BudgetPalWindow


def _preflight_subtracker(settings: dict) -> None:
    db_path = str(settings.get("subtracker", {}).get("database_path", "")).strip()
    if not db_path:
        return
    importer = SubTrackerViewImporter(db_path)
    importer.load_active_subscriptions()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BudgetPal")

    settings_mgr = get_settings_manager()
    settings = settings_mgr.load()

    logger, log_emitter = configure_logging(settings)

    try:
        _preflight_subtracker(settings)
    except SubTrackerIntegrationError as exc:
        QMessageBox.critical(
            None,
            "SubTracker Integration Startup Error",
            "BudgetPal failed its SubTracker contract preflight.\n\n"
            f"{exc}\n\n"
            "Fix the SubTracker DB/view contract before launching BudgetPal.",
        )
        return

    db_path = str(settings.get("database", {}).get("path", "")).strip()
    db = BudgetPalDatabase(db_path=db_path or None)

    context = BudgetPalContext(db=db, settings=settings)
    window = BudgetPalWindow(context=context, logger=logger, log_emitter=log_emitter)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
