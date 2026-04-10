from __future__ import annotations

from core.persistence.db import BudgetPalDatabase


class IncomeRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    @staticmethod
    def _normalized_interval_unit(interval_unit: str | None) -> str:
        raw = str(interval_unit or "").strip().lower()
        if raw in {"day", "days"}:
            return "days"
        if raw in {"week", "weeks"}:
            return "weeks"
        if raw in {"month", "months"}:
            return "months"
        if raw in {"year", "years"}:
            return "years"
        if raw in {"once", "one-time", "onetime"}:
            return "once"
        return "months"

    def add_definition(
        self,
        *,
        description: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        default_amount_cents: int | None,
        category_id: int | None,
        account_id: int,
        notes: str | None,
        source_system: str = "budgetpal",
    ) -> int:
        normalized_description = str(description).strip()
        if not normalized_description:
            raise ValueError("Income description is required.")
        normalized_interval_count = max(1, int(interval_count or 1))
        normalized_interval_unit = self._normalized_interval_unit(interval_unit)

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO income_definitions(
                    description,
                    default_amount_cents,
                    category_id,
                    account_id,
                    start_date,
                    interval_count,
                    interval_unit,
                    source_system,
                    is_active,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    normalized_description,
                    default_amount_cents,
                    category_id,
                    int(account_id),
                    start_date,
                    normalized_interval_count,
                    normalized_interval_unit,
                    str(source_system or "budgetpal").strip() or "budgetpal",
                    notes,
                ),
            )
            return int(cur.lastrowid)

    def update_definition(
        self,
        *,
        income_id: int,
        description: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        default_amount_cents: int | None,
        category_id: int | None,
        account_id: int,
        notes: str | None,
    ) -> int:
        normalized_description = str(description).strip()
        if not normalized_description:
            raise ValueError("Income description is required.")
        normalized_interval_count = max(1, int(interval_count or 1))
        normalized_interval_unit = self._normalized_interval_unit(interval_unit)

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE income_definitions
                SET description = ?,
                    start_date = ?,
                    interval_count = ?,
                    interval_unit = ?,
                    default_amount_cents = ?,
                    category_id = ?,
                    account_id = ?,
                    notes = ?,
                    is_active = 1
                WHERE income_id = ?
                """,
                (
                    normalized_description,
                    start_date,
                    normalized_interval_count,
                    normalized_interval_unit,
                    default_amount_cents,
                    category_id,
                    int(account_id),
                    notes,
                    int(income_id),
                ),
            )
            return int(cur.rowcount)

    def delete_definition(self, income_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM income_definitions WHERE income_id = ?",
                (int(income_id),),
            )
            return int(cur.rowcount)

    def list_definitions(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    i.income_id,
                    i.description,
                    i.default_amount_cents,
                    i.category_id,
                    c.name AS category_name,
                    i.account_id,
                    a.name AS account_name,
                    i.start_date,
                    i.interval_count,
                    i.interval_unit,
                    i.source_system,
                    i.notes
                FROM income_definitions i
                LEFT JOIN categories c ON c.category_id = i.category_id
                JOIN accounts a ON a.account_id = i.account_id
                WHERE i.is_active = 1
                ORDER BY i.description COLLATE NOCASE ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_occurrence_if_missing(
        self,
        *,
        income_id: int,
        year: int,
        month: int,
        expected_date: str | None,
        expected_amount_cents: int | None,
    ) -> bool:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO income_occurrences(
                    income_id,
                    year,
                    month,
                    expected_date,
                    expected_amount_cents,
                    status
                ) VALUES (?, ?, ?, ?, ?, 'expected')
                """,
                (
                    int(income_id),
                    int(year),
                    int(month),
                    expected_date,
                    expected_amount_cents,
                ),
            )
            return bool(conn.execute("SELECT changes()").fetchone()[0])

    def list_occurrences(self, year: int, month: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    io.income_occurrence_id,
                    io.income_id,
                    i.description,
                    i.category_id,
                    c.name AS category_name,
                    i.account_id,
                    a.name AS account_name,
                    i.interval_count,
                    i.interval_unit,
                    io.expected_date,
                    io.expected_amount_cents,
                    io.status,
                    io.note,
                    i.notes AS definition_notes,
                    i.source_system
                FROM income_occurrences io
                JOIN income_definitions i ON i.income_id = io.income_id
                LEFT JOIN categories c ON c.category_id = i.category_id
                JOIN accounts a ON a.account_id = i.account_id
                WHERE io.year = ? AND io.month = ?
                ORDER BY io.expected_date ASC, i.description ASC
                """,
                (int(year), int(month)),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_occurrence(
        self,
        *,
        income_occurrence_id: int,
        expected_date: str,
        expected_amount_cents: int | None,
        note: str | None,
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE income_occurrences
                SET expected_date = ?,
                    expected_amount_cents = ?,
                    note = ?,
                    status = CASE
                        WHEN ? <> expected_amount_cents THEN 'adjusted'
                        ELSE status
                    END
                WHERE income_occurrence_id = ?
                """,
                (
                    expected_date,
                    expected_amount_cents,
                    note,
                    expected_amount_cents,
                    int(income_occurrence_id),
                ),
            )
            return int(cur.rowcount)

    def delete_occurrence(self, income_occurrence_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM income_occurrences WHERE income_occurrence_id = ?",
                (int(income_occurrence_id),),
            )
            return int(cur.rowcount)

    def delete_occurrences_for_month(self, year: int, month: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM income_occurrences
                WHERE year = ? AND month = ?
                """,
                (int(year), int(month)),
            )
            return int(cur.rowcount)
