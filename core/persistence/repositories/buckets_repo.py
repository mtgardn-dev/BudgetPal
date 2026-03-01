from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class BucketsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def upsert_bucket(
        self, name: str, target_cents: int | None = None, target_date: str | None = None
    ) -> int:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO savings_buckets(name, target_cents, target_date, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(name)
                DO UPDATE SET
                    target_cents = excluded.target_cents,
                    target_date = excluded.target_date,
                    is_active = 1
                """,
                (name.strip(), target_cents, target_date),
            )
            row = conn.execute(
                "SELECT bucket_id FROM savings_buckets WHERE name = ?",
                (name.strip(),),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert bucket")
            return int(row["bucket_id"])
