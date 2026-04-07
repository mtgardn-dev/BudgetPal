from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class SubPaymentMappingsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def list_subscription_expense_candidates(self, year: int, month: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.amount_cents,
                    t.description,
                    t.account_id,
                    a.name AS account_name,
                    t.source_uid,
                    m.sub_id,
                    m.external_txn_key,
                    m.override_amount_cents,
                    m.last_post_status,
                    m.subtracker_payment_id,
                    m.last_error,
                    m.last_posted_at
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                LEFT JOIN sub_payment_mappings m ON m.txn_id = t.txn_id
                WHERE t.txn_type = 'expense'
                  AND t.is_subscription = 1
                  AND strftime('%Y', t.txn_date) = ?
                  AND strftime('%m', t.txn_date) = ?
                ORDER BY t.txn_date ASC, t.txn_id ASC
                """,
                (str(year), f"{month:02d}"),
            ).fetchall()
            parsed_rows = [dict(row) for row in rows]
            for row in parsed_rows:
                override = row.get("override_amount_cents")
                if override is None:
                    row["display_amount_cents"] = abs(int(row.get("amount_cents") or 0))
                else:
                    row["display_amount_cents"] = abs(int(override))
            return parsed_rows

    def upsert_selection(
        self,
        txn_id: int,
        sub_id: int | None,
        override_amount_cents: int | None,
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO sub_payment_mappings(
                    txn_id,
                    sub_id,
                    override_amount_cents,
                    updated_at
                ) VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(txn_id) DO UPDATE SET
                    sub_id = excluded.sub_id,
                    override_amount_cents = excluded.override_amount_cents,
                    updated_at = datetime('now')
                """,
                (txn_id, sub_id, override_amount_cents),
            )

    def record_post_success(
        self,
        txn_id: int,
        sub_id: int,
        external_txn_key: str,
        subtracker_payment_id: int,
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO sub_payment_mappings(
                    txn_id,
                    sub_id,
                    external_source,
                    external_txn_key,
                    last_post_status,
                    subtracker_payment_id,
                    last_error,
                    last_posted_at,
                    updated_at
                ) VALUES (?, ?, 'budgetpal', ?, 'posted', ?, NULL, datetime('now'), datetime('now'))
                ON CONFLICT(txn_id) DO UPDATE SET
                    sub_id = excluded.sub_id,
                    external_source = 'budgetpal',
                    external_txn_key = excluded.external_txn_key,
                    last_post_status = 'posted',
                    subtracker_payment_id = excluded.subtracker_payment_id,
                    last_error = NULL,
                    last_posted_at = datetime('now'),
                    updated_at = datetime('now')
                """,
                (txn_id, sub_id, external_txn_key, subtracker_payment_id),
            )

    def record_post_error(
        self,
        txn_id: int,
        sub_id: int | None,
        external_txn_key: str | None,
        error_text: str,
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO sub_payment_mappings(
                    txn_id,
                    sub_id,
                    external_source,
                    external_txn_key,
                    last_post_status,
                    last_error,
                    updated_at
                ) VALUES (?, ?, 'budgetpal', ?, 'error', ?, datetime('now'))
                ON CONFLICT(txn_id) DO UPDATE SET
                    sub_id = excluded.sub_id,
                    external_source = 'budgetpal',
                    external_txn_key = COALESCE(excluded.external_txn_key, sub_payment_mappings.external_txn_key),
                    last_post_status = 'error',
                    last_error = excluded.last_error,
                    updated_at = datetime('now')
                """,
                (txn_id, sub_id, external_txn_key, error_text),
            )
