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
