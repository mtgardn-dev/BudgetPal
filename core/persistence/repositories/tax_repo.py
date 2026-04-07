from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class TaxRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def list_categories(self) -> list[str]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM tax_categories WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            return [str(r["name"]) for r in rows]

    def tax_summary(self, tax_year: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(tax_category, 'Uncategorized') AS tax_category,
                    SUM(amount_cents) AS total_cents,
                    COUNT(*) AS txn_count
                FROM transactions
                WHERE tax_deductible = 1
                  AND txn_type = 'expense'
                  AND tax_year = ?
                GROUP BY COALESCE(tax_category, 'Uncategorized')
                ORDER BY tax_category ASC
                """,
                (tax_year,),
            ).fetchall()
            return [dict(row) for row in rows]

    def tax_detail(self, tax_year: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    txn_id,
                    txn_date,
                    COALESCE(NULLIF(description, ''), payee, '') AS description,
                    amount_cents,
                    tax_category,
                    tax_note,
                    receipt_uri
                FROM transactions
                WHERE tax_deductible = 1
                  AND txn_type = 'expense'
                  AND tax_year = ?
                ORDER BY txn_date ASC, txn_id ASC
                """,
                (tax_year,),
            ).fetchall()
            return [dict(row) for row in rows]
