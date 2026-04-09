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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table,),
    ).fetchone()
    return row is not None


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


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "transactions", "import_period_key"):
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN import_period_key TEXT NULL"
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_txn_import_period_key
        ON transactions(import_period_key)
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("5",),
    )
    conn.execute("PRAGMA user_version = 5")


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "transactions", "payment_type"):
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN payment_type TEXT NULL"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("6",),
    )
    conn.execute("PRAGMA user_version = 6")


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    has_old = _column_exists(conn, "transactions", "is_reconciled")
    has_new = _column_exists(conn, "transactions", "is_cleared")
    if has_old and not has_new:
        conn.execute(
            "ALTER TABLE transactions "
            "RENAME COLUMN is_reconciled TO is_cleared"
        )
    elif not has_new:
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN is_cleared INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("7",),
    )
    conn.execute("PRAGMA user_version = 7")


def _migrate_v7_to_v8(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "bills"):
        if not _column_exists(conn, "bills", "start_date"):
            conn.execute(
                "ALTER TABLE bills "
                "ADD COLUMN start_date TEXT NULL"
            )
        if not _column_exists(conn, "bills", "interval_count"):
            conn.execute(
                "ALTER TABLE bills "
                "ADD COLUMN interval_count INTEGER NOT NULL DEFAULT 1"
            )
        if not _column_exists(conn, "bills", "interval_unit"):
            conn.execute(
                "ALTER TABLE bills "
                "ADD COLUMN interval_unit TEXT NOT NULL DEFAULT 'months'"
            )

        conn.execute(
            """
            UPDATE bills
            SET interval_count = CASE
                WHEN interval_count IS NULL OR interval_count < 1 THEN 1
                ELSE interval_count
            END
            """
        )
        conn.execute(
            """
            UPDATE bills
            SET interval_unit = CASE
                WHEN interval_unit IS NULL OR trim(interval_unit) = '' THEN 'months'
                ELSE lower(trim(interval_unit))
            END
            """
        )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("8",),
    )
    conn.execute("PRAGMA user_version = 8")


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
        elif current_version == 4:
            _migrate_v4_to_v5(conn)
        elif current_version == 5:
            _migrate_v5_to_v6(conn)
        elif current_version == 6:
            _migrate_v6_to_v7(conn)
        elif current_version == 7:
            _migrate_v7_to_v8(conn)
        else:
            raise RuntimeError(
                "Unsupported migration path. "
                f"Found user_version={current_version}; expected {SCHEMA_VERSION}."
            )
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
