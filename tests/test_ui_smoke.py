from __future__ import annotations

import os
from datetime import date

from PySide6.QtWidgets import QApplication

from core.app_context import BudgetPalContext
from core.domain import TransactionInput
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


def test_credit_account_clearing_uses_debt_perspective_totals(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])

    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    credit_account_id = 3

    carry_forward_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-03-15",
            amount_cents=1000,
            txn_type="expense",
            payee="Prior Uncleared",
            account_id=credit_account_id,
            description="Prior Uncleared",
            source_uid="test:prior-uncleared",
        )
    )
    prior_cleared_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-03-16",
            amount_cents=2000,
            txn_type="expense",
            payee="Prior Cleared",
            account_id=credit_account_id,
            description="Prior Cleared",
            source_uid="test:prior-cleared",
        )
    )
    current_cleared_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-04-05",
            amount_cents=3000,
            txn_type="expense",
            payee="Current Cleared",
            account_id=credit_account_id,
            description="Current Cleared",
            source_uid="test:current-cleared",
        )
    )
    current_payment_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-04-10",
            amount_cents=500,
            txn_type="income",
            payee="Payment",
            account_id=credit_account_id,
            description="Payment",
            source_uid="test:payment",
        )
    )
    context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-04-12",
            amount_cents=4000,
            txn_type="expense",
            payee="Current Uncleared",
            account_id=credit_account_id,
            description="Current Uncleared",
            source_uid="test:current-uncleared",
        )
    )
    context.transactions_service.set_transaction_cleared(prior_cleared_id, True)
    context.transactions_service.set_transaction_cleared(current_cleared_id, True)
    context.transactions_service.set_transaction_cleared(current_payment_id, True)

    window = BudgetPalWindow(context=context, logger=DummyLogger(), log_emitter=QtLogEmitter())
    window._set_accounts_view_month(2026, 4)
    window.refresh_accounts()

    pane = window.accounts_tab.pane_for_account_id(credit_account_id)
    assert pane is not None
    descriptions = [
        str(pane.model.row_dict(row_index)["description_display"])
        for row_index in range(pane.model.rowCount())
    ]
    assert "Prior Uncleared" in descriptions
    assert "Prior Cleared" not in descriptions
    assert int(carry_forward_id) > 0
    assert pane.beginning_balance_input.isHidden()
    assert pane.statement_ending_input.isHidden()
    assert pane.computed_current_balance_label.text() == "Cleared Transactions"
    assert pane.computed_current_balance_value.text() == "+$25.00"
    assert pane.computed_available_credit_label.text() == "Uncleared Transactions"
    assert pane.computed_available_credit_value.text() == "+$50.00"
    assert pane.adjusted_statement_label.text() == "Uncleared Carry-Forward"
    assert pane.adjusted_statement_value.text() == "+$10.00"
    assert pane.reconciliation_diff_label.text() == "Total Activity"
    assert pane.reconciliation_diff_value.text() == "+$75.00"

    window.close()
    app.quit()
