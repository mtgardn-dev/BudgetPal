from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class BudgetsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def ensure_month(self, year: int, month: int, starting_balance_cents: int = 0) -> int:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO budget_months(year, month, starting_balance_cents)
                VALUES (?, ?, ?)
                """,
                (year, month, starting_balance_cents),
            )
            row = conn.execute(
                "SELECT budget_month_id FROM budget_months WHERE year = ? AND month = ?",
                (year, month),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to ensure budget month")
            return int(row["budget_month_id"])

    def get_month(self, year: int, month: int) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT budget_month_id, year, month, starting_balance_cents, notes
                FROM budget_months
                WHERE year = ? AND month = ?
                """,
                (year, month),
            ).fetchone()
            return dict(row) if row else None

    def copy_from_previous_month(self, year: int, month: int) -> None:
        current_id = self.ensure_month(year, month)
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)

        with self.db.connection() as conn:
            previous = conn.execute(
                """
                SELECT bl.category_id, bl.planned_cents
                FROM budget_lines bl
                JOIN budget_months bm ON bm.budget_month_id = bl.budget_month_id
                WHERE bm.year = ? AND bm.month = ?
                """,
                (prev_year, prev_month),
            ).fetchall()

            for row in previous:
                conn.execute(
                    """
                    INSERT INTO budget_lines(budget_month_id, category_id, planned_cents)
                    VALUES (?, ?, ?)
                    ON CONFLICT(budget_month_id, category_id)
                    DO UPDATE SET planned_cents = excluded.planned_cents,
                                  updated_at = datetime('now')
                    """,
                    (current_id, int(row["category_id"]), int(row["planned_cents"])),
                )

    def set_budget_line(self, budget_month_id: int, category_id: int, planned_cents: int) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO budget_lines(budget_month_id, category_id, planned_cents)
                VALUES (?, ?, ?)
                ON CONFLICT(budget_month_id, category_id)
                DO UPDATE SET planned_cents = excluded.planned_cents,
                              updated_at = datetime('now')
                """,
                (budget_month_id, category_id, planned_cents),
            )
