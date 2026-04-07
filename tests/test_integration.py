from __future__ import annotations

import sqlite3

import pytest

from core.importers.subtracker_view import (
    SubTrackerIntegrationError,
    SubTrackerViewImporter,
)
from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.budgets_repo import BudgetsRepository


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
    conn.execute("INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '1')")
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


def test_migration_v1_to_v4_adds_subscription_and_sub_payment_mappings(tmp_path) -> None:
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
            is_reconciled INTEGER NOT NULL DEFAULT 0,
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
    conn.close()

    names = [row[1] for row in columns]
    assert user_version == 4
    assert "is_subscription" in names
    assert mapping_table is not None
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
    conn.execute("INSERT INTO subtracker_meta(key, value) VALUES ('budgetpal_view_version', '1')")
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
