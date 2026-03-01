# Budget Pal Requirements and Design Specification

## 1. Purpose and Scope

**Budget Pal** is a **local-first** household budgeting application designed to match an existing “home CFO” spreadsheet workflow:

* planned vs actual monthly budget rollups
* transactions ledger as single source of truth
* bills checklist with paid tracking
* savings buckets (sinking funds) ledger
* account register and reconciliation support
* tax-deductible tagging and reporting
* export/import for audit-proof archiving

It integrates with an existing **SubTracker** application to populate subscription renewals into the bills checklist.

### Non-goals (for initial releases)

* No cloud backend or hosted service
* No mobile client app
* No real-time bank aggregator connection (Plaid-like) in MVP
* No investment portfolio management beyond simple balances (optional later)

---

## 2. Operating Model

### Local-first workflow

* CFO captures transactions on iPhone in **Google Sheets** (or Google Form feeding a sheet).
* Budget Pal imports transactions locally (CSV or Google Sheets API).
* Budget Pal maintains authoritative state in a local SQLite database.
* Budget Pal pulls subscriptions from SubTracker by reading a **SQLite VIEW** (stable contract).
* Budget Pal produces:

  * monthly budget rollups
  * bill checklist and paid state
  * tax reports
  * archive exports

---

## 3. Functional Requirements

### 3.1 Transactions

**FR-T1** Import transactions from external sources:

* CSV import (required for MVP)
* Google Sheets API import (optional but recommended)
* Manual entry in app (required)

**FR-T2** Transaction fields:

* Date, Amount, Payee/Description, Category, Account, Notes
* Type inferred (expense vs income) OR explicit field
* Optional fields: tags, “bill link”, “subscription link”, tax fields

**FR-T3** Categorization:

* Category dropdown with controlled vocabulary
* User-editable categories
* Rules engine (later): payee → category mapping

**FR-T4** Split transactions:

* One transaction may allocate to multiple categories (post-MVP, but plan schema now)

**FR-T5** De-duplication:

* Imports must not create duplicates (source_id or hash matching)

---

### 3.2 Monthly Budget (Planned vs Actual)

**FR-B1** Monthly budget setup:

* Create month from template (copy prior month planned values)
* Edit planned income and expense amounts

**FR-B2** Actual rollups:

* Actuals computed from transactions by month + category
* Over/under displayed per category

**FR-B3** Cash flow summary:

* Starting balance for month
* End balance computed: start + actual income − actual expenses

**FR-B4** Reporting:

* Monthly summary report (printable/exportable)

---

### 3.3 Bills Checklist (including SubTracker)

**FR-L1** Bill definitions:

* Name, amount (fixed or variable), due date/day, frequency, category, autopay flag, notes

**FR-L2** Monthly bill occurrences:

* For each month, generate expected bills
* Track status: expected, paid, skipped, adjusted
* Paid date and paid amount supported

**FR-L3** Subscription integration:

* Read subscription renewals from SubTracker view and include them as bill occurrences
* Subscriptions appear in a dedicated group/section

**FR-L4** Auto-matching (optional, recommended):

* Mark bill as paid when a matching transaction appears (payee + amount tolerance + date window)

---

### 3.4 Savings Buckets (Sinking Funds)

**FR-S1** Define buckets:

* Bucket name, optional target amount, optional target date

**FR-S2** Bucket movements:

* Add contribution/withdrawal events with date, amount, note, linked account (optional)

**FR-S3** Monthly snapshot:

* Track balances across months with roll-forward logic

---

### 3.5 Accounts and Reconciliation

**FR-A1** Accounts:

* Checking, savings, credit card, cash (at minimum)

**FR-A2** Register view:

* Running balance per account
* Flag transactions as reconciled

**FR-A3** Reconciliation workflow (post-MVP but design-ready):

* Import statement lines
* Match/confirm items
* Display difference until reconciled

---

### 3.6 Tax Support (18+ months and reporting)

**FR-X1** Retention:

* Store multiple years; at least 18 months accessible in UI

**FR-X2** Tax flags:

* A transaction can be marked tax deductible
* Assign tax category (Charity, Medical, Property Tax, etc.)
* Notes and optional receipt link

**FR-X3** Tax reports:

* Summary report by tax category and by budget category
* Detail report listing all tax-deductible transactions
* Export for preparer (CSV + optional PDF)

---

### 3.7 Export / Import / Archiving

**FR-E1** Export archive package:

* Single ZIP containing:

  * SQLite database file (authoritative)
  * CSV exports (transactions, bills, budgets, buckets)
  * metadata JSON with schema version + export date

**FR-E2** Import archive:

* Restore entire system from ZIP

**FR-E3** Import CSV:

* Merge transactions/bills/budgets from CSV with de-duplication

---

## 4. Non-Functional Requirements

### 4.1 Simplicity and maintainability

* Strict separation: UI ↔ Services ↔ Persistence
* All financial logic in testable core modules
* Schema migrations supported from day one

### 4.2 Security and privacy

* Local storage only
* No telemetry by default
* Optional database encryption later (SQLCipher) if desired

### 4.3 Performance

* Must handle several years of data and thousands of transactions without UI lag

### 4.4 Portability

* macOS primary, but avoid OS-specific dependencies where possible
* Distributable via PyInstaller

---

## 5. Data Model and SQLite Schema (Budget Pal)

### 5.1 Conventions

* Amounts stored as **integer cents** to avoid floating point errors.
* Dates stored as ISO-8601 text `YYYY-MM-DD`.
* All tables include `created_at`, `updated_at` (optional in MVP but recommended).

---

## 5.2 Core Tables

### `app_meta`

Tracks schema version and app info.

```sql
CREATE TABLE app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
/* keys: schema_version, created_on, app_name */
```

---

### `categories`

```sql
CREATE TABLE categories (
  category_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  parent_category_id INTEGER NULL,
  is_income INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(parent_category_id) REFERENCES categories(category_id)
);
```

---

### `accounts`

```sql
CREATE TABLE accounts (
  account_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  account_type TEXT NOT NULL, -- checking, savings, credit, cash
  opening_balance_cents INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1
);
```

---

### `transactions`

```sql
CREATE TABLE transactions (
  txn_id INTEGER PRIMARY KEY,
  txn_date TEXT NOT NULL,              -- YYYY-MM-DD
  amount_cents INTEGER NOT NULL,        -- expense negative OR store sign + type
  txn_type TEXT NOT NULL,              -- expense | income | transfer
  payee TEXT NOT NULL,
  description TEXT NULL,
  category_id INTEGER NULL,
  account_id INTEGER NOT NULL,
  note TEXT NULL,

  -- import/de-dupe support
  source_system TEXT NULL,             -- "google_sheet", "manual", "bank_csv"
  source_uid TEXT NULL,                -- stable row id if available
  import_hash TEXT NULL,               -- fallback de-dupe key
  is_reconciled INTEGER NOT NULL DEFAULT 0,

  -- tax support
  tax_deductible INTEGER NOT NULL DEFAULT 0,
  tax_category TEXT NULL,              -- "Charity", "Medical", etc.
  tax_year INTEGER NULL,               -- derived but stored for speed
  tax_note TEXT NULL,
  receipt_uri TEXT NULL,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY(category_id) REFERENCES categories(category_id),
  FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

CREATE UNIQUE INDEX idx_txn_source_uid ON transactions(source_system, source_uid)
  WHERE source_system IS NOT NULL AND source_uid IS NOT NULL;

CREATE INDEX idx_txn_date ON transactions(txn_date);
CREATE INDEX idx_txn_category ON transactions(category_id);
CREATE INDEX idx_txn_tax ON transactions(tax_deductible, tax_year);
```

**Design note:** For transfers, use `txn_type='transfer'` and either:

* two rows (one negative from account A, one positive to account B), linked by `transfer_group_id` (future enhancement), OR
* a dedicated transfers table. Start simple with two rows.

---

## 5.3 Monthly Budgets

### `budget_months`

```sql
CREATE TABLE budget_months (
  budget_month_id INTEGER PRIMARY KEY,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL, -- 1-12
  starting_balance_cents INTEGER NOT NULL DEFAULT 0,
  notes TEXT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(year, month)
);
```

### `budget_lines`

Planned values by category for a given month.

```sql
CREATE TABLE budget_lines (
  budget_line_id INTEGER PRIMARY KEY,
  budget_month_id INTEGER NOT NULL,
  category_id INTEGER NOT NULL,
  planned_cents INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(budget_month_id, category_id),
  FOREIGN KEY(budget_month_id) REFERENCES budget_months(budget_month_id),
  FOREIGN KEY(category_id) REFERENCES categories(category_id)
);
```

**Actuals are computed** via query on `transactions`.

---

## 5.4 Bills and Bill Occurrences

### `bills`

```sql
CREATE TABLE bills (
  bill_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  default_amount_cents INTEGER NULL,
  category_id INTEGER NULL,
  due_day INTEGER NULL,                -- 1-31
  frequency TEXT NOT NULL,             -- monthly, quarterly, annual, adhoc
  autopay INTEGER NOT NULL DEFAULT 0,
  payee_match TEXT NULL,               -- hint for auto-matching
  source_system TEXT NOT NULL DEFAULT 'budgetpal', -- budgetpal | subtracker
  source_uid TEXT NULL,                -- subtracker subscription_id if applicable
  is_active INTEGER NOT NULL DEFAULT 1,
  notes TEXT NULL,
  FOREIGN KEY(category_id) REFERENCES categories(category_id)
);

CREATE INDEX idx_bills_source ON bills(source_system, source_uid);
```

### `bill_occurrences`

```sql
CREATE TABLE bill_occurrences (
  bill_occurrence_id INTEGER PRIMARY KEY,
  bill_id INTEGER NOT NULL,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  expected_date TEXT NULL,             -- YYYY-MM-DD
  expected_amount_cents INTEGER NULL,
  status TEXT NOT NULL DEFAULT 'expected', -- expected, paid, skipped, adjusted
  paid_date TEXT NULL,
  paid_amount_cents INTEGER NULL,
  matched_txn_id INTEGER NULL,
  note TEXT NULL,
  UNIQUE(bill_id, year, month),
  FOREIGN KEY(bill_id) REFERENCES bills(bill_id),
  FOREIGN KEY(matched_txn_id) REFERENCES transactions(txn_id)
);
```

---

## 5.5 Savings Buckets

### `savings_buckets`

```sql
CREATE TABLE savings_buckets (
  bucket_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  target_cents INTEGER NULL,
  target_date TEXT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);
```

### `bucket_movements`

```sql
CREATE TABLE bucket_movements (
  movement_id INTEGER PRIMARY KEY,
  bucket_id INTEGER NOT NULL,
  movement_date TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,     -- + contribution, - withdrawal
  note TEXT NULL,
  linked_txn_id INTEGER NULL,
  FOREIGN KEY(bucket_id) REFERENCES savings_buckets(bucket_id),
  FOREIGN KEY(linked_txn_id) REFERENCES transactions(txn_id)
);

CREATE INDEX idx_bucket_date ON bucket_movements(bucket_id, movement_date);
```

---

## 6. SubTracker Integration Contract (SQLite VIEW)

Budget Pal reads subscriptions from SubTracker’s DB using a **stable view**. Budget Pal does not query SubTracker base tables directly.

### Required view in SubTracker DB

```sql
CREATE VIEW v_budgetpal_subscriptions AS
SELECT
  subscription_id            AS sub_id,
  vendor                     AS vendor,
  next_renewal_date          AS renewal_date,        -- YYYY-MM-DD
  renewal_amount_cents       AS amount_cents,
  billing_frequency          AS frequency,           -- monthly/annual/etc.
  category_name              AS category,            -- optional
  autopay_flag               AS autopay,
  is_active                  AS active
FROM subscriptions
WHERE is_active = 1;
```

### Recommended meta table in SubTracker

```sql
CREATE TABLE IF NOT EXISTS subtracker_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
/* key: budgetpal_view_version */
```

Budget Pal checks `budgetpal_view_version` to guard against breaking changes.

### Integration behavior

* On refresh, Budget Pal:

  1. reads the view
  2. upserts into `bills` with `source_system='subtracker'` and `source_uid=sub_id`
  3. generates/updates `bill_occurrences` for the target month(s)

---

## 7. Qt6 UI Design (PySide6)

### UI goals

* Mirror spreadsheet mental model
* Make “review” and “status” easy
* Minimize clicks and typing for repetitive work
* Keep screens simple, table-driven

### Main Window Layout

**QMainWindow**

* Menu: File (Import, Export, Backup), Edit (Categories, Accounts), Reports (Tax, Monthly), Help
* Toolbar: Import Transactions, Refresh Subscriptions, Export Archive
* Central: `QTabWidget` with primary screens

#### Tabs (initial)

1. **Dashboard**
2. **Transactions**
3. **Budget (Month)**
4. **Bills**
5. **Savings Buckets**
6. **Reports**

---

### Screen 1: Dashboard

Purpose: quick month status.

* Month selector (Year/Month)
* Cards:

  * Starting Balance, Actual Income, Actual Expenses, End Balance
  * Bills due this week / remaining
  * Overspent categories (top 5)
* Buttons:

  * Import Transactions
  * Refresh Subscriptions

Qt widgets:

* `QComboBox` month picker
* `QLabel` metrics
* Optional `QtCharts` later

---

### Screen 2: Transactions

* Table (QTableView) with filter row:

  * Date range
  * Category
  * Account
  * Search text
  * Tax deductible toggle
* Buttons:

  * Add / Edit / Delete
  * Import
  * Mark Reconciled
* Side panel (optional) showing transaction details and tax fields

Qt approach:

* `QTableView + QAbstractTableModel` (recommended, not QTableWidget)
* `QSortFilterProxyModel` for filtering
* Dialog for Add/Edit with validation

---

### Screen 3: Budget (Month)

* Month selector
* Two tables:

  * Income lines (planned vs actual vs variance)
  * Expense lines (planned vs actual vs variance)
* Summary bar:

  * Starting balance, end balance, net cash flow
* Buttons:

  * Copy planned from prior month
  * Export monthly report

Actuals computed via SQL query grouped by category for the month.

---

### Screen 4: Bills

* Month selector
* Table grouped by:

  * Fixed bills
  * Subscriptions (from SubTracker)
  * Periodic bills
* Columns:

  * Bill name, due date, expected amount, status, paid date, paid amount, autopay, notes, source
* Actions:

  * Mark Paid
  * Adjust amount
  * Refresh SubTracker
  * Auto-match to transactions (optional toggle)

---

### Screen 5: Savings Buckets

* Buckets list with balances
* Movement ledger for selected bucket
* Add movement dialog (amount, date, note, link txn optional)
* Monthly balances view (optional)

---

### Screen 6: Reports

* Report picker:

  * Tax deductible summary (year)
  * Tax deductible detail (year)
  * Monthly budget summary
* Export button (CSV/PDF)

---

## 8. Calculation Rules

### Monthly actuals

For selected month:

* Expense actual = sum(expense transactions in month, by category)
* Income actual = sum(income transactions in month, by category)

### End balance

`end_balance = starting_balance + sum(income) - sum(expenses)`
(Define sign conventions clearly; recommended: store income positive, expenses negative, then end_balance = start + sum(all amounts).)

### Bill matching (optional rule)

Match transaction to bill occurrence if:

* payee contains payee_match OR vendor (normalized)
* amount within tolerance (e.g., ±$1.00 or ±2%)
* txn_date within window (e.g., due_date ± 7 days)

---

## 9. Import/Export Specifications

### Transaction import CSV minimum columns

* Date, Amount, Payee/Description, Category, Account, Notes
  Optional:
* TaxDeductible, TaxCategory, ReceiptURI

### Export archive ZIP contents

* `budgetpal.sqlite`
* `export/transactions.csv`
* `export/bills.csv`
* `export/bill_occurrences.csv`
* `export/budgets.csv`
* `export/budget_lines.csv`
* `export/buckets.csv`
* `export/bucket_movements.csv`
* `meta.json` (schema_version, exported_at, app_version)

---

## 10. Transparency and Consistency
### Add logging to a file and a clearable user message area on the main gui to ensure that any errors, status changes, operations are clearly known.
### Use a path_registry for all directory and file locations.  No path math in any modules except the path_registry.  Make the path-registry compatible with using frozen paths in packaged apps.

## 11. Software Architecture

### Recommended package layout

```text
budgetpal/
  core/
    domain.py              # dataclasses / domain objects
    services/
      budgeting.py
      bills.py
      subscriptions.py
      tax.py
      reporting.py
  persistence/
    db.py                  # connection, row factory
    schema.py              # schema creation
    migrations.py          # schema upgrades
    repositories/
      transactions_repo.py
      budgets_repo.py
      bills_repo.py
      buckets_repo.py
  importers/
    csv_transactions.py
    google_sheets.py       # optional
    subtracker_view.py     # reads SubTracker view
  ui/
    qt/
      main_window.py
      tabs/
        dashboard.py
        transactions.py
        budget_month.py
        bills.py
        buckets.py
        reports.py
      models/
        transactions_model.py   # QAbstractTableModel
        bills_model.py
  tests/
    test_imports.py
    test_budget_math.py
    test_tax_reports.py
    test_export_import.py
```

### Engineering rules

* UI never runs SQL directly; UI calls services/repositories.
* Services return domain objects or DTOs for UI.
* All importers write through repositories (so de-dupe logic is centralized).
* Add schema migrations early (even if manual).

---

## 12. MVP Delivery Plan

**MVP-1**

* Local SQLite + schema + migrations
* Transactions: manual entry + CSV import + table view + category list
* Monthly budget: planned lines + actual rollup + start/end balance
* Bills: manual bills + monthly occurrences + paid tracking
* Export archive ZIP + restore import ZIP

**MVP-2**

* SubTracker integration via view (upsert bills + occurrences)
* Tax flags + tax reports (year selector)
* Basic filtering/search in transactions

**MVP-3**

* Savings buckets + movements
* Optional bill auto-match
* Optional Google Sheets API import
* Reconciliation scaffolding

---

## 13. Guardrails
Schema-first discipline
Lock down migrations early. No ad-hoc schema edits.

No business logic in UI layer
Qt screens should call services. Period.

Integer cents everywhere
No floats for money. Ever.

Do not change public APIs unless approved. 
This is a new application, do not program for backward compatibility...yet.

## 14. Open Decisions (parked, not required now)

* Whether to store expenses negative or store type separately + absolute amounts (pick one and stay consistent)
* Whether to support split transactions in MVP (schema can accommodate either way)
* Whether to package as one-click macOS app bundle early or keep as Python script during development


