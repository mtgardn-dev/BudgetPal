from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class BudgetAllocationsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def ensure_month(self, year: int, month: int) -> int:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO budget_months(year, month, starting_balance_cents)
                VALUES (?, ?, 0)
                """,
                (int(year), int(month)),
            )
            row = conn.execute(
                """
                SELECT budget_month_id
                FROM budget_months
                WHERE year = ? AND month = ?
                """,
                (int(year), int(month)),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to ensure budget month.")
            return int(row["budget_month_id"])

    def list_available_months(self) -> list[str]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT printf('%04d-%02d', year, month) AS year_month
                FROM budget_months
                ORDER BY year DESC, month DESC
                """
            ).fetchall()
            return [str(row["year_month"]) for row in rows if row["year_month"]]

    def list_definitions(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    d.definition_id,
                    d.category_id,
                    c.name AS category_name,
                    d.default_amount_cents,
                    d.note
                FROM budget_category_definitions d
                JOIN categories c ON c.category_id = d.category_id
                WHERE d.is_active = 1
                ORDER BY c.name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_definition(
        self,
        *,
        category_id: int,
        default_amount_cents: int,
        note: str | None,
    ) -> int:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO budget_category_definitions(
                    category_id,
                    default_amount_cents,
                    note,
                    is_active
                ) VALUES (?, ?, ?, 1)
                ON CONFLICT(category_id) DO UPDATE SET
                    default_amount_cents = excluded.default_amount_cents,
                    note = excluded.note,
                    is_active = 1,
                    updated_at = datetime('now')
                """,
                (int(category_id), int(default_amount_cents), note),
            )
            row = conn.execute(
                """
                SELECT definition_id
                FROM budget_category_definitions
                WHERE category_id = ?
                """,
                (int(category_id),),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert budget category definition.")
            return int(row["definition_id"])

    def delete_definition(self, definition_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM budget_category_definitions WHERE definition_id = ?",
                (int(definition_id),),
            )
            return int(cur.rowcount or 0)

    def list_month_allocations(self, year: int, month: int) -> list[dict]:
        month_id = self.ensure_month(year, month)
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    bl.budget_line_id,
                    bl.budget_month_id,
                    bl.category_id,
                    c.name AS category_name,
                    bl.planned_cents,
                    bl.note
                FROM budget_lines bl
                JOIN categories c ON c.category_id = bl.category_id
                WHERE bl.budget_month_id = ?
                ORDER BY c.name COLLATE NOCASE ASC
                """,
                (int(month_id),),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_month_allocation(
        self,
        *,
        year: int,
        month: int,
        category_id: int,
        planned_cents: int,
        note: str | None,
    ) -> int:
        month_id = self.ensure_month(year, month)
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO budget_lines(
                    budget_month_id,
                    category_id,
                    planned_cents,
                    note
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(budget_month_id, category_id) DO UPDATE SET
                    planned_cents = excluded.planned_cents,
                    note = excluded.note,
                    updated_at = datetime('now')
                """,
                (int(month_id), int(category_id), int(planned_cents), note),
            )
            row = conn.execute(
                """
                SELECT budget_line_id
                FROM budget_lines
                WHERE budget_month_id = ? AND category_id = ?
                """,
                (int(month_id), int(category_id)),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert month budget allocation.")
            return int(row["budget_line_id"])

    def update_month_allocation(
        self,
        *,
        budget_line_id: int,
        category_id: int,
        planned_cents: int,
        note: str | None,
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE budget_lines
                SET category_id = ?,
                    planned_cents = ?,
                    note = ?,
                    updated_at = datetime('now')
                WHERE budget_line_id = ?
                """,
                (int(category_id), int(planned_cents), note, int(budget_line_id)),
            )
            return int(cur.rowcount or 0)

    def delete_month_allocation(self, budget_line_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM budget_lines WHERE budget_line_id = ?",
                (int(budget_line_id),),
            )
            return int(cur.rowcount or 0)

    def delete_month_allocations(self, year: int, month: int) -> int:
        month_id = self.ensure_month(year, month)
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM budget_lines WHERE budget_month_id = ?",
                (int(month_id),),
            )
            return int(cur.rowcount or 0)

    def regenerate_for_month(self, year: int, month: int) -> tuple[int, int]:
        month_id = self.ensure_month(year, month)
        with self.db.connection() as conn:
            deleted_cur = conn.execute(
                "DELETE FROM budget_lines WHERE budget_month_id = ?",
                (int(month_id),),
            )
            deleted = int(deleted_cur.rowcount or 0)

            conn.execute(
                """
                INSERT INTO budget_lines(
                    budget_month_id,
                    category_id,
                    planned_cents,
                    note
                )
                SELECT
                    ?,
                    d.category_id,
                    d.default_amount_cents,
                    d.note
                FROM budget_category_definitions d
                WHERE d.is_active = 1
                """,
                (int(month_id),),
            )
            inserted = int(conn.execute("SELECT changes()").fetchone()[0])
            return deleted, inserted
