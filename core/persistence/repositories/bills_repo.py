from __future__ import annotations

from datetime import date

from core.persistence.db import BudgetPalDatabase


class BillsRepository:
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
        start_date: str | None = None,
        interval_count: int = 1,
        interval_unit: str = "months",
    ) -> int:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Bill name is required.")

        normalized_interval_count = max(1, int(interval_count or 1))
        normalized_interval_unit = self._normalized_interval_unit(interval_unit)
        effective_due_day = due_day
        if effective_due_day is None and start_date:
            try:
                effective_due_day = int(str(start_date).split("-")[2])
            except (TypeError, ValueError, IndexError):
                effective_due_day = None
        effective_frequency = (
            str(frequency).strip()
            if str(frequency).strip()
            else f"{normalized_interval_count} {normalized_interval_unit}"
        )

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
                            start_date = ?,
                            interval_count = ?,
                            interval_unit = ?,
                            default_amount_cents = ?,
                            category_id = ?,
                            autopay = ?,
                            payee_match = ?,
                            is_active = 1,
                            notes = ?
                        WHERE bill_id = ?
                        """,
                        (
                            normalized_name,
                            effective_frequency,
                            effective_due_day,
                            start_date,
                            normalized_interval_count,
                            normalized_interval_unit,
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
                    start_date,
                    interval_count,
                    interval_unit,
                    default_amount_cents,
                    category_id,
                    autopay,
                    payee_match,
                    source_system,
                    source_uid,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_name,
                    effective_frequency,
                    effective_due_day,
                    start_date,
                    normalized_interval_count,
                    normalized_interval_unit,
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

    def add_manual_bill(
        self,
        *,
        name: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        default_amount_cents: int | None,
        category_id: int | None,
        notes: str | None,
    ) -> int:
        return self.upsert_bill(
            name=name,
            frequency="",
            due_day=None,
            default_amount_cents=default_amount_cents,
            category_id=category_id,
            source_system="budgetpal",
            source_uid=None,
            notes=notes,
            start_date=start_date,
            interval_count=interval_count,
            interval_unit=interval_unit,
        )

    def update_bill_definition(
        self,
        *,
        bill_id: int,
        name: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        default_amount_cents: int | None,
        category_id: int | None,
        notes: str | None,
    ) -> int:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Bill name is required.")
        normalized_interval_count = max(1, int(interval_count or 1))
        normalized_interval_unit = self._normalized_interval_unit(interval_unit)
        due_day = int(start_date.split("-")[2])
        frequency = f"{normalized_interval_count} {normalized_interval_unit}"

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE bills
                SET name = ?,
                    start_date = ?,
                    due_day = ?,
                    interval_count = ?,
                    interval_unit = ?,
                    frequency = ?,
                    default_amount_cents = ?,
                    category_id = ?,
                    notes = ?,
                    is_active = 1
                WHERE bill_id = ?
                """,
                (
                    normalized_name,
                    start_date,
                    due_day,
                    normalized_interval_count,
                    normalized_interval_unit,
                    frequency,
                    default_amount_cents,
                    category_id,
                    notes,
                    int(bill_id),
                ),
            )
            return int(cur.rowcount)

    def delete_bill(self, bill_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM bills WHERE bill_id = ?",
                (int(bill_id),),
            )
            return int(cur.rowcount)

    def update_category_for_source(
        self,
        *,
        source_system: str,
        source_uid: str,
        category_id: int | None,
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE bills
                SET category_id = ?
                WHERE source_system = ? AND source_uid = ?
                """,
                (category_id, source_system, source_uid),
            )
            return int(cur.rowcount)

    def list_bill_definitions(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    b.bill_id,
                    b.name,
                    b.start_date,
                    b.due_day,
                    b.interval_count,
                    b.interval_unit,
                    b.default_amount_cents,
                    b.category_id,
                    c.name AS category_name,
                    b.notes,
                    b.source_system
                FROM bills b
                LEFT JOIN categories c ON c.category_id = b.category_id
                WHERE b.is_active = 1
                ORDER BY b.name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def generate_month_occurrences(self, year: int, month: int) -> int:
        count = 0
        with self.db.connection() as conn:
            bills = conn.execute(
                """
                SELECT bill_id, due_day, start_date, default_amount_cents
                FROM bills
                WHERE is_active = 1
                """
            ).fetchall()

            for row in bills:
                day = row["due_day"]
                if day is None and row["start_date"]:
                    try:
                        day = int(str(row["start_date"]).split("-")[2])
                    except (TypeError, ValueError, IndexError):
                        day = 1
                day = int(day or 1)
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
                if conn.execute("SELECT changes()").fetchone()[0]:
                    count += 1

        return count

    def list_occurrences(self, year: int, month: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    bo.bill_occurrence_id,
                    bo.bill_id,
                    b.name,
                    b.category_id,
                    c.name AS category_name,
                    b.interval_count,
                    b.interval_unit,
                    bo.expected_date,
                    bo.expected_amount_cents,
                    bo.status,
                    bo.paid_date,
                    bo.paid_amount_cents,
                    b.autopay,
                    b.source_system,
                    bo.note,
                    b.notes AS definition_notes
                FROM bill_occurrences bo
                JOIN bills b ON b.bill_id = bo.bill_id
                LEFT JOIN categories c ON c.category_id = b.category_id
                WHERE bo.year = ? AND bo.month = ?
                ORDER BY bo.expected_date ASC, b.name ASC
                """,
                (year, month),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_occurrence_if_missing(
        self,
        *,
        bill_id: int,
        year: int,
        month: int,
        expected_date: str | None,
        expected_amount_cents: int | None,
    ) -> bool:
        with self.db.connection() as conn:
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
                    int(bill_id),
                    int(year),
                    int(month),
                    expected_date,
                    expected_amount_cents,
                ),
            )
            return bool(conn.execute("SELECT changes()").fetchone()[0])

    def update_occurrence(
        self,
        *,
        bill_occurrence_id: int,
        expected_date: str,
        expected_amount_cents: int | None,
        note: str | None,
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE bill_occurrences
                SET expected_date = ?,
                    expected_amount_cents = ?,
                    note = ?,
                    status = CASE
                        WHEN status = 'paid' THEN status
                        WHEN ? <> expected_amount_cents THEN 'adjusted'
                        ELSE status
                    END
                WHERE bill_occurrence_id = ?
                """,
                (
                    expected_date,
                    expected_amount_cents,
                    note,
                    expected_amount_cents,
                    int(bill_occurrence_id),
                ),
            )
            return int(cur.rowcount)

    def delete_occurrence(self, bill_occurrence_id: int) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM bill_occurrences WHERE bill_occurrence_id = ?",
                (int(bill_occurrence_id),),
            )
            return int(cur.rowcount)

    def delete_occurrences_for_month(
        self,
        year: int,
        month: int,
        source_system: str | None = None,
    ) -> int:
        with self.db.connection() as conn:
            if source_system is None:
                cur = conn.execute(
                    """
                    DELETE FROM bill_occurrences
                    WHERE year = ? AND month = ?
                    """,
                    (int(year), int(month)),
                )
            else:
                cur = conn.execute(
                    """
                    DELETE FROM bill_occurrences
                    WHERE bill_occurrence_id IN (
                        SELECT bo.bill_occurrence_id
                        FROM bill_occurrences bo
                        JOIN bills b ON b.bill_id = bo.bill_id
                        WHERE bo.year = ?
                          AND bo.month = ?
                          AND lower(trim(b.source_system)) = lower(trim(?))
                    )
                    """,
                    (int(year), int(month), str(source_system)),
                )
            return int(cur.rowcount)

    def get_month_auto_refresh_enabled(self, year: int, month: int) -> bool:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT auto_refresh_enabled
                FROM bills_month_settings
                WHERE year = ? AND month = ?
                """,
                (int(year), int(month)),
            ).fetchone()
            if row is None:
                return True
            return bool(int(row["auto_refresh_enabled"]))

    def set_month_auto_refresh_enabled(self, year: int, month: int, enabled: bool) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO bills_month_settings(year, month, auto_refresh_enabled, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(year, month) DO UPDATE SET
                    auto_refresh_enabled = excluded.auto_refresh_enabled,
                    updated_at = datetime('now')
                """,
                (int(year), int(month), int(bool(enabled))),
            )
