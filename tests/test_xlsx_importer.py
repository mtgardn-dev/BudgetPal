from __future__ import annotations

import pytest

from core.app_context import BudgetPalContext
from core.domain import TransactionInput, TransferInput
from core.importers.xlsx_transactions import XLSXTransactionImporter
from core.persistence.db import BudgetPalDatabase

openpyxl = pytest.importorskip("openpyxl")


def _write_transactions_workbook(path, expense_rows, income_rows) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"

    ws["A1"] = "Expenses"
    ws["A2"] = "Date"
    ws["B2"] = "Amount"
    ws["C2"] = "Description"
    ws["D2"] = "Category"
    ws["E2"] = "Account"
    ws["F2"] = "Subscription"
    ws["G2"] = "Tax"
    ws["H2"] = "Type"
    ws["I2"] = "Note"

    ws["K1"] = "Income"
    ws["K2"] = "Date"
    ws["L2"] = "Amount"
    ws["M2"] = "Description"
    ws["N2"] = "Category"
    ws["O2"] = "Account"
    ws["P2"] = "Tax"
    ws["Q2"] = "Type"
    ws["R2"] = "Note"

    row = 3
    for rec in expense_rows:
        date_value, amount_value, description, category = rec[:4]
        # Default to a valid seeded account alias unless a test explicitly provides one.
        account = rec[4] if len(rec) >= 5 else "Checking"
        subscription = rec[5] if len(rec) >= 6 else ""
        tax = rec[6] if len(rec) >= 7 else ""
        payment_type = rec[7] if len(rec) >= 8 else ""
        note = rec[8] if len(rec) >= 9 else ""
        ws.cell(row=row, column=1, value=date_value)
        ws.cell(row=row, column=2, value=amount_value)
        ws.cell(row=row, column=3, value=description)
        ws.cell(row=row, column=4, value=category)
        ws.cell(row=row, column=5, value=account)
        ws.cell(row=row, column=6, value=subscription)
        ws.cell(row=row, column=7, value=tax)
        ws.cell(row=row, column=8, value=payment_type)
        ws.cell(row=row, column=9, value=note)
        row += 1

    row = 3
    for rec in income_rows:
        date_value, amount_value, description, category = rec[:4]
        # Default to a valid seeded account alias unless a test explicitly provides one.
        account = rec[4] if len(rec) >= 5 else "Checking"
        tax = rec[5] if len(rec) >= 6 else ""
        payment_type = rec[6] if len(rec) >= 7 else ""
        note = rec[7] if len(rec) >= 8 else ""
        ws.cell(row=row, column=11, value=date_value)
        ws.cell(row=row, column=12, value=amount_value)
        ws.cell(row=row, column=13, value=description)
        ws.cell(row=row, column=14, value=category)
        ws.cell(row=row, column=15, value=account)
        ws.cell(row=row, column=16, value=tax)
        ws.cell(row=row, column=17, value=payment_type)
        ws.cell(row=row, column=18, value=note)
        row += 1

    wb.save(path)


def test_xlsx_import_replaces_monthly_baseline(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)

    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    first_file = tmp_path / "first.xlsx"
    _write_transactions_workbook(
        first_file,
        expense_rows=[
            ("2/1/2026", 74.68, "Insurance payment", "Insurance"),
            ("2/2/2026", 150.00, "Home maintenance", "Home"),
        ],
        income_rows=[
            ("2/1/2026", 2374.04, "ERB deposit", "ERB"),
        ],
    )
    first_result = importer.import_file(first_file)
    assert first_result.deleted_count == 0
    assert first_result.imported_count == 3
    assert first_result.year_month_keys == ("2026-02",)

    second_file = tmp_path / "second.xlsx"
    _write_transactions_workbook(
        second_file,
        expense_rows=[
            ("2/1/2026", 80.00, "Insurance payment revised", "Insurance"),
        ],
        income_rows=[
            ("2/1/2026", 2400.00, "ERB deposit revised", "ERB"),
        ],
    )
    second_result = importer.import_file(second_file)
    assert second_result.deleted_count == 3
    assert second_result.imported_count == 2

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT txn_date, amount_cents, payee, source_system
            FROM transactions
            WHERE substr(txn_date, 1, 7) = '2026-02'
            ORDER BY txn_date, txn_id
            """
        ).fetchall()

    assert len(rows) == 2
    assert all(r["source_system"] == "xlsx_import" for r in rows)
    amounts = sorted(int(r["amount_cents"]) for r in rows)
    assert amounts == [-8000, 240000]


def test_xlsx_import_raises_when_transactions_sheet_missing(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    wb = openpyxl.Workbook()
    wb.active.title = "NotTransactions"
    bad_file = tmp_path / "bad.xlsx"
    wb.save(bad_file)

    with pytest.raises(ValueError, match="Worksheet 'Transactions' was not found"):
        importer.import_file(bad_file)


def test_xlsx_import_requires_account_alias_match(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "invalid_account_alias.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/1/2026", 25.00, "Alias mismatch", "Misc", "credit", False, False, "card", ""),
        ],
        income_rows=[],
    )

    with pytest.raises(ValueError, match="Account alias validation failed"):
        importer.import_file(workbook)

    with db.connection() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    assert count == 0


def test_xlsx_import_allows_out_of_month_transactions_in_same_sheet(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    mixed_month_file = tmp_path / "mixed_months.xlsx"
    _write_transactions_workbook(
        mixed_month_file,
        expense_rows=[
            ("2/1/2026", 74.68, "Insurance payment", "Insurance"),
        ],
        income_rows=[
            ("3/1/2026", 2374.04, "ERB deposit", "ERB"),
        ],
    )

    result = importer.import_file(mixed_month_file)
    assert result.imported_count == 2
    assert result.import_period_key == "2026-02"
    assert result.year_month_keys == ("2026-02",)

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT txn_date, import_period_key
            FROM transactions
            ORDER BY txn_id
            """
        ).fetchall()

    assert len(rows) == 2
    assert str(rows[0]["txn_date"]) == "2026-02-01"
    assert str(rows[1]["txn_date"]) == "2026-03-01"
    assert all(str(r["import_period_key"]) == "2026-02" for r in rows)


def test_xlsx_import_replaces_all_rows_for_period_key(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    first_file = tmp_path / "baseline.xlsx"
    _write_transactions_workbook(
        first_file,
        expense_rows=[("2/1/2026", 10.00, "Sheet Expense", "Home")],
        income_rows=[("2/1/2026", 20.00, "Sheet Income", "ERB")],
    )
    first_result = importer.import_file(first_file)
    assert first_result.imported_count == 2

    manual_txn_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-02-03",
            amount_cents=-1234,
            txn_type="expense",
            payee="Manual entry",
            description="Manual entry",
            category_id=11,  # Misc
            account_id=1,  # Checking
            source_system="manual",
            source_uid="manual:test",
        )
    )
    assert manual_txn_id > 0

    second_file = tmp_path / "replacement.xlsx"
    _write_transactions_workbook(
        second_file,
        expense_rows=[("2/4/2026", 50.00, "Replacement Expense", "Home")],
        income_rows=[("2/4/2026", 100.00, "Replacement Income", "ERB")],
    )
    second_result = importer.import_file(second_file)
    assert second_result.deleted_count == 3
    assert second_result.imported_count == 2

    with db.connection() as conn:
        month_rows = conn.execute(
            """
            SELECT source_system, description, import_period_key
            FROM transactions
            WHERE substr(txn_date, 1, 7) = '2026-02'
            ORDER BY txn_id
            """
        ).fetchall()
        manual_row = conn.execute(
            "SELECT txn_id FROM transactions WHERE txn_id = ?",
            (manual_txn_id,),
        ).fetchone()

    assert manual_row is None
    assert len(month_rows) == 2
    assert all(str(r["source_system"]) == "xlsx_import" for r in month_rows)
    assert all(str(r["import_period_key"]) == "2026-02" for r in month_rows)


def test_xlsx_import_replacement_uses_import_period_key_not_txn_date_month(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    first_file = tmp_path / "period_mixed_first.xlsx"
    _write_transactions_workbook(
        first_file,
        expense_rows=[
            ("2/28/2026", 30.00, "End of month expense", "Home"),
            ("3/01/2026", 40.00, "Late recorded expense", "Home"),
        ],
        income_rows=[],
    )
    first_result = importer.import_file(first_file)
    assert first_result.import_period_key == "2026-02"
    assert first_result.imported_count == 2

    second_file = tmp_path / "period_mixed_second.xlsx"
    _write_transactions_workbook(
        second_file,
        expense_rows=[
            ("2/15/2026", 99.00, "Replacement February expense", "Home"),
        ],
        income_rows=[],
    )
    second_result = importer.import_file(second_file)
    assert second_result.import_period_key == "2026-02"
    assert second_result.deleted_count == 2
    assert second_result.imported_count == 1

    with db.connection() as conn:
        march_rows = conn.execute(
            """
            SELECT txn_id
            FROM transactions
            WHERE txn_date = '2026-03-01'
            """
        ).fetchall()
        period_rows = conn.execute(
            """
            SELECT txn_date, description
            FROM transactions
            WHERE import_period_key = '2026-02'
            ORDER BY txn_date
            """
        ).fetchall()

    assert len(march_rows) == 0
    assert len(period_rows) == 1
    assert str(period_rows[0]["txn_date"]) == "2026-02-15"


def test_xlsx_import_parses_account_subscription_tax_columns(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "columns.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            (
                "2/5/2026",
                45.67,
                "Music plan",
                "Entertainment",
                "Credit Card",
                True,
                True,
                "usaa",
                "1 of 2 totaling $100",
            ),
            ("2/6/2026", 20.00, "Coffee", "Misc", "cash", False, False, "venmo", ""),
        ],
        income_rows=[
            ("2/7/2026", 1000.00, "Payroll", "Income", "checking", True, "ach", "direct deposit"),
            ("2/8/2026", 200.00, "Bonus", "Income", "checking", "", "", ""),
        ],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 4

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.description,
                t.txn_type,
                t.is_subscription,
                t.tax_deductible,
                t.payment_type,
                t.note,
                a.account_type
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            WHERE substr(t.txn_date, 1, 7) = '2026-02'
            ORDER BY t.txn_date, t.txn_id
            """
        ).fetchall()

    by_description = {str(r["description"]): dict(r) for r in rows}
    assert by_description["Music plan"]["account_type"] == "credit"
    assert int(by_description["Music plan"]["is_subscription"]) == 1
    assert int(by_description["Music plan"]["tax_deductible"]) == 1
    assert by_description["Music plan"]["payment_type"] == "usaa"
    assert by_description["Music plan"]["note"] == "1 of 2 totaling $100"
    assert by_description["Coffee"]["account_type"] == "cash"
    assert int(by_description["Coffee"]["is_subscription"]) == 0
    assert int(by_description["Coffee"]["tax_deductible"]) == 0
    assert by_description["Coffee"]["payment_type"] == "venmo"
    assert by_description["Coffee"]["note"] in (None, "")
    assert by_description["Payroll"]["account_type"] == "checking"
    assert int(by_description["Payroll"]["is_subscription"]) == 0
    assert int(by_description["Payroll"]["tax_deductible"]) == 1
    assert by_description["Payroll"]["payment_type"] == "ach"
    assert by_description["Payroll"]["note"] == "direct deposit"
    # Tax defaults to true for income when column value is blank.
    assert by_description["Bonus"]["account_type"] == "checking"
    assert int(by_description["Bonus"]["tax_deductible"]) == 1
    assert by_description["Bonus"]["payment_type"] in (None, "")
    assert by_description["Bonus"]["note"] in (None, "")


def test_xlsx_import_accepts_notes_header_alias(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "transactions_notes_alias.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/5/2026", 45.67, "Music plan", "Entertainment", "Credit Card", True, True, "usaa", "alias-note"),
        ],
        income_rows=[],
    )

    wb = openpyxl.load_workbook(workbook)
    ws = wb["Transactions"]
    ws["I2"] = "Notes"
    wb.save(workbook)

    result = importer.import_file(workbook)
    assert result.imported_count == 1

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT description, note
            FROM transactions
            WHERE source_system = 'xlsx_import'
            """
        ).fetchone()

    assert row is not None
    assert row["description"] == "Music plan"
    assert row["note"] == "alias-note"


def test_xlsx_import_accepts_payment_type_header_alias(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "transactions_payment_type_alias.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/5/2026", 45.67, "Music plan", "Entertainment", "Credit Card", True, True, "usaa", ""),
        ],
        income_rows=[
            ("2/7/2026", 1000.00, "Payroll", "Income", "checking", True, "ach", ""),
        ],
    )

    wb = openpyxl.load_workbook(workbook)
    ws = wb["Transactions"]
    ws["H2"] = "Payment Type"
    ws["Q2"] = "Payment Type"
    wb.save(workbook)

    importer.import_file(workbook)
    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT description, payment_type
            FROM transactions
            WHERE substr(txn_date, 1, 7) = '2026-02'
            ORDER BY txn_id
            """
        ).fetchall()

    by_description = {str(r["description"]): str(r["payment_type"] or "") for r in rows}
    assert by_description["Music plan"] == "usaa"
    assert by_description["Payroll"] == "ach"


def test_xlsx_import_does_not_create_new_categories_on_unmatched_names(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "transactions_unmatched_category.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/5/2026", 45.67, "Music plan", "Health/Medical"),
            ("2/6/2026", 20.00, "Coffee", ""),
        ],
        income_rows=[
            ("2/7/2026", 1000.00, "Payroll", "ERB"),
            ("2/8/2026", 200.00, "Bonus", ""),
        ],
    )

    with db.connection() as conn:
        before_categories = int(conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()["c"])

    result = importer.import_file(workbook)
    assert result.imported_count == 4

    with db.connection() as conn:
        after_categories = int(conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()["c"])
        rows = conn.execute(
            """
            SELECT description, category_id
            FROM transactions
            WHERE import_period_key = '2026-02'
            ORDER BY txn_date, txn_id
            """
        ).fetchall()

    assert after_categories == before_categories
    by_description = {str(row["description"]): row for row in rows}
    assert by_description["Music plan"]["category_id"] is None
    assert by_description["Coffee"]["category_id"] is None
    assert by_description["Payroll"]["category_id"] is None
    assert by_description["Bonus"]["category_id"] is None


def test_xlsx_import_maps_case_insensitive_to_existing_category(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    health_id = context.categories_repo.upsert("Health/medical", is_income=False)

    workbook = tmp_path / "transactions_case_category.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/5/2026", 45.67, "Clinic", "Health/Medical"),
        ],
        income_rows=[],
    )
    importer.import_file(workbook)

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT category_id
            FROM transactions
            WHERE description = 'Clinic'
            """
        ).fetchone()
        variants = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM categories
            WHERE lower(name) = lower('Health/medical')
            """
        ).fetchone()

    assert row is not None
    assert int(row["category_id"]) == health_id
    assert int(variants["c"]) == 1


def test_xlsx_import_transfer_rule_converts_budget_savings_to_transfer(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "transfers": {
            "rules": [
                {
                    "name": "Budget Savings to Savings",
                    "enabled": True,
                    "match_category": "Budget Savings",
                    "match_description": "Savings transfer",
                    "from_account_number": "1001",
                    "from_account_alias": "Checking",
                    "from_account_type": "checking",
                    "to_account_number": "2001",
                    "to_account_alias": "Savings",
                    "to_account_type": "savings",
                }
            ]
        },
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
        transfer_rules=settings["transfers"]["rules"],
    )
    budget_savings_category_id = context.categories_repo.upsert("Budget Savings", is_income=False)
    with db.connection() as conn:
        conn.execute("UPDATE accounts SET account_number = '1001' WHERE name = 'Checking'")
        conn.execute("UPDATE accounts SET account_number = '2001' WHERE name = 'Savings'")

    workbook = tmp_path / "transfer_rules.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/10/2026", 1100.00, "Savings transfer", "Budget Savings", "Credit Card", False, False, "ach", ""),
        ],
        income_rows=[],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 2
    assert result.deleted_count == 0
    assert result.import_period_key == "2026-02"
    assert result.transfer_rule_override_count == 1
    assert result.transfer_rule_override_examples

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.txn_type,
                t.amount_cents,
                t.category_id,
                t.source_system,
                t.source_uid,
                t.import_period_key,
                t.payment_type,
                a.name AS account_name
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            ORDER BY t.txn_id
            """
        ).fetchall()

    assert len(rows) == 2
    assert all(str(r["txn_type"]) == "transfer" for r in rows)
    assert sorted(int(r["amount_cents"]) for r in rows) == [-110000, 110000]
    assert all(int(r["category_id"]) == budget_savings_category_id for r in rows)
    assert int(rows[0]["category_id"]) == int(rows[1]["category_id"])
    assert all(str(r["source_system"]) == "xlsx_import" for r in rows)
    assert all(str(r["import_period_key"]) == "2026-02" for r in rows)
    assert all(str(r["payment_type"]).startswith("transfer-") for r in rows)
    assert str(rows[0]["source_uid"]).endswith(":out")
    assert str(rows[1]["source_uid"]).endswith(":in")
    assert {str(r["account_name"]) for r in rows} == {"Checking", "Savings"}


def test_xlsx_import_transfer_rule_requires_description_match(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "transfers": {
            "rules": [
                {
                    "name": "Budget Savings to Savings",
                    "enabled": True,
                    "match_category": "Budget Savings",
                    "match_description": "Edward Jones",
                    "from_account_number": "1001",
                    "from_account_alias": "Checking",
                    "from_account_type": "checking",
                    "to_account_number": "2001",
                    "to_account_alias": "Savings",
                    "to_account_type": "savings",
                }
            ]
        },
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
        transfer_rules=settings["transfers"]["rules"],
    )
    with db.connection() as conn:
        conn.execute("UPDATE accounts SET account_number = '1001' WHERE name = 'Checking'")
        conn.execute("UPDATE accounts SET account_number = '2001' WHERE name = 'Savings'")

    workbook = tmp_path / "transfer_rules_description_mismatch.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("2/10/2026", 1100.00, "Savings transfer", "Budget Savings", "checking", False, False, "ach", ""),
        ],
        income_rows=[],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 1
    assert result.deleted_count == 0

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT txn_type, amount_cents, payment_type
            FROM transactions
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert str(row["txn_type"]) == "expense"
    assert int(row["amount_cents"]) == -110000
    assert str(row["payment_type"]) == "ach"


def test_xlsx_import_replacement_preserves_manual_transfers(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "transfers": {
            "rules": [
                {
                    "name": "Budget Savings to Savings",
                    "enabled": True,
                    "match_category": "Budget Savings",
                    "match_description": "Savings transfer",
                    "from_account_number": "1001",
                    "from_account_alias": "Checking",
                    "from_account_type": "checking",
                    "to_account_number": "2001",
                    "to_account_alias": "Savings",
                    "to_account_type": "savings",
                }
            ]
        },
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
        transfer_rules=settings["transfers"]["rules"],
    )
    with db.connection() as conn:
        conn.execute("UPDATE accounts SET account_number = '1001' WHERE name = 'Checking'")
        conn.execute("UPDATE accounts SET account_number = '2001' WHERE name = 'Savings'")

    first_file = tmp_path / "first_rule_transfer.xlsx"
    _write_transactions_workbook(
        first_file,
        expense_rows=[
            ("2/10/2026", 1100.00, "Savings transfer", "Budget Savings", "Credit Card", False, False, "ach", ""),
        ],
        income_rows=[],
    )
    first_result = importer.import_file(first_file)
    assert first_result.imported_count == 2
    assert first_result.deleted_count == 0

    manual_group_id = context.transactions_service.add_transfer(
        TransferInput(
            txn_date="2026-02-12",
            amount_cents=2500,
            from_account_id=1,  # Checking
            to_account_id=2,  # Savings
            payee="Manual Transfer",
            description="Manual Transfer",
            source_system="manual",
            source_uid="manual:test-transfer",
            import_period_key="2026-02",
        )
    )
    assert manual_group_id

    second_file = tmp_path / "second_rule_transfer.xlsx"
    _write_transactions_workbook(
        second_file,
        expense_rows=[
            ("2/14/2026", 1200.00, "Savings transfer", "Budget Savings", "Credit Card", False, False, "ach", ""),
        ],
        income_rows=[],
    )
    second_result = importer.import_file(second_file)
    assert second_result.imported_count == 2
    assert second_result.deleted_count == 2

    with db.connection() as conn:
        summary = conn.execute(
            """
            SELECT source_system, txn_type, COUNT(*) AS c
            FROM transactions
            WHERE import_period_key = '2026-02'
            GROUP BY source_system, txn_type
            ORDER BY source_system, txn_type
            """
        ).fetchall()
        manual_rows = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM transactions
            WHERE transfer_group_id = ?
            """,
            (manual_group_id,),
        ).fetchone()
        new_rule_rows = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM transactions
            WHERE source_system = 'xlsx_import'
              AND txn_type = 'transfer'
            """
        ).fetchone()

    assert summary is not None
    assert int(manual_rows["c"]) == 2
    assert int(new_rule_rows["c"]) == 2


def test_xlsx_import_allows_zero_amount_placeholders(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
    )

    workbook = tmp_path / "zero_amount_placeholder.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("4/1/2026", 0.00, "Expected utility bill", "Utilities"),
        ],
        income_rows=[
            ("4/2/2026", 0.00, "Pending reimbursement", "Reimbursements"),
        ],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 2

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT description, txn_type, amount_cents
            FROM transactions
            ORDER BY txn_id
            """
        ).fetchall()

    assert len(rows) == 2
    assert str(rows[0]["description"]) == "Expected utility bill"
    assert str(rows[0]["txn_type"]) == "expense"
    assert int(rows[0]["amount_cents"]) == 0
    assert str(rows[1]["description"]) == "Pending reimbursement"
    assert str(rows[1]["txn_type"]) == "income"
    assert int(rows[1]["amount_cents"]) == 0


def test_xlsx_import_zero_amount_rule_match_keeps_placeholder_transaction(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": ""},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "transfers": {
            "rules": [
                {
                    "name": "Budget Savings to Savings",
                    "enabled": True,
                    "match_category": "Budget Savings",
                    "match_description": "Edward Jones",
                    "from_account_number": "1001",
                    "from_account_alias": "Checking",
                    "from_account_type": "checking",
                    "to_account_number": "2001",
                    "to_account_alias": "Savings",
                    "to_account_type": "savings",
                }
            ]
        },
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    importer = XLSXTransactionImporter(
        context.transactions_service,
        context.categories_repo,
        context.accounts_repo,
        transfer_rules=settings["transfers"]["rules"],
    )
    with db.connection() as conn:
        conn.execute("UPDATE accounts SET account_number = '1001' WHERE name = 'Checking'")
        conn.execute("UPDATE accounts SET account_number = '2001' WHERE name = 'Savings'")

    workbook = tmp_path / "zero_rule_match.xlsx"
    _write_transactions_workbook(
        workbook,
        expense_rows=[
            ("4/10/2026", 0.00, "Edward Jones", "Budget Savings", "checking", False, False, "ach", ""),
        ],
        income_rows=[],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 1

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT txn_type, amount_cents, transfer_group_id, source_system
            FROM transactions
            ORDER BY txn_id
            """
        ).fetchall()

    assert len(rows) == 1
    assert str(rows[0]["txn_type"]) == "expense"
    assert int(rows[0]["amount_cents"]) == 0
    assert rows[0]["transfer_group_id"] is None
    assert str(rows[0]["source_system"]) == "xlsx_import"
