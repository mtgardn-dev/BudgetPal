from __future__ import annotations

SCHEMA_VERSION = 1

INITIAL_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tax_categories (
        name TEXT PRIMARY KEY,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        parent_category_id INTEGER NULL,
        is_income INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(parent_category_id) REFERENCES categories(category_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        account_type TEXT NOT NULL,
        opening_balance_cents INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        txn_id INTEGER PRIMARY KEY,
        txn_date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        txn_type TEXT NOT NULL CHECK (txn_type IN ('expense', 'income', 'transfer')),
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
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY(category_id) REFERENCES categories(category_id),
        FOREIGN KEY(account_id) REFERENCES accounts(account_id),
        FOREIGN KEY(tax_category) REFERENCES tax_categories(name)
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_source_uid
    ON transactions(source_system, source_uid)
    WHERE source_system IS NOT NULL AND source_uid IS NOT NULL;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(txn_date);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_txn_tax ON transactions(tax_deductible, tax_year);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_txn_transfer_group ON transactions(transfer_group_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS transaction_splits (
        split_id INTEGER PRIMARY KEY,
        txn_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        amount_cents INTEGER NOT NULL,
        note TEXT NULL,
        FOREIGN KEY(txn_id) REFERENCES transactions(txn_id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(category_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_txn_splits_txn ON transaction_splits(txn_id);
    """,
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
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_lines (
        budget_line_id INTEGER PRIMARY KEY,
        budget_month_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        planned_cents INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(budget_month_id, category_id),
        FOREIGN KEY(budget_month_id) REFERENCES budget_months(budget_month_id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(category_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bills (
        bill_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        default_amount_cents INTEGER NULL,
        category_id INTEGER NULL,
        due_day INTEGER NULL,
        frequency TEXT NOT NULL,
        autopay INTEGER NOT NULL DEFAULT 0,
        payee_match TEXT NULL,
        source_system TEXT NOT NULL DEFAULT 'budgetpal',
        source_uid TEXT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        notes TEXT NULL,
        FOREIGN KEY(category_id) REFERENCES categories(category_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bills_source ON bills(source_system, source_uid);
    """,
    """
    CREATE TABLE IF NOT EXISTS bill_occurrences (
        bill_occurrence_id INTEGER PRIMARY KEY,
        bill_id INTEGER NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        expected_date TEXT NULL,
        expected_amount_cents INTEGER NULL,
        status TEXT NOT NULL DEFAULT 'expected'
            CHECK (status IN ('expected', 'paid', 'skipped', 'adjusted')),
        paid_date TEXT NULL,
        paid_amount_cents INTEGER NULL,
        matched_txn_id INTEGER NULL,
        note TEXT NULL,
        UNIQUE(bill_id, year, month),
        FOREIGN KEY(bill_id) REFERENCES bills(bill_id) ON DELETE CASCADE,
        FOREIGN KEY(matched_txn_id) REFERENCES transactions(txn_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_buckets (
        bucket_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        target_cents INTEGER NULL,
        target_date TEXT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bucket_movements (
        movement_id INTEGER PRIMARY KEY,
        bucket_id INTEGER NOT NULL,
        movement_date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        note TEXT NULL,
        linked_txn_id INTEGER NULL,
        FOREIGN KEY(bucket_id) REFERENCES savings_buckets(bucket_id) ON DELETE CASCADE,
        FOREIGN KEY(linked_txn_id) REFERENCES transactions(txn_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bucket_date
    ON bucket_movements(bucket_id, movement_date);
    """,
]

SEEDED_TAX_CATEGORIES = [
    "Charity",
    "Medical",
    "Property Tax",
    "Education",
    "Business Expense",
    "Home Office",
    "Childcare",
    "Mileage",
    "Other",
]

SEEDED_CATEGORY_ROWS = [
    ("Income", 1),
    ("Housing", 0),
    ("Utilities", 0),
    ("Groceries", 0),
    ("Transportation", 0),
    ("Insurance", 0),
    ("Debt", 0),
    ("Savings", 0),
    ("Entertainment", 0),
    ("Healthcare", 0),
    ("Misc", 0),
]

SEEDED_ACCOUNT_ROWS = [
    ("Checking", "checking"),
    ("Savings", "savings"),
    ("Credit Card", "credit"),
    ("Cash", "cash"),
]
