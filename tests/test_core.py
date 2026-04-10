from __future__ import annotations

from core.domain import TransactionInput, TransactionSplitInput, TransferInput
from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.bills_repo import BillsRepository
from core.persistence.repositories.budget_allocations_repo import BudgetAllocationsRepository
from core.persistence.repositories.budgets_repo import BudgetsRepository
from core.persistence.repositories.transactions_repo import TransactionsRepository
from core.services.bills import BillsService
from core.services.budget_allocations import BudgetAllocationsService
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


def test_bills_occurrence_edits_are_month_scoped(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    service = BillsService(bills_repo)

    bill_id = bills_repo.add_manual_bill(
        name="Streaming",
        start_date="2026-01-10",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=53700,
        category_id=2,
        notes=None,
    )
    assert bill_id > 0

    inserted_apr = service.generate_for_month(2026, 4)
    inserted_may = service.generate_for_month(2026, 5)
    assert inserted_apr == 1
    assert inserted_may == 1

    april_rows = service.list_month_bills(year=2026, month=4)
    may_rows = service.list_month_bills(year=2026, month=5)
    assert len(april_rows) == 1
    assert len(may_rows) == 1
    assert int(april_rows[0]["expected_amount_cents"]) == 53700
    assert int(may_rows[0]["expected_amount_cents"]) == 53700

    updated = service.update_occurrence(
        bill_occurrence_id=int(april_rows[0]["bill_occurrence_id"]),
        expected_date="2026-04-10",
        expected_amount_cents=53800,
        note="Adjusted for April",
    )
    assert updated == 1

    regenerated_apr = service.generate_for_month(2026, 4)
    assert regenerated_apr == 0

    april_rows_after = service.list_month_bills(year=2026, month=4)
    may_rows_after = service.list_month_bills(year=2026, month=5)
    assert int(april_rows_after[0]["expected_amount_cents"]) == 53800
    assert int(may_rows_after[0]["expected_amount_cents"]) == 53700


def test_bills_regenerate_for_month_replaces_existing_occurrences(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    service = BillsService(bills_repo)

    bill_id = bills_repo.add_manual_bill(
        name="Tithing - Air Force",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=53700,
        category_id=2,
        notes=None,
    )
    assert bill_id > 0

    inserted = service.generate_for_month(2026, 4)
    assert inserted == 1
    april_rows = service.list_month_bills(year=2026, month=4)
    assert len(april_rows) == 1

    service.update_occurrence(
        bill_occurrence_id=int(april_rows[0]["bill_occurrence_id"]),
        expected_date="2026-04-01",
        expected_amount_cents=53800,
        note="Monthly override",
    )
    overridden = service.list_month_bills(year=2026, month=4)
    assert int(overridden[0]["expected_amount_cents"]) == 53800

    bills_repo.update_bill_definition(
        bill_id=int(bill_id),
        name="Tithing - Air Force",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=54000,
        category_id=2,
        notes=None,
    )

    deleted, regenerated = service.regenerate_for_month(2026, 4)
    assert deleted == 1
    assert regenerated == 1

    refreshed = service.list_month_bills(year=2026, month=4)
    assert len(refreshed) == 1
    assert int(refreshed[0]["expected_amount_cents"]) == 54000


def test_bills_regenerate_for_month_can_target_source_system_only(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    service = BillsService(bills_repo)

    budgetpal_bill_id = bills_repo.add_manual_bill(
        name="Manual Bill",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=10000,
        category_id=2,
        notes=None,
    )
    subtracker_bill_id = bills_repo.upsert_bill(
        name="Sub Bill",
        frequency="monthly",
        due_day=1,
        default_amount_cents=20000,
        category_id=2,
        source_system="subtracker",
        source_uid="sub:1",
        notes="Imported from SubTracker",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
    )
    assert budgetpal_bill_id > 0
    assert subtracker_bill_id > 0

    inserted = service.generate_for_month(2026, 4)
    assert inserted == 2
    april_rows = service.list_month_bills(year=2026, month=4)
    by_source = {str(r.get("source_system")): r for r in april_rows}
    assert int(by_source["budgetpal"]["expected_amount_cents"]) == 10000
    assert int(by_source["subtracker"]["expected_amount_cents"]) == 20000

    service.update_occurrence(
        bill_occurrence_id=int(by_source["budgetpal"]["bill_occurrence_id"]),
        expected_date="2026-04-01",
        expected_amount_cents=11111,
        note=None,
    )
    service.update_occurrence(
        bill_occurrence_id=int(by_source["subtracker"]["bill_occurrence_id"]),
        expected_date="2026-04-01",
        expected_amount_cents=22222,
        note=None,
    )

    bills_repo.update_bill_definition(
        bill_id=int(budgetpal_bill_id),
        name="Manual Bill",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=10000,
        category_id=2,
        notes=None,
    )
    bills_repo.update_bill_definition(
        bill_id=int(subtracker_bill_id),
        name="Sub Bill",
        start_date="2026-01-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=23000,
        category_id=2,
        notes="Imported from SubTracker",
    )

    deleted, regenerated = service.regenerate_for_month(2026, 4, source_system="subtracker")
    assert deleted == 1
    assert regenerated == 1

    after = service.list_month_bills(year=2026, month=4)
    after_by_source = {str(r.get("source_system")): r for r in after}
    assert int(after_by_source["budgetpal"]["expected_amount_cents"]) == 11111
    assert int(after_by_source["subtracker"]["expected_amount_cents"]) == 23000


def test_budget_allocations_regenerate_for_month_replaces_instance_values(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    repo = BudgetAllocationsRepository(db)
    service = BudgetAllocationsService(repo)

    definition_id = service.upsert_definition(
        category_id=2,
        amount_cents=50000,
        note="Base allocation",
    )
    assert definition_id > 0

    deleted, inserted = service.regenerate_for_month(2026, 4)
    assert deleted == 0
    assert inserted == 1

    april_rows = service.list_month_allocations(year=2026, month=4)
    assert len(april_rows) == 1
    assert int(april_rows[0]["planned_cents"]) == 50000

    updated = service.update_month_allocation(
        budget_line_id=int(april_rows[0]["budget_line_id"]),
        category_id=2,
        planned_cents=52500,
        note="Monthly override",
    )
    assert updated == 1
    overridden_rows = service.list_month_allocations(year=2026, month=4)
    assert int(overridden_rows[0]["planned_cents"]) == 52500

    service.upsert_definition(
        category_id=2,
        amount_cents=54000,
        note="Definition changed",
    )
    deleted_again, inserted_again = service.regenerate_for_month(2026, 4)
    assert deleted_again == 1
    assert inserted_again == 1
    refreshed_rows = service.list_month_allocations(year=2026, month=4)
    assert int(refreshed_rows[0]["planned_cents"]) == 54000


def test_checking_ledger_includes_prior_uncleared_and_current_month(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)

    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-02-25",
            amount_cents=-2500,
            txn_type="expense",
            payee="Old Uncleared",
            description="Old Uncleared",
            category_id=2,
            account_id=1,  # checking
            source_system="manual",
            source_uid="manual:old-uncleared",
        )
    )
    old_cleared_id = tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-02-26",
            amount_cents=-1500,
            txn_type="expense",
            payee="Old Cleared",
            description="Old Cleared",
            category_id=2,
            account_id=1,  # checking
            source_system="manual",
            source_uid="manual:old-cleared",
        )
    )
    tx_repo.set_transaction_cleared(old_cleared_id, True)
    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-02",
            amount_cents=50000,
            txn_type="income",
            payee="Payroll",
            description="Payroll",
            category_id=1,
            account_id=1,  # checking
            source_system="manual",
            source_uid="manual:current-income",
        )
    )
    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-03",
            amount_cents=-10000,
            txn_type="expense",
            payee="Groceries",
            description="Groceries",
            category_id=4,
            account_id=1,  # checking
            source_system="manual",
            source_uid="manual:current-expense",
        )
    )
    tx_repo.add_transaction(
        TransactionInput(
            txn_date="2026-03-04",
            amount_cents=-7777,
            txn_type="expense",
            payee="Credit Account Expense",
            description="Credit Account Expense",
            category_id=4,
            account_id=3,  # credit
            source_system="manual",
            source_uid="manual:credit-expense",
        )
    )

    rows = tx_repo.list_checking_ledger_for_month(2026, 3)
    descriptions = [str(row.get("description") or "") for row in rows]
    assert descriptions == ["Old Uncleared", "Payroll", "Groceries"]


def test_checking_month_beginning_balance_persists(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    tx_repo = TransactionsRepository(db)
    assert tx_repo.get_checking_month_beginning_balance(2026, 3) == 0

    tx_repo.set_checking_month_beginning_balance(2026, 3, 123456)
    assert tx_repo.get_checking_month_beginning_balance(2026, 3) == 123456
