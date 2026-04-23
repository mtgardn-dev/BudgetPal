from __future__ import annotations

import sqlite3

from core.persistence.db import BudgetPalDatabase


class AccountsRepository:
    DEFAULT_INSTITUTION_NAME = "Default Institution"

    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    @staticmethod
    def _normalize_account_type(account_type: str) -> str:
        normalized = str(account_type or "").strip().lower()
        if not normalized:
            raise ValueError("Account type is required.")
        return normalized

    @staticmethod
    def _normalize_name(name: str, field_name: str) -> str:
        normalized = str(name or "").strip()
        if not normalized:
            raise ValueError(f"{field_name} is required.")
        return normalized

    def _default_institution_id(self, conn) -> int:
        conn.execute(
            """
            INSERT OR IGNORE INTO institutions(name, is_active)
            VALUES (?, 1)
            """,
            (self.DEFAULT_INSTITUTION_NAME,),
        )
        row = conn.execute(
            """
            SELECT institution_id
            FROM institutions
            WHERE lower(trim(name)) = lower(trim(?))
            LIMIT 1
            """,
            (self.DEFAULT_INSTITUTION_NAME,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to resolve default institution.")
        return int(row["institution_id"])

    def list_institutions_active(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT institution_id, name
                FROM institutions
                WHERE is_active = 1
                ORDER BY lower(name) ASC, institution_id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_institution(self, name: str) -> int:
        normalized_name = self._normalize_name(name, "Institution name")
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO institutions(name, is_active)
                VALUES (?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    is_active = 1
                """,
                (normalized_name,),
            )
            row = conn.execute(
                """
                SELECT institution_id
                FROM institutions
                WHERE name = ?
                """,
                (normalized_name,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert institution.")
            return int(row["institution_id"])

    def list_active(
        self,
        account_type: str | None = None,
        *,
        include_external: bool = True,
    ) -> list[dict]:
        with self.db.connection() as conn:
            sql = """
                SELECT
                    a.account_id,
                    a.institution_id,
                    i.name AS institution_name,
                    a.name,
                    a.account_type,
                    a.opening_balance_cents,
                    a.account_number,
                    a.notes,
                    a.cd_start_date,
                    a.cd_interval_count,
                    a.cd_interval_unit,
                    a.cd_interest_rate_bps,
                    a.is_external
                FROM accounts a
                LEFT JOIN institutions i ON i.institution_id = a.institution_id
                WHERE a.is_active = 1
            """
            params: list[object] = []
            if not include_external:
                sql += " AND COALESCE(a.is_external, 0) = 0"
            if account_type:
                sql += " AND lower(trim(a.account_type)) = ?"
                params.append(self._normalize_account_type(account_type))
            sql += " ORDER BY lower(coalesce(i.name, '')), lower(a.name), a.account_id"
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def get_by_id(self, account_id: int) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    a.account_id,
                    a.institution_id,
                    i.name AS institution_name,
                    a.name,
                    a.account_type,
                    a.opening_balance_cents,
                    a.account_number,
                    a.notes,
                    a.cd_start_date,
                    a.cd_interval_count,
                    a.cd_interval_unit,
                    a.cd_interest_rate_bps,
                    a.is_external,
                    a.is_active
                FROM accounts a
                LEFT JOIN institutions i ON i.institution_id = a.institution_id
                WHERE a.account_id = ?
                """,
                (int(account_id),),
            ).fetchone()
            return dict(row) if row else None

    def find_by_name(
        self,
        name: str,
        *,
        institution_id: int | None = None,
        account_type: str | None = None,
    ) -> dict | None:
        normalized_name = self._normalize_name(name, "Account name")
        with self.db.connection() as conn:
            sql = """
                SELECT
                    a.account_id,
                    a.institution_id,
                    i.name AS institution_name,
                    a.name,
                    a.account_type,
                    a.opening_balance_cents,
                    a.account_number,
                    a.notes,
                    a.is_external
                FROM accounts a
                LEFT JOIN institutions i ON i.institution_id = a.institution_id
                WHERE lower(trim(a.name)) = lower(trim(?))
                  AND a.is_active = 1
            """
            params: list[object] = [normalized_name]
            if institution_id is not None:
                sql += " AND a.institution_id = ?"
                params.append(int(institution_id))
            if account_type:
                sql += " AND lower(trim(a.account_type)) = ?"
                params.append(self._normalize_account_type(account_type))
            sql += " ORDER BY a.account_id ASC LIMIT 1"
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def upsert(
        self,
        name: str,
        account_type: str,
        opening_balance_cents: int = 0,
        *,
        institution_id: int | None = None,
        account_number: str | None = None,
        notes: str | None = None,
        cd_start_date: str | None = None,
        cd_interval_count: int | None = None,
        cd_interval_unit: str | None = None,
        cd_interest_rate_bps: int | None = None,
        is_external: bool = False,
    ) -> int:
        normalized_name = self._normalize_name(name, "Account name")
        normalized_type = self._normalize_account_type(account_type)
        normalized_account_number = str(account_number or "").strip() or None
        normalized_notes = str(notes or "").strip() or None
        normalized_cd_start = str(cd_start_date or "").strip() or None
        normalized_cd_interval_count = int(cd_interval_count) if cd_interval_count is not None else None
        normalized_cd_interval_unit = str(cd_interval_unit or "").strip().lower() or None
        normalized_cd_interest_bps = (
            int(cd_interest_rate_bps) if cd_interest_rate_bps is not None else None
        )
        with self.db.connection() as conn:
            effective_institution_id = (
                int(institution_id)
                if institution_id is not None
                else self._default_institution_id(conn)
            )
            conn.execute(
                """
                INSERT INTO accounts(
                    institution_id,
                    name,
                    account_type,
                    opening_balance_cents,
                    account_number,
                    notes,
                    cd_start_date,
                    cd_interval_count,
                    cd_interval_unit,
                    cd_interest_rate_bps,
                    is_external,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(institution_id, name)
                DO UPDATE SET
                    account_type = excluded.account_type,
                    opening_balance_cents = excluded.opening_balance_cents,
                    account_number = excluded.account_number,
                    notes = excluded.notes,
                    cd_start_date = excluded.cd_start_date,
                    cd_interval_count = excluded.cd_interval_count,
                    cd_interval_unit = excluded.cd_interval_unit,
                    cd_interest_rate_bps = excluded.cd_interest_rate_bps,
                    is_external = excluded.is_external,
                    is_active = 1
                """,
                (
                    effective_institution_id,
                    normalized_name,
                    normalized_type,
                    int(opening_balance_cents),
                    normalized_account_number,
                    normalized_notes,
                    normalized_cd_start,
                    normalized_cd_interval_count,
                    normalized_cd_interval_unit,
                    normalized_cd_interest_bps,
                    1 if is_external else 0,
                ),
            )
            row = conn.execute(
                """
                SELECT account_id
                FROM accounts
                WHERE institution_id = ? AND name = ?
                """,
                (effective_institution_id, normalized_name),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert account.")
            return int(row["account_id"])

    def update(
        self,
        *,
        account_id: int,
        institution_id: int,
        name: str,
        account_type: str,
        opening_balance_cents: int,
        account_number: str | None = None,
        notes: str | None = None,
        cd_start_date: str | None = None,
        cd_interval_count: int | None = None,
        cd_interval_unit: str | None = None,
        cd_interest_rate_bps: int | None = None,
        is_external: bool = False,
    ) -> int:
        normalized_name = self._normalize_name(name, "Account name")
        normalized_type = self._normalize_account_type(account_type)
        normalized_account_number = str(account_number or "").strip() or None
        normalized_notes = str(notes or "").strip() or None
        normalized_cd_start = str(cd_start_date or "").strip() or None
        normalized_cd_interval_count = int(cd_interval_count) if cd_interval_count is not None else None
        normalized_cd_interval_unit = str(cd_interval_unit or "").strip().lower() or None
        normalized_cd_interest_bps = (
            int(cd_interest_rate_bps) if cd_interest_rate_bps is not None else None
        )
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE accounts
                SET institution_id = ?,
                    name = ?,
                    account_type = ?,
                    opening_balance_cents = ?,
                    account_number = ?,
                    notes = ?,
                    cd_start_date = ?,
                    cd_interval_count = ?,
                    cd_interval_unit = ?,
                    cd_interest_rate_bps = ?,
                    is_external = ?,
                    is_active = 1
                WHERE account_id = ?
                """,
                (
                    int(institution_id),
                    normalized_name,
                    normalized_type,
                    int(opening_balance_cents),
                    normalized_account_number,
                    normalized_notes,
                    normalized_cd_start,
                    normalized_cd_interval_count,
                    normalized_cd_interval_unit,
                    normalized_cd_interest_bps,
                    1 if is_external else 0,
                    int(account_id),
                ),
            )
            return int(cur.rowcount or 0)

    def delete(self, account_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM accounts WHERE account_id = ?",
                (int(account_id),),
            )
            return int(cur.rowcount or 0)

    def deactivate(self, account_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE accounts
                SET is_active = 0
                WHERE account_id = ?
                """,
                (int(account_id),),
            )
            return int(cur.rowcount or 0)

    def get_reference_counts(self, account_id: int) -> dict[str, int]:
        with self.db.connection() as conn:
            txn_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE account_id = ?",
                    (int(account_id),),
                ).fetchone()[0]
            )
            income_def_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM income_definitions WHERE account_id = ?",
                    (int(account_id),),
                ).fetchone()[0]
            )
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            account_month_settings_count = 0
            if "account_month_settings" in tables:
                account_month_settings_count += int(
                    conn.execute(
                        "SELECT COUNT(*) FROM account_month_settings WHERE account_id = ?",
                        (int(account_id),),
                    ).fetchone()[0]
                )
            if "checking_month_settings" in tables:
                account_month_settings_count += int(
                    conn.execute(
                        "SELECT COUNT(*) FROM checking_month_settings WHERE account_id = ?",
                        (int(account_id),),
                    ).fetchone()[0]
                )
            return {
                "transactions": txn_count,
                "income_definitions": income_def_count,
                "account_month_settings": account_month_settings_count,
            }

    def delete_or_deactivate(self, account_id: int) -> str:
        try:
            deleted = self.delete(account_id)
            if deleted > 0:
                return "deleted"
            return "missing"
        except sqlite3.IntegrityError:
            deactivated = self.deactivate(account_id)
            if deactivated > 0:
                return "deactivated"
            return "missing"
