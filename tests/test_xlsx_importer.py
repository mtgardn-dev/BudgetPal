from __future__ import annotations

import pytest

from core.app_context import BudgetPalContext
from core.domain import TransactionInput
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

    ws["I1"] = "Income"
    ws["I2"] = "Date"
    ws["J2"] = "Amount"
    ws["K2"] = "Description"
    ws["L2"] = "Category"
    ws["M2"] = "Account"
    ws["N2"] = "Tax"

    row = 3
    for rec in expense_rows:
        date_value, amount_value, description, category = rec[:4]
        account = rec[4] if len(rec) >= 5 else ""
        subscription = rec[5] if len(rec) >= 6 else ""
        tax = rec[6] if len(rec) >= 7 else ""
        ws.cell(row=row, column=1, value=date_value)
        ws.cell(row=row, column=2, value=amount_value)
        ws.cell(row=row, column=3, value=description)
        ws.cell(row=row, column=4, value=category)
        ws.cell(row=row, column=5, value=account)
        ws.cell(row=row, column=6, value=subscription)
        ws.cell(row=row, column=7, value=tax)
        row += 1

    row = 3
    for rec in income_rows:
        date_value, amount_value, description, category = rec[:4]
        account = rec[4] if len(rec) >= 5 else ""
        tax = rec[5] if len(rec) >= 6 else ""
        ws.cell(row=row, column=9, value=date_value)
        ws.cell(row=row, column=10, value=amount_value)
        ws.cell(row=row, column=11, value=description)
        ws.cell(row=row, column=12, value=category)
        ws.cell(row=row, column=13, value=account)
        ws.cell(row=row, column=14, value=tax)
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


def test_xlsx_import_raises_for_multiple_months(tmp_path) -> None:
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

    with pytest.raises(ValueError, match="exactly one month of data"):
        importer.import_file(mixed_month_file)


def test_xlsx_import_replaces_all_month_rows_not_only_imported_source(tmp_path) -> None:
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
            SELECT source_system, description
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
    assert all(r["source_system"] == "xlsx_import" for r in month_rows)


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
            ("2/5/2026", 45.67, "Music plan", "Entertainment", "credit", True, True),
            ("2/6/2026", 20.00, "Coffee", "Misc", "cash", False, False),
        ],
        income_rows=[
            ("2/7/2026", 1000.00, "Payroll", "Income", "checking", True),
            ("2/8/2026", 200.00, "Bonus", "Income", "", ""),
        ],
    )

    result = importer.import_file(workbook)
    assert result.imported_count == 4

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT t.description, t.txn_type, t.is_subscription, t.tax_deductible, a.account_type
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
    assert by_description["Coffee"]["account_type"] == "cash"
    assert int(by_description["Coffee"]["is_subscription"]) == 0
    assert int(by_description["Coffee"]["tax_deductible"]) == 0
    assert by_description["Payroll"]["account_type"] == "checking"
    assert int(by_description["Payroll"]["is_subscription"]) == 0
    assert int(by_description["Payroll"]["tax_deductible"]) == 1
    # Default account/tax for income when column values are blank.
    assert by_description["Bonus"]["account_type"] == "checking"
    assert int(by_description["Bonus"]["tax_deductible"]) == 1
