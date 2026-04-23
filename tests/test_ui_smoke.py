from __future__ import annotations

import os
from datetime import date

from PySide6.QtWidgets import QApplication

from core.app_context import BudgetPalContext
from core.logging_utils import QtLogEmitter
from core.persistence.db import BudgetPalDatabase
from core.ui.qt.main_window import BudgetPalWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class DummyLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message, *args):
        if args:
            message = message % args
        self.messages.append(str(message))

    def error(self, message, *args):
        if args:
            message = message % args
        self.messages.append(str(message))


def test_budgetpal_window_smoke(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])

    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)

    window = BudgetPalWindow(context=context, logger=DummyLogger(), log_emitter=QtLogEmitter())
    assert window.tabs.count() == 8
    assert window.windowTitle() == "BudgetPal"
    assert window.log_area.isReadOnly()
    assert window.settings_button.text() == "Settings"
    assert window.transactions_tab.save_button.text() == "Save"
    assert window.transactions_tab.month_filter.count() >= 1
    assert window.transactions_tab.month_filter.currentText() == date.today().strftime("%Y-%m")
    assert window.transfers_tab.month_filter.currentText() == date.today().strftime("%Y-%m")
    assert not hasattr(window.transactions_tab, "reconcile_button")
    window.close()
    app.quit()
