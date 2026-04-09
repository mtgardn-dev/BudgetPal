from __future__ import annotations

from core.domain import TransactionInput, TransactionSplitInput, TransferInput
from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.bills_repo import BillsRepository
from core.persistence.repositories.budgets_repo import BudgetsRepository
from core.persistence.repositories.transactions_repo import TransactionsRepository
from core.services.bills import BillsService
from core.services.budgeting import BudgetingService


def test_transfer_creates_two_linked_rows(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)

    group_id = tx_repo.add_transfer(
        TransferInput(
            txn_date="2026-03-01",
            amount_cents=25000,
            from_account_id=1,
            to_account_id=2,
            payee="Internal Transfer",
        )
    )

    rows = tx_repo.get_transfer_rows(group_id)
    assert len(rows) == 2
    amounts = sorted(int(r["amount_cents"]) for r in rows)
    assert amounts == [-25000, 25000]
    account_ids = {int(r["account_id"]) for r in rows}
    assert account_ids == {1, 2}


def test_transaction_splits_require_exact_total(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)

    txn_id = tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-01",
            amount_cents=-3000,
            txn_type="expense",
            payee="Supermarket",
            category_id=4,
            account_id=1,
            source_system="manual",
            source_uid="txn-1",
        )
    )

    tx_repo.add_splits(
        txn_id,
        [
            TransactionSplitInput(category_id=4, amount_cents=-1000),
            TransactionSplitInput(category_id=11, amount_cents=-2000),
        ],
    )

    raised = False
    try:
        tx_repo.add_splits(
            txn_id,
            [
                TransactionSplitInput(category_id=4, amount_cents=-1000),
                TransactionSplitInput(category_id=11, amount_cents=-1000),
            ],
        )
    except ValueError:
        raised = True

    assert raised is True


def test_monthly_cashflow_signed_amounts(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)
    budget_repo = BudgetsRepository(db)
    service = BudgetingService(budget_repo, tx_repo)

    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-03",
            amount_cents=500000,
            txn_type="income",
            payee="Payroll",
            category_id=1,
            account_id=1,
            source_system="manual",
            source_uid="income-1",
        )
    )
    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-05",
            amount_cents=-125000,
            txn_type="expense",
            payee="Mortgage",
            category_id=2,
            account_id=1,
            source_system="manual",
            source_uid="expense-1",
        )
    )

    values = service.monthly_cashflow(2026, 3, starting_balance_cents=100000)
    assert values["income_cents"] == 500000
    assert values["expense_cents"] == 125000
    assert values["net_cents"] == 375000
    assert values["end_balance_cents"] == 475000


def test_transaction_crud_and_month_listing(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)

    txn_id = tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-14",
            amount_cents=-7468,
            txn_type="expense",
            payee="Insurance payment",
            description="Insurance payment",
            category_id=6,
            account_id=1,
            source_system="manual",
            source_uid="manual:txn-1",
        )
    )

    loaded = tx_repo.get_transaction(txn_id)
    assert loaded is not None
    assert int(loaded["amount_cents"]) == -7468
    assert str(loaded["import_period_key"]) == "2026-03"

    updated_count = tx_repo.update_transaction(
        txn_id,
        TransactionInput(
            txn_date="2026-03-14",
            amount_cents=-8000,
            txn_type="expense",
            payee="Insurance updated",
            description="Insurance updated",
            category_id=6,
            account_id=1,
            source_system="manual",
            source_uid="manual:txn-1",
        ),
    )
    assert updated_count == 1

    monthly = tx_repo.list_transactions_for_month(2026, 3)
    assert len(monthly) == 1
    assert monthly[0]["description_display"] == "Insurance updated"
    assert int(monthly[0]["account_id"]) == 1
    assert str(monthly[0]["import_period_key"]) == "2026-03"
    assert "2026-03" in tx_repo.list_available_months()

    deleted_count = tx_repo.delete_transaction(txn_id)
    assert deleted_count == 1
    assert tx_repo.get_transaction(txn_id) is None


def test_bills_service_filters_due_rows_by_selected_month(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    service = BillsService(bills_repo)

    category_id = 2
    bills_repo.add_manual_bill(
        name="Monthly Utilities",
        start_date="2026-01-15",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=7500,
        category_id=category_id,
        notes=None,
    )
    bills_repo.add_manual_bill(
        name="Quarterly Insurance",
        start_date="2026-01-20",
        interval_count=3,
        interval_unit="months",
        default_amount_cents=25000,
        category_id=category_id,
        notes=None,
    )

    april_rows = service.list_bill_definitions(sort_by="payment_due", year=2026, month=4)
    april_names = [str(r["name"]) for r in april_rows]
    assert "Monthly Utilities" in april_names
    assert "Quarterly Insurance" in april_names

    may_rows = service.list_bill_definitions(sort_by="payment_due", year=2026, month=5)
    may_names = [str(r["name"]) for r in may_rows]
    assert "Monthly Utilities" in may_names
    assert "Quarterly Insurance" not in may_names
