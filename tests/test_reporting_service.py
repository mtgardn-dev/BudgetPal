from __future__ import annotations

import csv

from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.bills_repo import BillsRepository
from core.persistence.repositories.budget_allocations_repo import (
    BudgetAllocationsRepository,
)
from core.persistence.repositories.income_repo import IncomeRepository
from core.services.reporting import ReportingService


def test_export_global_definitions_writes_snapshot_csvs(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    income_repo = IncomeRepository(db)
    budget_repo = BudgetAllocationsRepository(db)
    reporting = ReportingService(db)

    with db.connection() as conn:
        checking_id = int(
            conn.execute(
                "SELECT account_id FROM accounts WHERE lower(name) = 'checking'"
            ).fetchone()["account_id"]
        )

    bills_repo.add_manual_bill(
        name="Manual Electricity",
        start_date="2026-04-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=5300,
        category_id=2,
        notes="Autopay",
    )
    # Should not be exported in global definitions snapshot.
    bills_repo.upsert_bill(
        name="Imported Subscription",
        frequency="monthly",
        due_day=15,
        default_amount_cents=999,
        category_id=2,
        source_system="subtracker",
        source_uid="sub:1",
        notes="Imported from SubTracker",
        start_date="2026-04-15",
        interval_count=1,
        interval_unit="months",
    )

    income_repo.add_definition(
        description="Pension",
        start_date="2026-04-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=250000,
        category_id=1,
        account_id=checking_id,
        notes="Monthly pension",
        source_system="budgetpal",
    )
    budget_repo.upsert_definition(
        category_id=2,
        default_amount_cents=50000,
        note="Housing allocation",
    )

    output_dir = tmp_path / "definitions_export"
    files = reporting.export_global_definitions(output_dir)
    assert len(files) == 3
    assert all(path.exists() for path in files)

    by_name = {path.name: path for path in files}
    bills_file = next(path for name, path in by_name.items() if "bill_definitions" in name)
    income_file = next(path for name, path in by_name.items() if "income_definitions" in name)
    budget_file = next(path for name, path in by_name.items() if "budget_category_definitions" in name)

    with bills_file.open("r", encoding="utf-8", newline="") as f:
        bill_rows = list(csv.DictReader(f))
    assert len(bill_rows) == 1
    assert bill_rows[0]["name"] == "Manual Electricity"

    with income_file.open("r", encoding="utf-8", newline="") as f:
        income_rows = list(csv.DictReader(f))
    assert len(income_rows) == 1
    assert income_rows[0]["description"] == "Pension"

    with budget_file.open("r", encoding="utf-8", newline="") as f:
        budget_rows = list(csv.DictReader(f))
    assert len(budget_rows) == 1
    assert budget_rows[0]["category_name"] == "Housing"
