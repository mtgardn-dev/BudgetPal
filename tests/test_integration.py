from __future__ import annotations

import sqlite3

import pytest

from core.app_context import BudgetPalContext
from core.importers.subtracker_view import (
    SubTrackerIntegrationError,
    SubTrackerViewImporter,
)
from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.budgets_repo import BudgetsRepository
from core.persistence.schema import SCHEMA_VERSION


def test_schema_bootstraps_seeded_tax_categories(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    with db.connection() as conn:
        rows = conn.execute("SELECT name FROM tax_categories ORDER BY name").fetchall()
    names = [r["name"] for r in rows]
    assert "Charity" in names
    assert "Medical" in names


def test_budget_month_copy_previous(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    repo = BudgetsRepository(db)

    feb_id = repo.ensure_month(2026, 2, starting_balance_cents=100000)
    repo.set_budget_line(feb_id, category_id=2, planned_cents=200000)
    repo.set_budget_line(feb_id, category_id=3, planned_cents=30000)

    mar_id = repo.ensure_month(2026, 3, starting_balance_cents=120000)
    repo.copy_from_previous_month(2026, 3)

    with db.connection() as conn:
        lines = conn.execute(
            """
            SELECT category_id, planned_cents
            FROM budget_lines
            WHERE budget_month_id = ?
            ORDER BY category_id
            """,
            (mar_id,),
        ).fetchall()

    assert [(row["category_id"], row["planned_cents"]) for row in lines] == [(2, 200000), (3, 30000)]


def test_subtracker_importer_requires_contract(tmp_path) -> None:
    sub_db = tmp_path / "subtracker.db"
    conn = sqlite3.connect(sub_db)
    conn.execute("CREATE TABLE subscriptions(id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    importer = SubTrackerViewImporter(sub_db)
    with pytest.raises(SubTrackerIntegrationError):
        importer.load_active_subscriptions()


def test_subtracker_importer_loads_view_rows(tmp_path) -> None:
    sub_db = tmp_path / "subtracker.db"
    conn = sqlite3.connect(sub_db)
    conn.execute("CREATE TABLE subscriptions (subscription_id INTEGER PRIMARY KEY, vendor TEXT, next_renewal_date TEXT, renewal_amount_cents INTEGER, billing_frequency TEXT, category_name TEXT, autopay_flag INTEGER, is_active INTEGER)")
    conn.execute("CREATE TABLE subtracker_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '2')")
    conn.execute("INSERT INTO subscriptions(subscription_id, vendor, next_renewal_date, renewal_amount_cents, billing_frequency, category_name, autopay_flag, is_active) VALUES (1, 'Netflix', '2026-03-15', 1999, 'monthly', 'Media', 1, 1)")
    conn.execute(
        """
        CREATE VIEW v_budgetpal_subscriptions AS
        SELECT
          subscription_id AS sub_id,
          vendor AS vendor,
          next_renewal_date AS renewal_date,
          renewal_amount_cents AS amount_cents,
          billing_frequency AS frequency,
          category_name AS category,
          2 AS budgetpal_category_id,
          autopay_flag AS autopay,
          is_active AS active
        FROM subscriptions
        WHERE is_active = 1
        """
    )
    conn.commit()
    conn.close()

    importer = SubTrackerViewImporter(sub_db)
    rows = importer.load_active_subscriptions()
    assert len(rows) == 1
    assert rows[0]["vendor"] == "Netflix"
    assert rows[0]["amount_cents"] == 1999


def test_subtracker_refresh_maps_category_and_filters_to_selected_month(tmp_path) -> None:
    sub_db = tmp_path / "subtracker_refresh.db"
    conn = sqlite3.connect(sub_db)
    conn.execute(
        """
        CREATE TABLE subscriptions (
            subscription_id INTEGER PRIMARY KEY,
            vendor TEXT NOT NULL,
            next_renewal_date TEXT NOT NULL,
            renewal_amount_cents INTEGER NOT NULL,
            billing_frequency TEXT NOT NULL,
            category_name TEXT,
            autopay_flag INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("CREATE TABLE subtracker_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '2')"
    )
    conn.execute(
        """
        CREATE VIEW v_budgetpal_subscriptions AS
        SELECT
          subscription_id AS sub_id,
          vendor AS vendor,
          next_renewal_date AS renewal_date,
          renewal_amount_cents AS amount_cents,
          billing_frequency AS frequency,
          category_name AS category,
          CASE
            WHEN subscription_id IN (1, 3) THEN 2
            ELSE 99999
          END AS budgetpal_category_id,
          autopay_flag AS autopay,
          is_active AS active
        FROM subscriptions
        WHERE is_active = 1
        """
    )
    conn.execute(
        """
        INSERT INTO subscriptions(
            subscription_id, vendor, next_renewal_date, renewal_amount_cents, billing_frequency, category_name, autopay_flag, is_active
        ) VALUES
            (1, 'Known April', '2026-04-15', 1200, 'monthly', 'Housing', 1, 1),
            (2, 'Unknown April', '2026-04-20', 3400, 'monthly', 'NotInBudgetPal', 0, 1),
            (3, 'Known May', '2026-05-01', 5600, 'monthly', 'Housing', 1, 1)
        """
    )
    conn.commit()
    conn.close()

    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": str(sub_db)},
        "logging": {"level": "INFO", "max_bytes": 1_000_000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)

    assert context.subscriptions_service is not None
    refreshed = context.subscriptions_service.refresh_subtracker_bills(year=2026, month=4)
    assert refreshed == 2
    errors = context.subscriptions_service.last_mapping_errors
    assert any("99999" in str(msg) for msg in errors)

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT b.name, c.name AS category_name, b.start_date
            FROM bills b
            LEFT JOIN categories c ON c.category_id = b.category_id
            WHERE b.source_system = 'subtracker'
            ORDER BY b.name ASC
            """
        ).fetchall()

    assert len(rows) == 2
    by_name = {str(r["name"]): str(r["category_name"]) for r in rows}
    assert by_name["Known April"] == "Housing"
    assert by_name["Unknown April"] == "Uncategorized"


def test_subtracker_refresh_backfills_existing_bill_category_for_other_month(tmp_path) -> None:
    sub_db = tmp_path / "subtracker_backfill.db"
    conn = sqlite3.connect(sub_db)
    conn.execute(
        """
        CREATE TABLE subscriptions (
            subscription_id INTEGER PRIMARY KEY,
            vendor TEXT NOT NULL,
            next_renewal_date TEXT NOT NULL,
            renewal_amount_cents INTEGER NOT NULL,
            billing_frequency TEXT NOT NULL,
            category_name TEXT,
            autopay_flag INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("CREATE TABLE subtracker_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '2')"
    )
    conn.execute(
        """
        CREATE VIEW v_budgetpal_subscriptions AS
        SELECT
          subscription_id AS sub_id,
          vendor AS vendor,
          next_renewal_date AS renewal_date,
          renewal_amount_cents AS amount_cents,
          billing_frequency AS frequency,
          category_name AS category,
          CASE
            WHEN subscription_id = 1 THEN 2
            ELSE NULL
          END AS budgetpal_category_id,
          autopay_flag AS autopay,
          is_active AS active
        FROM subscriptions
        WHERE is_active = 1
        """
    )
    conn.execute(
        """
        INSERT INTO subscriptions(
            subscription_id, vendor, next_renewal_date, renewal_amount_cents, billing_frequency, category_name, autopay_flag, is_active
        ) VALUES
            (1, 'April Match', '2026-04-15', 1200, 'monthly', 'Housing', 1, 1),
            (2, 'May Existing', '2026-05-15', 3400, 'monthly', 'Software', 1, 1)
        """
    )
    conn.commit()
    conn.close()

    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    settings = {
        "database": {"path": str(tmp_path / "budgetpal.db")},
        "subtracker": {"database_path": str(sub_db)},
        "logging": {"level": "INFO", "max_bytes": 1_000_000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(db=db, settings=settings)
    assert context.subscriptions_service is not None
    software_category_id = context.categories_repo.upsert("Software", is_income=False)
    conn = sqlite3.connect(sub_db)
    conn.execute(
        "UPDATE subscriptions SET category_name='Software' WHERE subscription_id = 2"
    )
    conn.execute("DROP VIEW v_budgetpal_subscriptions")
    conn.execute(
        f"""
        CREATE VIEW v_budgetpal_subscriptions AS
        SELECT
          subscription_id AS sub_id,
          vendor AS vendor,
          next_renewal_date AS renewal_date,
          renewal_amount_cents AS amount_cents,
          billing_frequency AS frequency,
          category_name AS category,
          CASE
            WHEN subscription_id = 1 THEN 2
            WHEN subscription_id = 2 THEN {int(software_category_id)}
            ELSE NULL
          END AS budgetpal_category_id,
          autopay_flag AS autopay,
          is_active AS active
        FROM subscriptions
        WHERE is_active = 1
        """
    )
    conn.commit()
    conn.close()

    # Seed an old row (simulates pre-fix uncategorized import).
    context.bills_repo.upsert_bill(
        name="May Existing",
        frequency="monthly",
        due_day=15,
        default_amount_cents=3400,
        category_id=None,
        source_system="subtracker",
        source_uid="2",
        notes="Imported from SubTracker",
        start_date="2026-05-15",
        interval_count=1,
        interval_unit="months",
    )

    # Refresh April only; should still backfill existing May category.
    context.subscriptions_service.refresh_subtracker_bills(year=2026, month=4)

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT c.name AS category_name
            FROM bills b
            LEFT JOIN categories c ON c.category_id = b.category_id
            WHERE b.source_system = 'subtracker' AND b.source_uid = '2'
            """
        ).fetchone()

    assert row is not None
    assert str(row["category_name"]) == "Software"


def test_migration_v1_to_v16_adds_institutions_richer_accounts_and_checking_tables(tmp_path) -> None:
    db_path = tmp_path / "budgetpal_v1.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO app_meta(key, value) VALUES ('schema_version', '1')")
    conn.execute(
        """
        CREATE TABLE transactions (
            txn_id INTEGER PRIMARY KEY,
            txn_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            txn_type TEXT NOT NULL,
            payee TEXT NOT NULL,
            description TEXT NULL,
            category_id INTEGER NULL,
            account_id INTEGER NOT NULL,
            note TEXT NULL,
            source_system TEXT NULL,
            source_uid TEXT NULL,
            import_hash TEXT NULL,
            is_cleared INTEGER NOT NULL DEFAULT 0,
            tax_deductible INTEGER NOT NULL DEFAULT 0,
            tax_category TEXT NULL,
            tax_year INTEGER NULL,
            tax_note TEXT NULL,
            receipt_uri TEXT NULL,
            transfer_group_id TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()

    BudgetPalDatabase(db_path)

    conn = sqlite3.connect(db_path)
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
    mapping_columns = conn.execute("PRAGMA table_info(sub_payment_mappings)").fetchall()
    mapping_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sub_payment_mappings'"
    ).fetchone()
    income_definitions_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='income_definitions'"
    ).fetchone()
    income_occurrences_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='income_occurrences'"
    ).fetchone()
    budget_category_definitions_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_category_definitions'"
    ).fetchone()
    institutions_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='institutions'"
    ).fetchone()
    accounts_columns = conn.execute("PRAGMA table_info(accounts)").fetchall()
    account_month_settings_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='account_month_settings'"
    ).fetchone()
    account_month_columns = conn.execute("PRAGMA table_info(account_month_settings)").fetchall()
    budget_lines_columns = conn.execute("PRAGMA table_info(budget_lines)").fetchall()
    conn.close()

    names = [row[1] for row in columns]
    assert user_version == SCHEMA_VERSION
    assert "is_subscription" in names
    assert "import_period_key" in names
    assert "payment_type" in names
    assert "is_cleared" in names
    assert "is_reconciled" not in names
    assert mapping_table is not None
    assert income_definitions_table is not None
    assert income_occurrences_table is not None
    assert budget_category_definitions_table is not None
    assert institutions_table is not None
    assert account_month_settings_table is not None
    assert "institution_id" in [row[1] for row in accounts_columns]
    assert "account_number_mask" not in [row[1] for row in accounts_columns]
    assert "account_number" in [row[1] for row in accounts_columns]
    assert "balance_cents" not in [row[1] for row in accounts_columns]
    assert "notes" in [row[1] for row in accounts_columns]
    assert "cd_start_date" in [row[1] for row in accounts_columns]
    assert "cd_interval_count" in [row[1] for row in accounts_columns]
    assert "cd_interval_unit" in [row[1] for row in accounts_columns]
    assert "cd_interest_rate_bps" in [row[1] for row in accounts_columns]
    assert "is_external" in [row[1] for row in accounts_columns]
    assert "show_on_accounts_tab" in [row[1] for row in accounts_columns]
    assert "account_id" in [row[1] for row in account_month_columns]
    assert "statement_ending_balance_cents" in [row[1] for row in account_month_columns]
    assert "statement_ending_date" in [row[1] for row in account_month_columns]
    assert "note" in [row[1] for row in budget_lines_columns]
    assert "override_amount_cents" in [row[1] for row in mapping_columns]


def test_subtracker_payment_upsert_is_idempotent_and_updates_existing(tmp_path) -> None:
    sub_db = tmp_path / "subtracker_payments.db"
    conn = sqlite3.connect(sub_db)
    conn.execute(
        """
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            start_date TEXT NOT NULL,
            interval_type TEXT NOT NULL,
            interval_value INTEGER NOT NULL,
            cost REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE subscription_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            remarks TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE subtracker_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '2')")
    conn.execute(
        """
        INSERT INTO subscriptions(id, name, category, start_date, interval_type, interval_value, cost)
        VALUES (1, 'Netflix', 'Media', '2026-01-01', 'months', 1, 19.99),
               (2, 'Apple', 'Software', '2026-01-01', 'months', 1, 0.99)
        """
    )
    conn.execute(
        """
        CREATE VIEW v_budgetpal_subscriptions AS
        SELECT
          id AS sub_id,
          name AS vendor,
          start_date AS renewal_date,
          CAST(ROUND(cost * 100) AS INTEGER) AS amount_cents,
          'monthly' AS frequency,
          category AS category,
          NULL AS budgetpal_category_id,
          0 AS autopay,
          1 AS active
        FROM subscriptions
        """
    )
    conn.commit()
    conn.close()

    importer = SubTrackerViewImporter(sub_db)
    first = importer.upsert_subscription_payment(
        external_source="budgetpal",
        external_txn_key="budgetpal:txn:123",
        subscription_id=1,
        payment_date="2026-02-28",
        amount_cents=1999,
        remarks="checking",
    )
    second = importer.upsert_subscription_payment(
        external_source="budgetpal",
        external_txn_key="budgetpal:txn:123",
        subscription_id=2,
        payment_date="2026-02-28",
        amount_cents=99,
        remarks="credit",
    )

    conn = sqlite3.connect(sub_db)
    ingest_rows = conn.execute(
        """
        SELECT subscription_id, amount_cents, remarks, applied_payment_id
        FROM budgetpal_payment_ingest
        WHERE external_source='budgetpal' AND external_txn_key='budgetpal:txn:123'
        """
    ).fetchall()
    payment_rows = conn.execute(
        "SELECT id, subscription_id, amount, remarks FROM subscription_payments ORDER BY id"
    ).fetchall()
    conn.close()

    assert first["created"] is True
    assert second["created"] is False
    assert len(ingest_rows) == 1
    assert len(payment_rows) == 1
    assert int(ingest_rows[0][0]) == 2
    assert int(ingest_rows[0][1]) == 99
    assert str(ingest_rows[0][2]) == "credit"
    assert int(payment_rows[0][1]) == 2
    assert float(payment_rows[0][2]) == pytest.approx(0.99)
    assert str(payment_rows[0][3]) == "credit"


def test_migration_v6_to_v16_renames_is_reconciled_to_is_cleared(tmp_path) -> None:
    db_path = tmp_path / "budgetpal_v6.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 6")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO app_meta(key, value) VALUES ('schema_version', '6')")
    conn.execute(
        """
        CREATE TABLE transactions (
            txn_id INTEGER PRIMARY KEY,
            txn_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            txn_type TEXT NOT NULL,
            payee TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            source_uid TEXT NULL,
            is_reconciled INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO transactions(txn_id, txn_date, amount_cents, txn_type, payee, account_id, source_uid, is_reconciled)
        VALUES (1, '2026-02-01', -1000, 'expense', 'Test', 1, 'manual:1', 1)
        """
    )
    conn.commit()
    conn.close()

    BudgetPalDatabase(db_path)

    conn = sqlite3.connect(db_path)
    columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    row = conn.execute("SELECT is_cleared FROM transactions WHERE txn_id = 1").fetchone()
    conn.close()

    names = [row[1] for row in columns]
    assert user_version == SCHEMA_VERSION
    assert "is_cleared" in names
    assert "is_reconciled" not in names
    assert int(row[0]) == 1


def test_migration_v15_to_v16_removes_legacy_tables_and_columns(tmp_path) -> None:
    db_path = tmp_path / "budgetpal_v15.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA user_version = 15")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO app_meta(key, value) VALUES ('schema_version', '15')")
    conn.execute(
        """
        CREATE TABLE categories (
            category_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            parent_category_id INTEGER NULL,
            is_income INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE institutions (
            institution_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("INSERT INTO institutions(institution_id, name, is_active) VALUES (1, 'Default Institution', 1)")
    conn.execute(
        """
        CREATE TABLE accounts (
            account_id INTEGER PRIMARY KEY,
            institution_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            opening_balance_cents INTEGER NOT NULL DEFAULT 0,
            account_number_mask TEXT NULL,
            account_number TEXT NULL,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            notes TEXT NULL,
            cd_start_date TEXT NULL,
            cd_interval_count INTEGER NULL,
            cd_interval_unit TEXT NULL,
            cd_interest_rate_bps INTEGER NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO accounts(
            account_id, institution_id, name, account_type, opening_balance_cents,
            account_number_mask, account_number, balance_cents, notes, is_active
        ) VALUES (1, 1, 'Checking', 'checking', 0, 'xxx1234', 'xxx1234', 0, NULL, 1)
        """
    )
    conn.execute(
        """
        CREATE TABLE transactions (
            txn_id INTEGER PRIMARY KEY,
            txn_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            txn_type TEXT NOT NULL,
            payee TEXT NOT NULL,
            category_id INTEGER NULL,
            account_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE transaction_splits (
            split_id INTEGER PRIMARY KEY,
            txn_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE bills_month_settings (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            auto_refresh_enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(year, month)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE savings_buckets (
            bucket_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            target_cents INTEGER NULL,
            target_date TEXT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE bucket_movements (
            movement_id INTEGER PRIMARY KEY,
            bucket_id INTEGER NOT NULL,
            movement_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    BudgetPalDatabase(db_path)

    conn = sqlite3.connect(db_path)
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    categories_cols = [row[1] for row in conn.execute("PRAGMA table_info(categories)").fetchall()]
    accounts_cols = [row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    has_splits = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transaction_splits'"
    ).fetchone()
    has_month_settings = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bills_month_settings'"
    ).fetchone()
    has_buckets = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='savings_buckets'"
    ).fetchone()
    has_bucket_moves = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bucket_movements'"
    ).fetchone()
    conn.close()

    assert user_version == SCHEMA_VERSION
    assert "parent_category_id" not in categories_cols
    assert "account_number_mask" not in accounts_cols
    assert "balance_cents" not in accounts_cols
    assert "show_on_accounts_tab" in accounts_cols
    assert has_splits is None
    assert has_month_settings is None
    assert has_buckets is None
    assert has_bucket_moves is None
