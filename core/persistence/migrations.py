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

    if current_version < SCHEMA_VERSION:
        raise RuntimeError(
            "Automatic migrations for older schema versions are not yet implemented. "
            f"Found user_version={current_version}; expected {SCHEMA_VERSION}."
        )
