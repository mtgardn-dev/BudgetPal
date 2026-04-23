from __future__ import annotations

import sqlite3
from datetime import date

from core.persistence.schema import (
    INITIAL_SCHEMA_SQL,
    SCHEMA_VERSION,
    SEEDED_ACCOUNT_ROWS,
    SEEDED_CATEGORY_ROWS,
    SEEDED_INSTITUTION_ROWS,
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

    for (institution_name,) in SEEDED_INSTITUTION_ROWS:
        conn.execute(
            """
            INSERT OR IGNORE INTO institutions(name, is_active)
            VALUES (?, 1)
            """,
            (institution_name,),
        )
    default_institution = conn.execute(
        """
        SELECT institution_id
        FROM institutions
        WHERE lower(trim(name)) = 'default institution'
        LIMIT 1
        """
    ).fetchone()
    if default_institution is None:
        raise RuntimeError("Failed to seed default institution.")
    default_institution_id = int(default_institution["institution_id"])

    for account_name, account_type in SEEDED_ACCOUNT_ROWS:
        conn.execute(
            """
            INSERT OR IGNORE INTO accounts(
                institution_id,
                name,
                account_type,
                opening_balance_cents,
                account_number,
                notes,
                cd_start_date,
                cd_interval_count,
                cd_interval_unit,
                cd_interest_rate_bps,
                is_external,
                is_active
            )
            VALUES (?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL, NULL, 0, 1)
            """,
            (default_institution_id, account_name, account_type),
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


def _migrate_v8_to_v9(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bills_month_settings (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            auto_refresh_enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(year, month)
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("9",),
    )
    conn.execute("PRAGMA user_version = 9")


def _migrate_v9_to_v10(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_definitions (
            income_id INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            default_amount_cents INTEGER NULL,
            category_id INTEGER NULL,
            account_id INTEGER NOT NULL,
            start_date TEXT NULL,
            interval_count INTEGER NOT NULL DEFAULT 1,
            interval_unit TEXT NOT NULL DEFAULT 'months',
            source_system TEXT NOT NULL DEFAULT 'budgetpal',
            is_active INTEGER NOT NULL DEFAULT 1,
            notes TEXT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(category_id),
            FOREIGN KEY(account_id) REFERENCES accounts(account_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_income_definitions_source
        ON income_definitions(source_system)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_occurrences (
            income_occurrence_id INTEGER PRIMARY KEY,
            income_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            expected_date TEXT NULL,
            expected_amount_cents INTEGER NULL,
            status TEXT NOT NULL DEFAULT 'expected'
                CHECK (status IN ('expected', 'adjusted')),
            note TEXT NULL,
            UNIQUE(income_id, year, month),
            FOREIGN KEY(income_id) REFERENCES income_definitions(income_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("10",),
    )
    conn.execute("PRAGMA user_version = 10")


def _migrate_v10_to_v11(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_months (
            budget_month_id INTEGER PRIMARY KEY,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            starting_balance_cents INTEGER NOT NULL DEFAULT 0,
            notes TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(year, month)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_lines (
            budget_line_id INTEGER PRIMARY KEY,
            budget_month_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            planned_cents INTEGER NOT NULL DEFAULT 0,
            note TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(budget_month_id, category_id),
            FOREIGN KEY(budget_month_id) REFERENCES budget_months(budget_month_id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(category_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_category_definitions (
            definition_id INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL UNIQUE,
            default_amount_cents INTEGER NOT NULL DEFAULT 0,
            note TEXT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(category_id) REFERENCES categories(category_id)
        )
        """
    )
    if _table_exists(conn, "budget_lines") and not _column_exists(conn, "budget_lines", "note"):
        conn.execute(
            "ALTER TABLE budget_lines ADD COLUMN note TEXT NULL"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("11",),
    )
    conn.execute("PRAGMA user_version = 11")


def _migrate_v11_to_v12(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checking_month_settings (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            beginning_balance_cents INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(year, month)
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("12",),
    )
    conn.execute("PRAGMA user_version = 12")


def _migrate_v12_to_v13(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS institutions (
            institution_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO institutions(name, is_active)
        VALUES ('Default Institution', 1)
        """
    )
    default_institution = conn.execute(
        """
        SELECT institution_id
        FROM institutions
        WHERE lower(trim(name)) = 'default institution'
        LIMIT 1
        """
    ).fetchone()
    if default_institution is None:
        raise RuntimeError("Failed to ensure default institution during migration.")
    default_institution_id = int(default_institution["institution_id"])

    if not _table_exists(conn, "accounts"):
        conn.execute(
            """
            CREATE TABLE accounts (
                account_id INTEGER PRIMARY KEY,
                institution_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                account_type TEXT NOT NULL,
                opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                account_number_mask TEXT NULL,
                notes TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(institution_id, name),
                FOREIGN KEY(institution_id) REFERENCES institutions(institution_id)
            )
            """
        )
        for account_name, account_type in SEEDED_ACCOUNT_ROWS:
            conn.execute(
                """
                INSERT OR IGNORE INTO accounts(
                    institution_id, name, account_type, opening_balance_cents, account_number_mask, notes, is_active
                )
                VALUES (?, ?, ?, 0, NULL, NULL, 1)
                """,
                (default_institution_id, account_name, account_type),
            )
    else:
        account_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        # Use in-place ALTERs instead of table rebuild. Rebuild + rename can break
        # dependent foreign keys in existing user databases during migration.
        if "institution_id" not in account_cols:
            conn.execute(
                "ALTER TABLE accounts ADD COLUMN institution_id INTEGER NULL"
            )
        if "account_number_mask" not in account_cols:
            conn.execute(
                "ALTER TABLE accounts ADD COLUMN account_number_mask TEXT NULL"
            )
        if "notes" not in account_cols:
            conn.execute(
                "ALTER TABLE accounts ADD COLUMN notes TEXT NULL"
            )
        conn.execute(
            """
            UPDATE accounts
            SET institution_id = ?
            WHERE institution_id IS NULL
            """,
            (default_institution_id,),
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_institution_name
            ON accounts(institution_id, name)
            """
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checking_month_settings_new (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            beginning_balance_cents INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(year, month, account_id),
            FOREIGN KEY(account_id) REFERENCES accounts(account_id)
        )
        """
    )
    checking_account = conn.execute(
        """
        SELECT account_id
        FROM accounts
        WHERE lower(trim(account_type)) = 'checking'
        ORDER BY account_id ASC
        LIMIT 1
        """
    ).fetchone()
    fallback_account = conn.execute(
        "SELECT account_id FROM accounts ORDER BY account_id ASC LIMIT 1"
    ).fetchone()
    default_checking_account_id = int(
        (checking_account or fallback_account or {"account_id": 1})["account_id"]
    )

    checking_cols = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(checking_month_settings)").fetchall()
    }
    if "account_id" in checking_cols:
        conn.execute(
            """
            INSERT OR IGNORE INTO checking_month_settings_new(
                year, month, account_id, beginning_balance_cents, updated_at
            )
            SELECT year, month, account_id, beginning_balance_cents, updated_at
            FROM checking_month_settings
            """
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO checking_month_settings_new(
                year, month, account_id, beginning_balance_cents, updated_at
            )
            SELECT year, month, ?, beginning_balance_cents, updated_at
            FROM checking_month_settings
            """,
            (default_checking_account_id,),
        )

    conn.execute("DROP TABLE checking_month_settings")
    conn.execute("ALTER TABLE checking_month_settings_new RENAME TO checking_month_settings")

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("13",),
    )
    conn.execute("PRAGMA user_version = 13")


def _migrate_v13_to_v14(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "accounts") and not _column_exists(conn, "accounts", "notes"):
        conn.execute("ALTER TABLE accounts ADD COLUMN notes TEXT NULL")
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("14",),
    )
    conn.execute("PRAGMA user_version = 14")


def _migrate_v14_to_v15(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "accounts"):
        if not _column_exists(conn, "accounts", "account_number"):
            conn.execute("ALTER TABLE accounts ADD COLUMN account_number TEXT NULL")
        if not _column_exists(conn, "accounts", "balance_cents"):
            conn.execute("ALTER TABLE accounts ADD COLUMN balance_cents INTEGER NOT NULL DEFAULT 0")
        if not _column_exists(conn, "accounts", "cd_start_date"):
            conn.execute("ALTER TABLE accounts ADD COLUMN cd_start_date TEXT NULL")
        if not _column_exists(conn, "accounts", "cd_interval_count"):
            conn.execute("ALTER TABLE accounts ADD COLUMN cd_interval_count INTEGER NULL")
        if not _column_exists(conn, "accounts", "cd_interval_unit"):
            conn.execute("ALTER TABLE accounts ADD COLUMN cd_interval_unit TEXT NULL")
        if not _column_exists(conn, "accounts", "cd_interest_rate_bps"):
            conn.execute("ALTER TABLE accounts ADD COLUMN cd_interest_rate_bps INTEGER NULL")

        # Backfill new fields from legacy data where possible.
        if _column_exists(conn, "accounts", "account_number_mask"):
            conn.execute(
                """
                UPDATE accounts
                SET account_number = account_number_mask
                WHERE (account_number IS NULL OR trim(account_number) = '')
                  AND account_number_mask IS NOT NULL
                  AND trim(account_number_mask) <> ''
                """
            )
        if _column_exists(conn, "accounts", "opening_balance_cents"):
            conn.execute(
                """
                UPDATE accounts
                SET balance_cents = opening_balance_cents
                WHERE balance_cents = 0
                """
            )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("15",),
    )
    conn.execute("PRAGMA user_version = 15")


def _migrate_v15_to_v16(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS transaction_splits")
    conn.execute("DROP TABLE IF EXISTS bills_month_settings")
    conn.execute("DROP TABLE IF EXISTS bucket_movements")
    conn.execute("DROP TABLE IF EXISTS savings_buckets")

    needs_categories_rebuild = _column_exists(conn, "categories", "parent_category_id")
    needs_accounts_rebuild = _column_exists(conn, "accounts", "account_number_mask")
    if needs_categories_rebuild or needs_accounts_rebuild:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            if needs_categories_rebuild:
                conn.execute(
                    """
                    CREATE TABLE categories_new (
                        category_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        is_income INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO categories_new(category_id, name, is_income, is_active)
                    SELECT category_id, name, is_income, is_active
                    FROM categories
                    """
                )
                conn.execute("DROP TABLE categories")
                conn.execute("ALTER TABLE categories_new RENAME TO categories")

            if needs_accounts_rebuild:
                conn.execute(
                    """
                    CREATE TABLE accounts_new (
                        account_id INTEGER PRIMARY KEY,
                        institution_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        account_type TEXT NOT NULL,
                        opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                        account_number TEXT NULL,
                        balance_cents INTEGER NOT NULL DEFAULT 0,
                        notes TEXT NULL,
                        cd_start_date TEXT NULL,
                        cd_interval_count INTEGER NULL,
                        cd_interval_unit TEXT NULL,
                        cd_interest_rate_bps INTEGER NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        UNIQUE(institution_id, name),
                        FOREIGN KEY(institution_id) REFERENCES institutions(institution_id)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO accounts_new(
                        account_id,
                        institution_id,
                        name,
                        account_type,
                        opening_balance_cents,
                        account_number,
                        balance_cents,
                        notes,
                        cd_start_date,
                        cd_interval_count,
                        cd_interval_unit,
                        cd_interest_rate_bps,
                        is_active
                    )
                    SELECT
                        account_id,
                        institution_id,
                        name,
                        account_type,
                        opening_balance_cents,
                        account_number,
                        balance_cents,
                        notes,
                        cd_start_date,
                        cd_interval_count,
                        cd_interval_unit,
                        cd_interest_rate_bps,
                        is_active
                    FROM accounts
                    """
                )
                conn.execute("DROP TABLE accounts")
                conn.execute("ALTER TABLE accounts_new RENAME TO accounts")
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("16",),
    )
    conn.execute("PRAGMA user_version = 16")


def _migrate_v16_to_v17(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "accounts") and not _column_exists(conn, "accounts", "is_external"):
        conn.execute(
            "ALTER TABLE accounts ADD COLUMN is_external INTEGER NOT NULL DEFAULT 0"
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS account_month_settings (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            beginning_balance_cents INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(year, month, account_id),
            FOREIGN KEY(account_id) REFERENCES accounts(account_id)
        )
        """
    )

    if _table_exists(conn, "checking_month_settings"):
        conn.execute(
            """
            INSERT OR IGNORE INTO account_month_settings(
                year,
                month,
                account_id,
                beginning_balance_cents,
                updated_at
            )
            SELECT
                year,
                month,
                account_id,
                beginning_balance_cents,
                updated_at
            FROM checking_month_settings
            """
        )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("17",),
    )
    conn.execute("PRAGMA user_version = 17")


def _migrate_v17_to_v18(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "accounts") and _column_exists(conn, "accounts", "balance_cents"):
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                """
                CREATE TABLE accounts_new (
                    account_id INTEGER PRIMARY KEY,
                    institution_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    account_type TEXT NOT NULL,
                    opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                    account_number TEXT NULL,
                    notes TEXT NULL,
                    cd_start_date TEXT NULL,
                    cd_interval_count INTEGER NULL,
                    cd_interval_unit TEXT NULL,
                    cd_interest_rate_bps INTEGER NULL,
                    is_external INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(institution_id, name),
                    FOREIGN KEY(institution_id) REFERENCES institutions(institution_id)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO accounts_new(
                    account_id,
                    institution_id,
                    name,
                    account_type,
                    opening_balance_cents,
                    account_number,
                    notes,
                    cd_start_date,
                    cd_interval_count,
                    cd_interval_unit,
                    cd_interest_rate_bps,
                    is_external,
                    is_active
                )
                SELECT
                    account_id,
                    institution_id,
                    name,
                    account_type,
                    opening_balance_cents,
                    account_number,
                    notes,
                    cd_start_date,
                    cd_interval_count,
                    cd_interval_unit,
                    cd_interest_rate_bps,
                    is_external,
                    is_active
                FROM accounts
                """
            )
            conn.execute("DROP TABLE accounts")
            conn.execute("ALTER TABLE accounts_new RENAME TO accounts")
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("18",),
    )
    conn.execute("PRAGMA user_version = 18")


def _migrate_v18_to_v19(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("19",),
    )
    conn.execute("PRAGMA user_version = 19")


def _migrate_v19_to_v20(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "account_month_settings"):
        if not _column_exists(conn, "account_month_settings", "statement_ending_balance_cents"):
            conn.execute(
                "ALTER TABLE account_month_settings "
                "ADD COLUMN statement_ending_balance_cents INTEGER NULL"
            )
        if not _column_exists(conn, "account_month_settings", "statement_ending_date"):
            conn.execute(
                "ALTER TABLE account_month_settings "
                "ADD COLUMN statement_ending_date TEXT NULL"
            )

    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("20",),
    )
    conn.execute("PRAGMA user_version = 20")


def _migrate_v20_to_v21(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_report_catalog_active_sort")
    conn.execute("DROP TABLE IF EXISTS report_catalog")
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        ("21",),
    )
    conn.execute("PRAGMA user_version = 21")


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
        elif current_version == 8:
            _migrate_v8_to_v9(conn)
        elif current_version == 9:
            _migrate_v9_to_v10(conn)
        elif current_version == 10:
            _migrate_v10_to_v11(conn)
        elif current_version == 11:
            _migrate_v11_to_v12(conn)
        elif current_version == 12:
            _migrate_v12_to_v13(conn)
        elif current_version == 13:
            _migrate_v13_to_v14(conn)
        elif current_version == 14:
            _migrate_v14_to_v15(conn)
        elif current_version == 15:
            _migrate_v15_to_v16(conn)
        elif current_version == 16:
            _migrate_v16_to_v17(conn)
        elif current_version == 17:
            _migrate_v17_to_v18(conn)
        elif current_version == 18:
            _migrate_v18_to_v19(conn)
        elif current_version == 19:
            _migrate_v19_to_v20(conn)
        elif current_version == 20:
            _migrate_v20_to_v21(conn)
        else:
            raise RuntimeError(
                "Unsupported migration path. "
                f"Found user_version={current_version}; expected {SCHEMA_VERSION}."
            )
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
