# BudgetPal Requirements and Design Specification

## Scope
BudgetPal is a local-first household budget manager that integrates with SubTracker through a stable SQLite view contract (`v_budgetpal_subscriptions`).

## Confirmed Decisions
- Signed integer cents (`income > 0`, `expense < 0`).
- Transfers are two linked rows using `transfer_group_id`.
- `transaction_splits` included in v1 schema.
- SubTracker DB location in `config/budgetpal_config.json`.
- Missing SubTracker view contract fails early.
- New month budget lines auto-copy from prior month and remain editable.
- Bill occurrences generated for selected month only.
- Bill auto-match deferred.
- Tax categories seeded from fixed list.
- Docked activity log in UI + rotating file logs (5 files x 1MB).
- Path registry API is frozen-path ready.
- Tests include core, integration, and UI smoke.

## SQLite Tables
- `app_meta`
- `tax_categories`
- `categories`
- `accounts`
- `transactions`
- `transaction_splits`
- `budget_months`
- `budget_lines`
- `bills`
- `bill_occurrences`
- `savings_buckets`
- `bucket_movements`

## Qt6 Screen Layout
Tabs:
1. Dashboard
2. Transactions
3. Budget (Month)
4. Bills
5. Savings Buckets
6. Reports

Includes a docked clearable activity log panel.
