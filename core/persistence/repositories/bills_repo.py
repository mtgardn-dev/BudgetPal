from __future__ import annotations

from datetime import date

from core.persistence.db import BudgetPalDatabase


class BillsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def upsert_bill(
        self,
        *,
        name: str,
        frequency: str,
        due_day: int | None,
        default_amount_cents: int | None,
        category_id: int | None = None,
        autopay: bool = False,
        payee_match: str | None = None,
        source_system: str = "budgetpal",
        source_uid: str | None = None,
        notes: str | None = None,
    ) -> int:
        with self.db.connection() as conn:
            if source_uid and source_system:
                existing = conn.execute(
                    """
                    SELECT bill_id FROM bills
                    WHERE source_system = ? AND source_uid = ?
                    """,
                    (source_system, source_uid),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE bills
                        SET name = ?,
                            frequency = ?,
                            due_day = ?,
                            default_amount_cents = ?,
                            category_id = ?,
                            autopay = ?,
                            payee_match = ?,
                            is_active = 1,
                            notes = ?
                        WHERE bill_id = ?
                        """,
                        (
                            name,
                            frequency,
                            due_day,
                            default_amount_cents,
                            category_id,
                            int(autopay),
                            payee_match,
                            notes,
                            int(existing["bill_id"]),
                        ),
                    )
                    return int(existing["bill_id"])

            cur = conn.execute(
                """
                INSERT INTO bills(
                    name,
                    frequency,
                    due_day,
                    default_amount_cents,
                    category_id,
                    autopay,
                    payee_match,
                    source_system,
                    source_uid,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    frequency,
                    due_day,
                    default_amount_cents,
                    category_id,
                    int(autopay),
                    payee_match,
                    source_system,
                    source_uid,
                    notes,
                ),
            )
            return int(cur.lastrowid)

    def generate_month_occurrences(self, year: int, month: int) -> int:
        count = 0
        with self.db.connection() as conn:
            bills = conn.execute(
                """
                SELECT bill_id, due_day, default_amount_cents
                FROM bills
                WHERE is_active = 1
                """
            ).fetchall()

            for row in bills:
                day = int(row["due_day"] or 1)
                expected_date = date(year, month, min(max(day, 1), 28)).isoformat()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO bill_occurrences(
                        bill_id,
                        year,
                        month,
                        expected_date,
                        expected_amount_cents,
                        status
                    ) VALUES (?, ?, ?, ?, ?, 'expected')
                    """,
                    (
                        int(row["bill_id"]),
                        year,
                        month,
                        expected_date,
                        row["default_amount_cents"],
                    ),
                )
                count += 1

        return count

    def list_occurrences(self, year: int, month: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    bo.bill_occurrence_id,
                    b.name,
                    bo.expected_date,
                    bo.expected_amount_cents,
                    bo.status,
                    bo.paid_date,
                    bo.paid_amount_cents,
                    b.autopay,
                    b.source_system,
                    b.notes
                FROM bill_occurrences bo
                JOIN bills b ON b.bill_id = bo.bill_id
                WHERE bo.year = ? AND bo.month = ?
                ORDER BY bo.expected_date ASC, b.name ASC
                """,
                (year, month),
            ).fetchall()
            return [dict(row) for row in rows]
