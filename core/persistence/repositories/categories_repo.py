from __future__ import annotations

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
                ORDER BY is_income DESC, name ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def find_by_name(self, name: str) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT category_id, name, is_income FROM categories WHERE name = ?",
                (name,),
            ).fetchone()
            return dict(row) if row else None

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
