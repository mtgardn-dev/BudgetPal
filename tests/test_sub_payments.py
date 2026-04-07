from __future__ import annotations

import sqlite3

import pytest

from core.app_context import BudgetPalContext
from core.domain import TransactionInput
from core.persistence.db import BudgetPalDatabase


def _create_subtracker_db(path) -> None:
    conn = sqlite3.connect(path)
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
        VALUES
            (1, 'Netflix', 'Media', '2026-01-01', 'months', 1, 19.99),
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


def test_sub_payment_service_posts_and_supports_corrections(tmp_path) -> None:
    budgetpal_db_path = tmp_path / "budgetpal.db"
    subtracker_db_path = tmp_path / "subtracker.db"
    _create_subtracker_db(subtracker_db_path)

    settings = {
        "database": {"path": str(budgetpal_db_path)},
        "subtracker": {"database_path": str(subtracker_db_path)},
        "logging": {"level": "INFO", "max_bytes": 1000000, "backup_count": 5},
        "ui": {"window": {"width": 1000, "height": 700}},
    }
    context = BudgetPalContext(
        db=BudgetPalDatabase(budgetpal_db_path),
        settings=settings,
    )

    checking = context.accounts_repo.find_by_name("Checking")
    misc = context.categories_repo.find_by_name("Misc")
    assert checking is not None
    assert misc is not None

    txn_id = context.transactions_service.add_transaction(
        TransactionInput(
            txn_date="2026-02-20",
            amount_cents=-1999,
            txn_type="expense",
            payee="Netflix",
            description="Netflix monthly",
            category_id=int(misc["category_id"]),
            account_id=int(checking["account_id"]),
            source_system="manual",
            source_uid="manual:netflix",
            is_subscription=True,
            tax_deductible=False,
        )
    )

    service = context.subscription_payments_service
    assert service is not None

    payload = service.load_month_candidates(2026, 2)
    candidates = payload["candidates"]
    assert len(candidates) == 1
    assert int(candidates[0]["txn_id"]) == txn_id
    assert int(candidates[0]["selected_sub_id"]) == 1

    first = service.process_month(
        2026,
        2,
        {
            txn_id: {
                "sub_id": 1,
                "amount_cents": 1999,
            }
        },
    )
    assert first["posted_count"] == 1
    assert first["updated_count"] == 0
    assert first["error_count"] == 0

    second = service.process_month(
        2026,
        2,
        {
            txn_id: {
                "sub_id": 2,
                "amount_cents": 2500,
            }
        },
    )
    assert second["posted_count"] == 0
    assert second["updated_count"] == 1
    assert second["error_count"] == 0

    payload_after = service.load_month_candidates(2026, 2)
    assert int(payload_after["candidates"][0]["display_amount_cents"]) == 2500

    conn = sqlite3.connect(subtracker_db_path)
    payments = conn.execute(
        "SELECT subscription_id, payment_date, amount, remarks FROM subscription_payments"
    ).fetchall()
    ingest = conn.execute(
        """
        SELECT subscription_id, amount_cents, remarks
        FROM budgetpal_payment_ingest
        WHERE external_source='budgetpal' AND external_txn_key='budgetpal:manual:netflix'
        """
    ).fetchone()
    conn.close()

    assert len(payments) == 1
    assert int(payments[0][0]) == 2
    assert str(payments[0][1]) == "2026-02-20"
    assert float(payments[0][2]) == pytest.approx(25.00)
    assert str(payments[0][3]) == "Checking"
    assert ingest is not None
    assert int(ingest[0]) == 2
    assert int(ingest[1]) == 2500
