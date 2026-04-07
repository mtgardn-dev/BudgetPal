from __future__ import annotations

import sqlite3
from datetime import date

from core.persistence.schema import (
    INITIAL_SCHEMA_SQL,
    SCHEMA_VERSION,
    SEEDED_ACCOUNT_ROWS,
    SEEDED_CATEGORY_ROWS,
    SEEDED_TAX_CATEGORIES,
)


def _apply_initial_schema(conn: sqlite3.Connection) -> None:
    for stmt in INITIAL_SCHEMA_SQL:
        conn.execute(stmt)

    for tax_name in SEEDED_TAX_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO tax_categories(name, is_active) VALUES (?, 1)",
            (tax_name,),
        )

    for name, is_income in SEEDED_CATEGORY_ROWS:
        conn.execute(
            """
            INSERT OR IGNORE INTO categories(name, is_income, is_active)
            VALUES (?, ?, 1)
            """,
            (name, is_income),
        )

    for account_name, account_type in SEEDED_ACCOUNT_ROWS:
        conn.execute(
            """
            INSERT OR IGNORE INTO accounts(name, account_type, opening_balance_cents, is_active)
            VALUES (?, ?, 0, 1)
            """,
            (account_name, account_type),
        )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO app_meta(key, value) VALUES ('created_on', ?)",
        (date.today().isoformat(),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO app_meta(key, value) VALUES ('app_name', 'BudgetPal')"
    )


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "transactions", "is_subscription"):
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN is_subscription INTEGER NOT NULL DEFAULT 0"
        )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("2",),
    )
    conn.execute("PRAGMA user_version = 2")


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sub_payment_mappings (
            txn_id INTEGER PRIMARY KEY,
            sub_id INTEGER NULL,
            external_source TEXT NOT NULL DEFAULT 'budgetpal',
            external_txn_key TEXT NULL,
            last_post_status TEXT NOT NULL DEFAULT 'unposted'
                CHECK (last_post_status IN ('unposted', 'posted', 'error')),
            subtracker_payment_id INTEGER NULL,
            last_error TEXT NULL,
            last_posted_at TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(txn_id) REFERENCES transactions(txn_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_payment_mappings_sub_id
        ON sub_payment_mappings(sub_id)
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("3",),
    )
    conn.execute("PRAGMA user_version = 3")


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "sub_payment_mappings", "override_amount_cents"):
        conn.execute(
            "ALTER TABLE sub_payment_mappings "
            "ADD COLUMN override_amount_cents INTEGER NULL"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("4",),
    )
    conn.execute("PRAGMA user_version = 4")


def apply_migrations(conn: sqlite3.Connection) -> None:
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version == 0:
        _apply_initial_schema(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        return

    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            "Database schema is newer than this BudgetPal build supports. "
            f"Database user_version={current_version}, app supports up to {SCHEMA_VERSION}."
        )

    while current_version < SCHEMA_VERSION:
        if current_version == 1:
            _migrate_v1_to_v2(conn)
        elif current_version == 2:
            _migrate_v2_to_v3(conn)
        elif current_version == 3:
            _migrate_v3_to_v4(conn)
        else:
            raise RuntimeError(
                "Unsupported migration path. "
                f"Found user_version={current_version}; expected {SCHEMA_VERSION}."
            )
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
