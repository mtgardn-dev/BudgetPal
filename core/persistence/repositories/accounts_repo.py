from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class AccountsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def list_active(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT account_id, name, account_type, opening_balance_cents
                FROM accounts
                WHERE is_active = 1
                ORDER BY name ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def find_by_name(self, name: str) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT account_id, name, account_type, opening_balance_cents
                FROM accounts
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
            return dict(row) if row else None

    def upsert(self, name: str, account_type: str, opening_balance_cents: int = 0) -> int:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts(name, account_type, opening_balance_cents, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(name)
                DO UPDATE SET
                    account_type = excluded.account_type,
                    opening_balance_cents = excluded.opening_balance_cents,
                    is_active = 1
                """,
                (name.strip(), account_type.strip(), opening_balance_cents),
            )
            row = conn.execute(
                "SELECT account_id FROM accounts WHERE name = ?",
                (name.strip(),),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert account")
            return int(row["account_id"])
