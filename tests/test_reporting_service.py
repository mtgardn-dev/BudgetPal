from __future__ import annotations

import csv

import pytest

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
    assert len(files) == 4
    assert all(path.exists() for path in files)

    by_name = {path.name: path for path in files}
    bills_file = next(path for name, path in by_name.items() if "bill_definitions" in name)
    income_file = next(path for name, path in by_name.items() if "income_definitions" in name)
    budget_file = next(path for name, path in by_name.items() if "budget_category_definitions" in name)
    accounts_file = next(path for name, path in by_name.items() if "account_definitions" in name)

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

    with accounts_file.open("r", encoding="utf-8", newline="") as f:
        account_rows = list(csv.DictReader(f))
    assert len(account_rows) >= 1
    assert any(str(row.get("account_name", "")).strip() for row in account_rows)


def _rewrite_csv_rows(file_path, rows) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with file_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_import_global_definitions_upserts_existing_rows(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    bills_repo = BillsRepository(db)
    income_repo = IncomeRepository(db)
    budget_repo = BudgetAllocationsRepository(db)
    reporting = ReportingService(db)

    with db.connection() as conn:
        checking_id = int(
            conn.execute("SELECT account_id FROM accounts WHERE lower(name) = 'checking'").fetchone()[
                "account_id"
            ]
        )

    bills_repo.add_manual_bill(
        name="Water Bill",
        start_date="2026-05-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=4200,
        category_id=2,
        notes="Original bill note",
    )
    income_repo.add_definition(
        description="Pension",
        start_date="2026-05-01",
        interval_count=1,
        interval_unit="months",
        default_amount_cents=150000,
        category_id=1,
        account_id=checking_id,
        notes="Original income note",
        source_system="budgetpal",
    )
    budget_repo.upsert_definition(
        category_id=2,
        default_amount_cents=60000,
        note="Original budget note",
    )

    export_dir = tmp_path / "defs"
    files = reporting.export_global_definitions(export_dir)
    by_name = {path.name: path for path in files}
    bills_file = next(path for name, path in by_name.items() if "bill_definitions" in name)
    income_file = next(path for name, path in by_name.items() if "income_definitions" in name)
    budget_file = next(path for name, path in by_name.items() if "budget_category_definitions" in name)
    accounts_file = next(path for name, path in by_name.items() if "account_definitions" in name)

    with bills_file.open("r", encoding="utf-8", newline="") as f:
        bill_rows = list(csv.DictReader(f))
    bill_rows[0]["default_amount_cents"] = "4300"
    bill_rows[0]["notes"] = "Updated bill note"
    _rewrite_csv_rows(bills_file, bill_rows)

    with income_file.open("r", encoding="utf-8", newline="") as f:
        income_rows = list(csv.DictReader(f))
    income_rows[0]["default_amount_cents"] = "151000"
    income_rows[0]["notes"] = "Updated income note"
    _rewrite_csv_rows(income_file, income_rows)

    with budget_file.open("r", encoding="utf-8", newline="") as f:
        budget_rows = list(csv.DictReader(f))
    budget_rows[0]["default_amount_cents"] = "61000"
    budget_rows[0]["note"] = "Updated budget note"
    _rewrite_csv_rows(budget_file, budget_rows)

    with accounts_file.open("r", encoding="utf-8", newline="") as f:
        account_rows = list(csv.DictReader(f))
    target_account_id = int(account_rows[0]["definition_id"])
    account_rows[0]["notes"] = "Updated account note"
    account_rows[0]["account_number"] = "xxxx-1234"
    _rewrite_csv_rows(accounts_file, account_rows)

    bills_result = reporting.import_global_definitions("bills", bills_file)
    income_result = reporting.import_global_definitions("income", income_file)
    budget_result = reporting.import_global_definitions("budget_allocations", budget_file)
    accounts_result = reporting.import_global_definitions("accounts", accounts_file)

    assert bills_result["updated"] == 1
    assert bills_result["inserted"] == 0
    assert income_result["updated"] == 1
    assert income_result["inserted"] == 0
    assert budget_result["updated"] == 1
    assert budget_result["inserted"] == 0
    assert accounts_result["updated"] >= 1
    assert accounts_result["inserted"] == 0

    with db.connection() as conn:
        bill_row = conn.execute(
            "SELECT default_amount_cents, notes FROM bills WHERE source_system='budgetpal' AND name='Water Bill'"
        ).fetchone()
        assert int(bill_row["default_amount_cents"]) == 4300
        assert str(bill_row["notes"]) == "Updated bill note"

        income_row = conn.execute(
            "SELECT default_amount_cents, notes FROM income_definitions WHERE description='Pension'"
        ).fetchone()
        assert int(income_row["default_amount_cents"]) == 151000
        assert str(income_row["notes"]) == "Updated income note"

        budget_row = conn.execute(
            """
            SELECT d.default_amount_cents, d.note
            FROM budget_category_definitions d
            JOIN categories c ON c.category_id = d.category_id
            WHERE c.name = 'Housing'
            """
        ).fetchone()
        assert int(budget_row["default_amount_cents"]) == 61000
        assert str(budget_row["note"]) == "Updated budget note"

        account_row = conn.execute(
            """
            SELECT account_number, notes
            FROM accounts
            WHERE account_id = ?
            """,
            (target_account_id,),
        ).fetchone()
        assert account_row is not None
        assert str(account_row["account_number"]) == "xxxx-1234"
        assert str(account_row["notes"]) == "Updated account note"


def test_import_global_definitions_validation_errors_abort_transaction(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    budget_repo = BudgetAllocationsRepository(db)
    reporting = ReportingService(db)

    budget_repo.upsert_definition(
        category_id=2,
        default_amount_cents=50000,
        note="Baseline",
    )

    invalid_file = tmp_path / "invalid_budget_defs.csv"
    with invalid_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["definition_id", "category_id", "category_name", "default_amount_cents", "note"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "definition_id": "1",
                "category_id": "999999",
                "category_name": "Unknown",
                "default_amount_cents": "77777",
                "note": "Invalid category id",
            }
        )

    with pytest.raises(ValueError, match="category_name 'Unknown' does not exist"):
        reporting.import_global_definitions("budget_allocations", invalid_file)

    with db.connection() as conn:
        rows = conn.execute(
            "SELECT default_amount_cents, note FROM budget_category_definitions WHERE category_id = 2"
        ).fetchall()
    assert len(rows) == 1
    assert int(rows[0]["default_amount_cents"]) == 50000
    assert str(rows[0]["note"]) == "Baseline"


def test_import_global_definitions_category_name_remaps_mismatched_id(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    budget_repo = BudgetAllocationsRepository(db)
    reporting = ReportingService(db)

    budget_repo.upsert_definition(
        category_id=2,
        default_amount_cents=50000,
        note="Baseline",
    )

    mismatched_file = tmp_path / "budget_defs_mismatch.csv"
    with mismatched_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["definition_id", "category_id", "category_name", "default_amount_cents", "note"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "definition_id": "",
                "category_id": "999999",
                "category_name": "Housing",
                "default_amount_cents": "74000",
                "note": "Remapped by category name",
            }
        )

    result = reporting.import_global_definitions("budget_allocations", mismatched_file)
    assert int(result["updated"]) == 1
    assert int(result["inserted"]) == 0

    with db.connection() as conn:
        row = conn.execute(
            "SELECT default_amount_cents, note FROM budget_category_definitions WHERE category_id = 2"
        ).fetchone()
    assert row is not None
    assert int(row["default_amount_cents"]) == 74000
    assert str(row["note"]) == "Remapped by category name"
