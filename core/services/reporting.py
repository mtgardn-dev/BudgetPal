from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from core.persistence.db import BudgetPalDatabase


class ReportingService:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def export_global_definitions(self, output_dir: Path) -> list[Path]:
        target_dir = Path(output_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        bills_path = target_dir / f"budgetpal_bill_definitions_{timestamp}.csv"
        income_path = target_dir / f"budgetpal_income_definitions_{timestamp}.csv"
        budget_path = target_dir / f"budgetpal_budget_category_definitions_{timestamp}.csv"
        accounts_path = target_dir / f"budgetpal_account_definitions_{timestamp}.csv"

        with sqlite3.connect(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self._write_query_csv(
                conn,
                """
                SELECT
                    b.bill_id AS definition_id,
                    b.name,
                    b.category_id,
                    c.name AS category_name,
                    b.start_date,
                    b.interval_count,
                    b.interval_unit,
                    b.default_amount_cents,
                    b.autopay,
                    b.notes
                FROM bills b
                LEFT JOIN categories c ON c.category_id = b.category_id
                WHERE b.is_active = 1
                  AND lower(trim(b.source_system)) = 'budgetpal'
                ORDER BY lower(coalesce(c.name, '')), lower(b.name), b.bill_id
                """,
                bills_path,
            )
            self._write_query_csv(
                conn,
                """
                SELECT
                    i.income_id AS definition_id,
                    i.description,
                    i.category_id,
                    c.name AS category_name,
                    i.account_id,
                    a.name AS account_name,
                    i.start_date,
                    i.interval_count,
                    i.interval_unit,
                    i.default_amount_cents,
                    i.notes
                FROM income_definitions i
                LEFT JOIN categories c ON c.category_id = i.category_id
                JOIN accounts a ON a.account_id = i.account_id
                WHERE i.is_active = 1
                  AND lower(trim(i.source_system)) = 'budgetpal'
                ORDER BY lower(coalesce(c.name, '')), lower(i.description), i.income_id
                """,
                income_path,
            )
            self._write_query_csv(
                conn,
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
                ORDER BY lower(c.name), d.definition_id
                """,
                budget_path,
            )
            self._write_query_csv(
                conn,
                """
                SELECT
                    a.account_id AS definition_id,
                    a.institution_id,
                    i.name AS institution_name,
                    a.name AS account_name,
                    a.account_type,
                    a.opening_balance_cents,
                    a.line_of_credit_cents,
                    a.account_number,
                    a.notes,
                    a.cd_start_date,
                    a.cd_interval_count,
                    a.cd_interval_unit,
                    a.cd_interest_rate_bps,
                    a.is_external,
                    a.show_on_accounts_tab,
                    a.is_active
                FROM accounts a
                LEFT JOIN institutions i ON i.institution_id = a.institution_id
                WHERE a.is_active = 1
                ORDER BY lower(coalesce(i.name, '')), lower(a.name), a.account_id
                """,
                accounts_path,
            )

        return [bills_path, income_path, budget_path, accounts_path]

    def import_global_definitions(self, definition_type: str, csv_path: Path) -> dict[str, int | str]:
        normalized_type = str(definition_type or "").strip().lower()
        if normalized_type not in {"bills", "budget_allocations", "income", "accounts"}:
            raise ValueError(
                "Definition type must be one of: bills, budget_allocations, income, accounts."
            )

        source_path = Path(csv_path).expanduser()
        if not source_path.exists() or not source_path.is_file():
            raise OSError(f"Definitions CSV is not reachable: {source_path}")

        with source_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            if not fieldnames:
                raise ValueError("CSV header row is missing.")
            rows = list(reader)

        with sqlite3.connect(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            categories_by_id, categories_by_name = self._category_lookup(conn)
            accounts_by_id, accounts_by_name = self._account_lookup(conn)
            institutions_by_id, institutions_by_name = self._institution_lookup(conn)

            if normalized_type == "bills":
                inserted, updated, skipped_blank = self._import_bills(
                    conn, rows, fieldnames, categories_by_id, categories_by_name
                )
            elif normalized_type == "income":
                inserted, updated, skipped_blank = self._import_income(
                    conn,
                    rows,
                    fieldnames,
                    categories_by_id,
                    categories_by_name,
                    accounts_by_id,
                    accounts_by_name,
                )
            elif normalized_type == "accounts":
                inserted, updated, skipped_blank = self._import_accounts(
                    conn,
                    rows,
                    fieldnames,
                    institutions_by_id,
                    institutions_by_name,
                )
            else:
                inserted, updated, skipped_blank = self._import_budget_allocations(
                    conn,
                    rows,
                    fieldnames,
                    categories_by_id,
                    categories_by_name,
                )

        return {
            "definition_type": normalized_type,
            "inserted": inserted,
            "updated": updated,
            "skipped_blank": skipped_blank,
            "rows_total": len(rows),
            "file": str(source_path),
        }

    @staticmethod
    def _normalize_header(header: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(header or "").strip().casefold())

    @classmethod
    def _column_map(cls, fieldnames: list[str]) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for field in fieldnames:
            normalized = cls._normalize_header(field)
            if normalized and normalized not in mapped:
                mapped[normalized] = field
        return mapped

    @classmethod
    def _value(cls, row: dict, column_map: dict[str, str], *candidates: str) -> str:
        for candidate in candidates:
            field = column_map.get(cls._normalize_header(candidate))
            if field is not None:
                return str(row.get(field, "") or "").strip()
        return ""

    @staticmethod
    def _row_is_blank(row: dict) -> bool:
        return all(not str(value or "").strip() for value in row.values())

    @staticmethod
    def _parse_int(raw: str, label: str, row_number: int) -> int:
        text = str(raw or "").strip()
        if not text:
            raise ValueError(f"Row {row_number}: {label} is required.")
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {label} must be an integer.") from exc

    @staticmethod
    def _parse_int_optional(raw: str, label: str, row_number: int) -> int | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {label} must be an integer.") from exc

    @staticmethod
    def _parse_bool(raw: str) -> int:
        text = str(raw or "").strip().casefold()
        if text in {"1", "true", "t", "yes", "y"}:
            return 1
        if text in {"0", "false", "f", "no", "n", ""}:
            return 0
        raise ValueError(f"Boolean value is invalid: '{raw}'")

    @staticmethod
    def _validate_date(raw: str, label: str, row_number: int) -> str:
        text = str(raw or "").strip()
        if not text:
            raise ValueError(f"Row {row_number}: {label} is required.")
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {label} must be YYYY-MM-DD.") from exc
        return text

    @staticmethod
    def _normalize_interval_unit(raw: str) -> str:
        value = str(raw or "").strip().casefold()
        if value in {"day", "days"}:
            return "days"
        if value in {"week", "weeks"}:
            return "weeks"
        if value in {"month", "months"}:
            return "months"
        if value in {"year", "years"}:
            return "years"
        if value in {"once", "one-time", "onetime"}:
            return "once"
        raise ValueError("Interval unit must be days, weeks, months, years, or once.")

    @staticmethod
    def _category_lookup(conn: sqlite3.Connection) -> tuple[dict[int, str], dict[str, int]]:
        rows = conn.execute("SELECT category_id, name FROM categories").fetchall()
        by_id = {int(row["category_id"]): str(row["name"]) for row in rows}
        by_name = {str(row["name"]).casefold(): int(row["category_id"]) for row in rows}
        return by_id, by_name

    @staticmethod
    def _account_lookup(conn: sqlite3.Connection) -> tuple[dict[int, str], dict[str, int]]:
        rows = conn.execute("SELECT account_id, name FROM accounts").fetchall()
        by_id = {int(row["account_id"]): str(row["name"]) for row in rows}
        by_name = {str(row["name"]).casefold(): int(row["account_id"]) for row in rows}
        return by_id, by_name

    @staticmethod
    def _institution_lookup(conn: sqlite3.Connection) -> tuple[dict[int, str], dict[str, int]]:
        rows = conn.execute("SELECT institution_id, name FROM institutions").fetchall()
        by_id = {int(row["institution_id"]): str(row["name"]) for row in rows}
        by_name = {str(row["name"]).casefold(): int(row["institution_id"]) for row in rows}
        return by_id, by_name

    @classmethod
    def _resolve_category_id(
        cls,
        *,
        row: dict,
        column_map: dict[str, str],
        row_number: int,
        categories_by_id: dict[int, str],
        categories_by_name: dict[str, int],
        required: bool,
    ) -> int | None:
        category_id_text = cls._value(row, column_map, "category_id")
        category_name_text = cls._value(row, column_map, "category_name", "category")

        if not category_id_text and not category_name_text:
            if required:
                raise ValueError(f"Row {row_number}: Category is required.")
            return None

        resolved_id: int | None = None
        if category_id_text:
            try:
                parsed_category_id = cls._parse_int(category_id_text, "category_id", row_number)
            except ValueError:
                if not category_name_text:
                    raise
                parsed_category_id = None

            if parsed_category_id is not None:
                if parsed_category_id in categories_by_id:
                    resolved_id = parsed_category_id
                elif not category_name_text:
                    raise ValueError(
                        f"Row {row_number}: category_id {parsed_category_id} does not exist in categories."
                    )

        if category_name_text:
            match = categories_by_name.get(category_name_text.casefold())
            if match is None:
                raise ValueError(
                    f"Row {row_number}: category_name '{category_name_text}' does not exist."
                )
            # Name is authoritative for imports so exported IDs from another DB can remap safely.
            resolved_id = match

        if required and resolved_id is None:
            raise ValueError(f"Row {row_number}: Category is required.")
        return resolved_id

    @classmethod
    def _resolve_account_id(
        cls,
        *,
        row: dict,
        column_map: dict[str, str],
        row_number: int,
        accounts_by_id: dict[int, str],
        accounts_by_name: dict[str, int],
    ) -> int:
        account_id_text = cls._value(row, column_map, "account_id")
        account_name_text = cls._value(row, column_map, "account_name", "account")

        if not account_id_text and not account_name_text:
            raise ValueError(f"Row {row_number}: Account is required.")

        resolved_id: int | None = None
        if account_id_text:
            resolved_id = cls._parse_int(account_id_text, "account_id", row_number)
            if resolved_id not in accounts_by_id:
                raise ValueError(
                    f"Row {row_number}: account_id {resolved_id} does not exist in accounts."
                )

        if account_name_text:
            match = accounts_by_name.get(account_name_text.casefold())
            if match is None:
                raise ValueError(
                    f"Row {row_number}: account_name '{account_name_text}' does not exist."
                )
            if resolved_id is not None and match != resolved_id:
                raise ValueError(f"Row {row_number}: account_id/account_name mismatch.")
            resolved_id = match

        if resolved_id is None:
            raise ValueError(f"Row {row_number}: Account is required.")
        return resolved_id

    @classmethod
    def _import_bills(
        cls,
        conn: sqlite3.Connection,
        rows: list[dict],
        fieldnames: list[str],
        categories_by_id: dict[int, str],
        categories_by_name: dict[str, int],
    ) -> tuple[int, int, int]:
        column_map = cls._column_map(fieldnames)
        inserted = 0
        updated = 0
        skipped_blank = 0

        with conn:
            for index, row in enumerate(rows, start=2):
                if cls._row_is_blank(row):
                    skipped_blank += 1
                    continue

                definition_id = cls._parse_int_optional(
                    cls._value(row, column_map, "definition_id", "bill_id"),
                    "definition_id",
                    index,
                )
                name = cls._value(row, column_map, "name")
                if not name:
                    raise ValueError(f"Row {index}: name is required.")
                start_date = cls._validate_date(
                    cls._value(row, column_map, "start_date", "payment_due"),
                    "start_date",
                    index,
                )
                interval_count = cls._parse_int(
                    cls._value(row, column_map, "interval_count"),
                    "interval_count",
                    index,
                )
                if interval_count < 1:
                    raise ValueError(f"Row {index}: interval_count must be >= 1.")
                try:
                    interval_unit = cls._normalize_interval_unit(
                        cls._value(row, column_map, "interval_unit")
                    )
                except ValueError as exc:
                    raise ValueError(f"Row {index}: {exc}") from exc

                amount_cents = cls._parse_int_optional(
                    cls._value(row, column_map, "default_amount_cents"),
                    "default_amount_cents",
                    index,
                )
                autopay_raw = cls._value(row, column_map, "autopay")
                try:
                    autopay = cls._parse_bool(autopay_raw)
                except ValueError as exc:
                    raise ValueError(f"Row {index}: {exc}") from exc
                notes = cls._value(row, column_map, "notes", "note") or None
                category_id = cls._resolve_category_id(
                    row=row,
                    column_map=column_map,
                    row_number=index,
                    categories_by_id=categories_by_id,
                    categories_by_name=categories_by_name,
                    required=False,
                )

                due_day = int(start_date.split("-")[2])
                frequency = f"{interval_count} {interval_unit}"

                existing = None
                if definition_id is not None:
                    existing = conn.execute(
                        """
                        SELECT bill_id, source_system
                        FROM bills
                        WHERE bill_id = ?
                        """,
                        (int(definition_id),),
                    ).fetchone()
                    if existing is not None and str(existing["source_system"]).lower() != "budgetpal":
                        raise ValueError(
                            f"Row {index}: definition_id {definition_id} is not a budgetpal bill."
                        )

                update_bill_id: int | None = None
                if existing is not None:
                    update_bill_id = int(existing["bill_id"])
                elif definition_id is None:
                    natural = conn.execute(
                        """
                        SELECT bill_id
                        FROM bills
                        WHERE lower(trim(source_system)) = 'budgetpal'
                          AND lower(name) = lower(?)
                          AND coalesce(start_date, '') = ?
                          AND coalesce(interval_count, 1) = ?
                          AND lower(coalesce(interval_unit, 'months')) = ?
                        LIMIT 1
                        """,
                        (name, start_date, interval_count, interval_unit),
                    ).fetchone()
                    if natural is not None:
                        update_bill_id = int(natural["bill_id"])

                if update_bill_id is not None:
                    conn.execute(
                        """
                        UPDATE bills
                        SET name = ?,
                            category_id = ?,
                            due_day = ?,
                            start_date = ?,
                            interval_count = ?,
                            interval_unit = ?,
                            frequency = ?,
                            default_amount_cents = ?,
                            autopay = ?,
                            notes = ?,
                            source_system = 'budgetpal',
                            source_uid = NULL,
                            is_active = 1
                        WHERE bill_id = ?
                        """,
                        (
                            name,
                            category_id,
                            due_day,
                            start_date,
                            interval_count,
                            interval_unit,
                            frequency,
                            amount_cents,
                            autopay,
                            notes,
                            int(update_bill_id),
                        ),
                    )
                    updated += 1
                    continue

                if definition_id is not None:
                    conn.execute(
                        """
                        INSERT INTO bills(
                            bill_id,
                            name,
                            category_id,
                            due_day,
                            start_date,
                            interval_count,
                            interval_unit,
                            frequency,
                            default_amount_cents,
                            autopay,
                            source_system,
                            source_uid,
                            notes,
                            is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'budgetpal', NULL, ?, 1)
                        """,
                        (
                            int(definition_id),
                            name,
                            category_id,
                            due_day,
                            start_date,
                            interval_count,
                            interval_unit,
                            frequency,
                            amount_cents,
                            autopay,
                            notes,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO bills(
                            name,
                            category_id,
                            due_day,
                            start_date,
                            interval_count,
                            interval_unit,
                            frequency,
                            default_amount_cents,
                            autopay,
                            source_system,
                            source_uid,
                            notes,
                            is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'budgetpal', NULL, ?, 1)
                        """,
                        (
                            name,
                            category_id,
                            due_day,
                            start_date,
                            interval_count,
                            interval_unit,
                            frequency,
                            amount_cents,
                            autopay,
                            notes,
                        ),
                    )
                inserted += 1

        return inserted, updated, skipped_blank

    @classmethod
    def _import_income(
        cls,
        conn: sqlite3.Connection,
        rows: list[dict],
        fieldnames: list[str],
        categories_by_id: dict[int, str],
        categories_by_name: dict[str, int],
        accounts_by_id: dict[int, str],
        accounts_by_name: dict[str, int],
    ) -> tuple[int, int, int]:
        column_map = cls._column_map(fieldnames)
        inserted = 0
        updated = 0
        skipped_blank = 0

        with conn:
            for index, row in enumerate(rows, start=2):
                if cls._row_is_blank(row):
                    skipped_blank += 1
                    continue

                definition_id = cls._parse_int_optional(
                    cls._value(row, column_map, "definition_id", "income_id"),
                    "definition_id",
                    index,
                )
                description = cls._value(row, column_map, "description")
                if not description:
                    raise ValueError(f"Row {index}: description is required.")
                start_date = cls._validate_date(
                    cls._value(row, column_map, "start_date", "deposit_due"),
                    "start_date",
                    index,
                )
                interval_count = cls._parse_int(
                    cls._value(row, column_map, "interval_count"),
                    "interval_count",
                    index,
                )
                if interval_count < 1:
                    raise ValueError(f"Row {index}: interval_count must be >= 1.")
                try:
                    interval_unit = cls._normalize_interval_unit(
                        cls._value(row, column_map, "interval_unit")
                    )
                except ValueError as exc:
                    raise ValueError(f"Row {index}: {exc}") from exc

                amount_cents = cls._parse_int_optional(
                    cls._value(row, column_map, "default_amount_cents"),
                    "default_amount_cents",
                    index,
                )
                notes = cls._value(row, column_map, "notes", "note") or None
                category_id = cls._resolve_category_id(
                    row=row,
                    column_map=column_map,
                    row_number=index,
                    categories_by_id=categories_by_id,
                    categories_by_name=categories_by_name,
                    required=False,
                )
                account_id = cls._resolve_account_id(
                    row=row,
                    column_map=column_map,
                    row_number=index,
                    accounts_by_id=accounts_by_id,
                    accounts_by_name=accounts_by_name,
                )

                existing = None
                if definition_id is not None:
                    existing = conn.execute(
                        """
                        SELECT income_id, source_system
                        FROM income_definitions
                        WHERE income_id = ?
                        """,
                        (int(definition_id),),
                    ).fetchone()
                    if existing is not None and str(existing["source_system"]).lower() != "budgetpal":
                        raise ValueError(
                            f"Row {index}: definition_id {definition_id} is not a budgetpal income."
                        )

                update_income_id: int | None = None
                if existing is not None:
                    update_income_id = int(existing["income_id"])
                elif definition_id is None:
                    natural = conn.execute(
                        """
                        SELECT income_id
                        FROM income_definitions
                        WHERE lower(trim(source_system)) = 'budgetpal'
                          AND lower(description) = lower(?)
                          AND coalesce(start_date, '') = ?
                          AND coalesce(interval_count, 1) = ?
                          AND lower(coalesce(interval_unit, 'months')) = ?
                          AND account_id = ?
                        LIMIT 1
                        """,
                        (
                            description,
                            start_date,
                            interval_count,
                            interval_unit,
                            int(account_id),
                        ),
                    ).fetchone()
                    if natural is not None:
                        update_income_id = int(natural["income_id"])

                if update_income_id is not None:
                    conn.execute(
                        """
                        UPDATE income_definitions
                        SET description = ?,
                            default_amount_cents = ?,
                            category_id = ?,
                            account_id = ?,
                            start_date = ?,
                            interval_count = ?,
                            interval_unit = ?,
                            notes = ?,
                            source_system = 'budgetpal',
                            is_active = 1
                        WHERE income_id = ?
                        """,
                        (
                            description,
                            amount_cents,
                            category_id,
                            account_id,
                            start_date,
                            interval_count,
                            interval_unit,
                            notes,
                            int(update_income_id),
                        ),
                    )
                    updated += 1
                    continue

                if definition_id is not None:
                    conn.execute(
                        """
                        INSERT INTO income_definitions(
                            income_id,
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'budgetpal', 1, ?)
                        """,
                        (
                            int(definition_id),
                            description,
                            amount_cents,
                            category_id,
                            account_id,
                            start_date,
                            interval_count,
                            interval_unit,
                            notes,
                        ),
                    )
                else:
                    conn.execute(
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'budgetpal', 1, ?)
                        """,
                        (
                            description,
                            amount_cents,
                            category_id,
                            account_id,
                            start_date,
                            interval_count,
                            interval_unit,
                            notes,
                        ),
                    )
                inserted += 1

        return inserted, updated, skipped_blank

    @classmethod
    def _import_budget_allocations(
        cls,
        conn: sqlite3.Connection,
        rows: list[dict],
        fieldnames: list[str],
        categories_by_id: dict[int, str],
        categories_by_name: dict[str, int],
    ) -> tuple[int, int, int]:
        column_map = cls._column_map(fieldnames)
        inserted = 0
        updated = 0
        skipped_blank = 0

        with conn:
            for index, row in enumerate(rows, start=2):
                if cls._row_is_blank(row):
                    skipped_blank += 1
                    continue

                category_id = cls._resolve_category_id(
                    row=row,
                    column_map=column_map,
                    row_number=index,
                    categories_by_id=categories_by_id,
                    categories_by_name=categories_by_name,
                    required=True,
                )
                amount_cents = cls._parse_int(
                    cls._value(row, column_map, "default_amount_cents", "amount_cents"),
                    "default_amount_cents",
                    index,
                )
                if amount_cents < 0:
                    raise ValueError(f"Row {index}: default_amount_cents cannot be negative.")
                note = cls._value(row, column_map, "note", "notes") or None

                existing = conn.execute(
                    """
                    SELECT definition_id
                    FROM budget_category_definitions
                    WHERE category_id = ?
                    """,
                    (int(category_id),),
                ).fetchone()
                if existing is None:
                    inserted += 1
                else:
                    updated += 1

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
                    (int(category_id), int(amount_cents), note),
                )

        return inserted, updated, skipped_blank

    @classmethod
    def _import_accounts(
        cls,
        conn: sqlite3.Connection,
        rows: list[dict],
        fieldnames: list[str],
        institutions_by_id: dict[int, str],
        institutions_by_name: dict[str, int],
    ) -> tuple[int, int, int]:
        column_map = cls._column_map(fieldnames)
        inserted = 0
        updated = 0
        skipped_blank = 0

        with conn:
            for index, row in enumerate(rows, start=2):
                if cls._row_is_blank(row):
                    skipped_blank += 1
                    continue

                definition_id = cls._parse_int_optional(
                    cls._value(row, column_map, "definition_id", "account_id"),
                    "definition_id",
                    index,
                )
                institution_id_raw = cls._value(row, column_map, "institution_id")
                institution_name = cls._value(row, column_map, "institution_name", "institution")
                account_name = cls._value(
                    row,
                    column_map,
                    "account_name",
                    "name",
                    "account_alias",
                )
                if not account_name:
                    raise ValueError(f"Row {index}: account_name is required.")

                account_type = cls._value(
                    row,
                    column_map,
                    "account_type",
                    "account_class",
                    "type",
                ).strip().lower()
                if not account_type:
                    raise ValueError(f"Row {index}: account_type is required.")

                opening_balance_cents = cls._parse_int_optional(
                    cls._value(row, column_map, "opening_balance_cents", "opening_balance"),
                    "opening_balance_cents",
                    index,
                )
                opening_balance_cents = int(opening_balance_cents or 0)
                line_of_credit_cents = cls._parse_int_optional(
                    cls._value(row, column_map, "line_of_credit_cents", "line_of_credit"),
                    "line_of_credit_cents",
                    index,
                )

                account_number = cls._value(row, column_map, "account_number") or None
                notes = cls._value(row, column_map, "notes", "note") or None

                cd_start_date = cls._value(row, column_map, "cd_start_date")
                if cd_start_date:
                    cd_start_date = cls._validate_date(cd_start_date, "cd_start_date", index)
                else:
                    cd_start_date = None

                cd_interval_count = cls._parse_int_optional(
                    cls._value(row, column_map, "cd_interval_count", "cd_interval"),
                    "cd_interval_count",
                    index,
                )
                if cd_interval_count is not None and cd_interval_count < 1:
                    raise ValueError(f"Row {index}: cd_interval_count must be >= 1.")

                cd_interval_unit = cls._value(row, column_map, "cd_interval_unit")
                cd_interval_unit = cd_interval_unit.lower() if cd_interval_unit else None
                cd_interest_rate_bps = cls._parse_int_optional(
                    cls._value(row, column_map, "cd_interest_rate_bps"),
                    "cd_interest_rate_bps",
                    index,
                )

                is_external_raw = cls._value(
                    row,
                    column_map,
                    "is_external",
                    "external_account",
                    "external",
                )
                is_external = cls._parse_bool(is_external_raw)
                show_on_accounts_tab_raw = cls._value(
                    row,
                    column_map,
                    "show_on_accounts_tab",
                    "show_on_accounts",
                    "accounts_tab",
                    "show_in_accounts_tab",
                )
                show_on_accounts_tab = (
                    cls._parse_bool(show_on_accounts_tab_raw) if show_on_accounts_tab_raw else 1
                )

                is_active_raw = cls._value(row, column_map, "is_active")
                is_active = cls._parse_bool(is_active_raw) if is_active_raw else 1

                resolved_institution_id: int | None = None
                if institution_name:
                    match_id = institutions_by_name.get(institution_name.casefold())
                    if match_id is None:
                        conn.execute(
                            """
                            INSERT INTO institutions(name, is_active)
                            VALUES (?, 1)
                            """,
                            (institution_name,),
                        )
                        row_inst = conn.execute(
                            """
                            SELECT institution_id
                            FROM institutions
                            WHERE lower(trim(name)) = lower(trim(?))
                            LIMIT 1
                            """,
                            (institution_name,),
                        ).fetchone()
                        if row_inst is None:
                            raise RuntimeError(
                                f"Row {index}: could not resolve institution '{institution_name}'."
                            )
                        match_id = int(row_inst["institution_id"])
                    resolved_institution_id = int(match_id)
                    institutions_by_id[resolved_institution_id] = institution_name
                    institutions_by_name[institution_name.casefold()] = resolved_institution_id
                elif institution_id_raw:
                    parsed_institution_id = cls._parse_int(
                        institution_id_raw,
                        "institution_id",
                        index,
                    )
                    if parsed_institution_id not in institutions_by_id:
                        raise ValueError(
                            f"Row {index}: institution_id {parsed_institution_id} does not exist."
                        )
                    resolved_institution_id = parsed_institution_id

                if resolved_institution_id is None:
                    default_name = "Default Institution"
                    default_id = institutions_by_name.get(default_name.casefold())
                    if default_id is None:
                        conn.execute(
                            "INSERT INTO institutions(name, is_active) VALUES (?, 1)",
                            (default_name,),
                        )
                        row_inst = conn.execute(
                            """
                            SELECT institution_id
                            FROM institutions
                            WHERE lower(trim(name)) = lower(trim(?))
                            LIMIT 1
                            """,
                            (default_name,),
                        ).fetchone()
                        if row_inst is None:
                            raise RuntimeError("Could not resolve default institution.")
                        default_id = int(row_inst["institution_id"])
                    resolved_institution_id = int(default_id)
                    institutions_by_id[resolved_institution_id] = default_name
                    institutions_by_name[default_name.casefold()] = resolved_institution_id

                natural = conn.execute(
                    """
                    SELECT account_id
                    FROM accounts
                    WHERE institution_id = ?
                      AND lower(trim(name)) = lower(trim(?))
                    LIMIT 1
                    """,
                    (int(resolved_institution_id), account_name),
                ).fetchone()

                existing = None
                if natural is not None:
                    existing = natural
                elif definition_id is not None:
                    existing = conn.execute(
                        """
                        SELECT account_id
                        FROM accounts
                        WHERE account_id = ?
                        LIMIT 1
                        """,
                        (int(definition_id),),
                    ).fetchone()

                if existing is not None:
                    conn.execute(
                        """
                        UPDATE accounts
                        SET institution_id = ?,
                            name = ?,
                            account_type = ?,
                            opening_balance_cents = ?,
                            line_of_credit_cents = ?,
                            account_number = ?,
                            notes = ?,
                            cd_start_date = ?,
                            cd_interval_count = ?,
                            cd_interval_unit = ?,
                            cd_interest_rate_bps = ?,
                            is_external = ?,
                            show_on_accounts_tab = ?,
                            is_active = ?
                        WHERE account_id = ?
                        """,
                        (
                            int(resolved_institution_id),
                            account_name,
                            account_type,
                            int(opening_balance_cents),
                            line_of_credit_cents,
                            account_number,
                            notes,
                            cd_start_date,
                            cd_interval_count,
                            cd_interval_unit,
                            cd_interest_rate_bps,
                            int(is_external),
                            int(show_on_accounts_tab),
                            int(is_active),
                            int(existing["account_id"]),
                        ),
                    )
                    updated += 1
                    continue

                if definition_id is not None:
                    conn.execute(
                        """
                        INSERT INTO accounts(
                            account_id,
                            institution_id,
                            name,
                            account_type,
                            opening_balance_cents,
                            line_of_credit_cents,
                            account_number,
                            notes,
                            cd_start_date,
                            cd_interval_count,
                            cd_interval_unit,
                            cd_interest_rate_bps,
                            is_external,
                            show_on_accounts_tab,
                            is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(definition_id),
                            int(resolved_institution_id),
                            account_name,
                            account_type,
                            int(opening_balance_cents),
                            line_of_credit_cents,
                            account_number,
                            notes,
                            cd_start_date,
                            cd_interval_count,
                            cd_interval_unit,
                            cd_interest_rate_bps,
                            int(is_external),
                            int(show_on_accounts_tab),
                            int(is_active),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO accounts(
                            institution_id,
                            name,
                            account_type,
                            opening_balance_cents,
                            line_of_credit_cents,
                            account_number,
                            notes,
                            cd_start_date,
                            cd_interval_count,
                            cd_interval_unit,
                            cd_interest_rate_bps,
                            is_external,
                            show_on_accounts_tab,
                            is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(resolved_institution_id),
                            account_name,
                            account_type,
                            int(opening_balance_cents),
                            line_of_credit_cents,
                            account_number,
                            notes,
                            cd_start_date,
                            cd_interval_count,
                            cd_interval_unit,
                            cd_interest_rate_bps,
                            int(is_external),
                            int(show_on_accounts_tab),
                            int(is_active),
                        ),
                    )
                inserted += 1

        return inserted, updated, skipped_blank

    def _write_query_csv(self, conn: sqlite3.Connection, query: str, file_path: Path) -> None:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        fieldnames = [str(col[0]) for col in (cursor.description or [])]
        if not fieldnames:
            file_path.write_text("", encoding="utf-8")
            return

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
