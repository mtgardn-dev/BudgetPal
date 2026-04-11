from __future__ import annotations

import sqlite3

from core.persistence.db import BudgetPalDatabase


class CategoriesRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def list_active(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT category_id, name, is_income
                FROM categories
                WHERE is_active = 1
                ORDER BY is_income DESC, lower(name) ASC, category_id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def find_by_name(self, name: str) -> dict | None:
        normalized = name.strip()
        if not normalized:
            return None
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT category_id, name, is_income
                FROM categories
                WHERE lower(name) = lower(?)
                ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, category_id ASC
                LIMIT 1
                """,
                (normalized, normalized),
            ).fetchone()
            return dict(row) if row else None

    def find_case_variants(self, name: str, exclude_category_id: int | None = None) -> list[dict]:
        normalized = name.strip()
        if not normalized:
            return []
        with self.db.connection() as conn:
            sql = """
                SELECT category_id, name, is_income
                FROM categories
                WHERE lower(name) = lower(?)
            """
            params: list[object] = [normalized]
            if exclude_category_id is not None:
                sql += " AND category_id <> ?"
                params.append(int(exclude_category_id))
            sql += " ORDER BY category_id ASC"
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def get_by_id(self, category_id: int) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT category_id, name, is_income, is_active
                FROM categories
                WHERE category_id = ?
                """,
                (category_id,),
            ).fetchone()
            return dict(row) if row else None

    def upsert(self, name: str, is_income: bool = False) -> int:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Category name is required.")

        with self.db.connection() as conn:
            existing = conn.execute(
                """
                SELECT category_id
                FROM categories
                WHERE lower(name) = lower(?)
                ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, category_id ASC
                LIMIT 1
                """,
                (normalized, normalized),
            ).fetchone()
            if existing:
                category_id = int(existing["category_id"])
                conn.execute(
                    """
                    UPDATE categories
                    SET is_income = ?, is_active = 1
                    WHERE category_id = ?
                    """,
                    (int(is_income), category_id),
                )
                return category_id

            conn.execute(
                """
                INSERT INTO categories(name, is_income, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(name)
                DO UPDATE SET is_income = excluded.is_income, is_active = 1
                """,
                (normalized, int(is_income)),
            )
            row = conn.execute(
                "SELECT category_id FROM categories WHERE name = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert category")
            return int(row["category_id"])

    def update_name(self, category_id: int, name: str) -> int:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Category name is required.")

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE categories
                SET name = ?, is_active = 1
                WHERE category_id = ?
                """,
                (normalized, int(category_id)),
            )
            return int(cur.rowcount)

    def delete(self, category_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM categories
                WHERE category_id = ?
                """,
                (int(category_id),),
            )
            return int(cur.rowcount)

    @staticmethod
    def _merge_notes(left: str | None, right: str | None) -> str | None:
        left_clean = str(left or "").strip()
        right_clean = str(right or "").strip()
        if not left_clean and not right_clean:
            return None
        if not left_clean:
            return right_clean
        if not right_clean:
            return left_clean
        if right_clean in left_clean:
            return left_clean
        return f"{left_clean}; {right_clean}"

    def merge_category_into(self, source_category_id: int, target_category_id: int) -> int:
        source_id = int(source_category_id)
        target_id = int(target_category_id)
        if source_id == target_id:
            raise ValueError("Source and target category must be different.")

        with self.db.connection() as conn:
            source = conn.execute(
                "SELECT category_id, name FROM categories WHERE category_id = ?",
                (source_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT category_id, name FROM categories WHERE category_id = ?",
                (target_id,),
            ).fetchone()
            if source is None or target is None:
                raise ValueError("Source or target category no longer exists.")

            # Merge month allocation rows that have UNIQUE(budget_month_id, category_id).
            source_lines = conn.execute(
                """
                SELECT budget_line_id, budget_month_id, planned_cents, note
                FROM budget_lines
                WHERE category_id = ?
                """,
                (source_id,),
            ).fetchall()
            for src_row in source_lines:
                target_line = conn.execute(
                    """
                    SELECT budget_line_id, planned_cents, note
                    FROM budget_lines
                    WHERE budget_month_id = ? AND category_id = ?
                    """,
                    (int(src_row["budget_month_id"]), target_id),
                ).fetchone()
                if target_line:
                    merged_planned = int(target_line["planned_cents"]) + int(src_row["planned_cents"])
                    merged_note = self._merge_notes(target_line["note"], src_row["note"])
                    conn.execute(
                        """
                        UPDATE budget_lines
                        SET planned_cents = ?, note = ?, updated_at = datetime('now')
                        WHERE budget_line_id = ?
                        """,
                        (merged_planned, merged_note, int(target_line["budget_line_id"])),
                    )
                    conn.execute(
                        "DELETE FROM budget_lines WHERE budget_line_id = ?",
                        (int(src_row["budget_line_id"]),),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE budget_lines
                        SET category_id = ?, updated_at = datetime('now')
                        WHERE budget_line_id = ?
                        """,
                        (target_id, int(src_row["budget_line_id"])),
                    )

            # Merge global budget allocation definitions with UNIQUE(category_id).
            source_def = conn.execute(
                """
                SELECT definition_id, default_amount_cents, note
                FROM budget_category_definitions
                WHERE category_id = ?
                """,
                (source_id,),
            ).fetchone()
            if source_def:
                target_def = conn.execute(
                    """
                    SELECT definition_id, default_amount_cents, note
                    FROM budget_category_definitions
                    WHERE category_id = ?
                    """,
                    (target_id,),
                ).fetchone()
                if target_def:
                    merged_default_amount = int(target_def["default_amount_cents"]) + int(
                        source_def["default_amount_cents"]
                    )
                    merged_note = self._merge_notes(target_def["note"], source_def["note"])
                    conn.execute(
                        """
                        UPDATE budget_category_definitions
                        SET default_amount_cents = ?, note = ?, updated_at = datetime('now')
                        WHERE definition_id = ?
                        """,
                        (merged_default_amount, merged_note, int(target_def["definition_id"])),
                    )
                    conn.execute(
                        "DELETE FROM budget_category_definitions WHERE definition_id = ?",
                        (int(source_def["definition_id"]),),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE budget_category_definitions
                        SET category_id = ?, updated_at = datetime('now')
                        WHERE definition_id = ?
                        """,
                        (target_id, int(source_def["definition_id"])),
                    )

            # Repoint the remaining FK references.
            conn.execute(
                "UPDATE transactions SET category_id = ? WHERE category_id = ?",
                (target_id, source_id),
            )
            conn.execute(
                "UPDATE transaction_splits SET category_id = ? WHERE category_id = ?",
                (target_id, source_id),
            )
            conn.execute(
                "UPDATE bills SET category_id = ? WHERE category_id = ?",
                (target_id, source_id),
            )
            conn.execute(
                "UPDATE income_definitions SET category_id = ? WHERE category_id = ?",
                (target_id, source_id),
            )

            try:
                deleted = conn.execute(
                    "DELETE FROM categories WHERE category_id = ?",
                    (source_id,),
                ).rowcount
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(
                    "Could not merge category due to remaining references."
                ) from exc
            return int(deleted)
