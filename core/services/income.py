from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from core.persistence.repositories.income_repo import IncomeRepository


class IncomeService:
    def __init__(self, income_repo: IncomeRepository) -> None:
        self.income_repo = income_repo

    @staticmethod
    def _parse_date(date_text: str) -> date:
        return datetime.strptime(date_text, "%Y-%m-%d").date()

    @staticmethod
    def _add_months(base: date, months: int) -> date:
        year = base.year + (base.month - 1 + months) // 12
        month = (base.month - 1 + months) % 12 + 1
        day = min(base.day, monthrange(year, month)[1])
        return date(year, month, day)

    @classmethod
    def _add_interval(cls, base: date, interval_count: int, interval_unit: str) -> date:
        unit = str(interval_unit or "months").strip().lower()
        count = max(1, int(interval_count or 1))
        if unit == "once":
            return base
        if unit == "days":
            return base.fromordinal(base.toordinal() + count)
        if unit == "weeks":
            return base.fromordinal(base.toordinal() + (count * 7))
        if unit == "years":
            return cls._add_months(base, count * 12)
        return cls._add_months(base, count)

    @classmethod
    def _due_date_for_period(cls, row: dict, year: int, month: int) -> date | None:
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        start_text = str(row.get("start_date") or "").strip()
        if not start_text:
            return None
        try:
            due = cls._parse_date(start_text)
        except ValueError:
            return None

        interval_count = int(row.get("interval_count") or 1)
        interval_unit = str(row.get("interval_unit") or "months")
        if interval_unit == "once":
            return due if month_start <= due <= month_end else None
        safety = 0
        while due < month_start and safety < 1000:
            due = cls._add_interval(due, interval_count, interval_unit)
            safety += 1
        if month_start <= due <= month_end:
            return due
        return None

    @staticmethod
    def _interval_display(interval_count: int, interval_unit: str) -> str:
        count = max(1, int(interval_count or 1))
        unit = str(interval_unit or "months").strip().lower()
        if unit == "once":
            return "once"
        singular = unit[:-1] if unit.endswith("s") else unit
        if count == 1:
            return f"1 {singular}"
        if not unit.endswith("s"):
            unit = f"{unit}s"
        return f"{count} {unit}"

    def add_definition(
        self,
        *,
        description: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        amount_cents: int | None,
        category_id: int | None,
        account_id: int,
        notes: str | None,
    ) -> int:
        return self.income_repo.add_definition(
            description=description,
            start_date=start_date,
            interval_count=interval_count,
            interval_unit=interval_unit,
            default_amount_cents=amount_cents,
            category_id=category_id,
            account_id=account_id,
            notes=notes,
        )

    def update_definition(
        self,
        *,
        income_id: int,
        description: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        amount_cents: int | None,
        category_id: int | None,
        account_id: int,
        notes: str | None,
    ) -> int:
        return self.income_repo.update_definition(
            income_id=income_id,
            description=description,
            start_date=start_date,
            interval_count=interval_count,
            interval_unit=interval_unit,
            default_amount_cents=amount_cents,
            category_id=category_id,
            account_id=account_id,
            notes=notes,
        )

    def delete_definition(self, income_id: int) -> int:
        return self.income_repo.delete_definition(income_id)

    def list_definitions(self, *, sort_by: str = "payment_due") -> list[dict]:
        rows = self.income_repo.list_definitions()
        normalized: list[dict] = []
        for row in rows:
            due = self._due_date_for_period(row, date.today().year, date.today().month)
            amount_cents = row.get("default_amount_cents")
            amount_display = f"${int(amount_cents) / 100:.2f}" if amount_cents is not None else ""
            interval_count = int(row.get("interval_count") or 1)
            interval_unit = str(row.get("interval_unit") or "months")
            normalized.append(
                {
                    **row,
                    "payment_due": due.isoformat() if due else "",
                    "interval_display": self._interval_display(interval_count, interval_unit),
                    "amount_display": amount_display,
                    "category_name": str(row.get("category_name") or "Uncategorized"),
                    "account_name": str(row.get("account_name") or ""),
                    "notes": str(row.get("notes") or ""),
                }
            )

        key = str(sort_by or "payment_due").strip().lower()
        if key == "description":
            normalized.sort(
                key=lambda r: (
                    str(r.get("description") or "").lower(),
                    int(r.get("income_id") or 0),
                )
            )
        elif key == "category":
            normalized.sort(
                key=lambda r: (
                    str(r.get("category_name") or "").lower(),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_id") or 0),
                )
            )
        elif key == "account":
            normalized.sort(
                key=lambda r: (
                    str(r.get("account_name") or "").lower(),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_id") or 0),
                )
            )
        else:
            normalized.sort(
                key=lambda r: (
                    str(r.get("payment_due") or "9999-12-31"),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_id") or 0),
                )
            )
        return normalized

    def generate_for_month(self, year: int, month: int) -> int:
        inserted = 0
        for row in self.income_repo.list_definitions():
            due = self._due_date_for_period(row, int(year), int(month))
            if due is None:
                continue
            if self.income_repo.insert_occurrence_if_missing(
                income_id=int(row["income_id"]),
                year=int(year),
                month=int(month),
                expected_date=due.isoformat(),
                expected_amount_cents=row.get("default_amount_cents"),
            ):
                inserted += 1
        return inserted

    def regenerate_for_month(self, year: int, month: int) -> tuple[int, int]:
        deleted = self.income_repo.delete_occurrences_for_month(int(year), int(month))
        inserted = self.generate_for_month(int(year), int(month))
        return deleted, inserted

    def list_month_income(self, *, year: int, month: int, sort_by: str = "payment_due") -> list[dict]:
        rows = self.income_repo.list_occurrences(int(year), int(month))
        normalized: list[dict] = []
        for row in rows:
            amount_cents = row.get("expected_amount_cents")
            amount_display = f"${int(amount_cents) / 100:.2f}" if amount_cents is not None else ""
            interval_count = int(row.get("interval_count") or 1)
            interval_unit = str(row.get("interval_unit") or "months")
            normalized.append(
                {
                    **row,
                    "payment_due": str(row.get("expected_date") or ""),
                    "interval_display": self._interval_display(interval_count, interval_unit),
                    "amount_display": amount_display,
                    "category_name": str(row.get("category_name") or "Uncategorized"),
                    "account_name": str(row.get("account_name") or ""),
                    "notes": str(row.get("note") or row.get("definition_notes") or ""),
                }
            )

        key = str(sort_by or "payment_due").strip().lower()
        if key == "description":
            normalized.sort(
                key=lambda r: (
                    str(r.get("description") or "").lower(),
                    int(r.get("income_occurrence_id") or 0),
                )
            )
        elif key == "category":
            normalized.sort(
                key=lambda r: (
                    str(r.get("category_name") or "").lower(),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_occurrence_id") or 0),
                )
            )
        elif key == "account":
            normalized.sort(
                key=lambda r: (
                    str(r.get("account_name") or "").lower(),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_occurrence_id") or 0),
                )
            )
        else:
            normalized.sort(
                key=lambda r: (
                    str(r.get("payment_due") or "9999-12-31"),
                    str(r.get("description") or "").lower(),
                    int(r.get("income_occurrence_id") or 0),
                )
            )
        return normalized

    def update_occurrence(
        self,
        *,
        income_occurrence_id: int,
        expected_date: str,
        expected_amount_cents: int | None,
        note: str | None,
    ) -> int:
        return self.income_repo.update_occurrence(
            income_occurrence_id=income_occurrence_id,
            expected_date=expected_date,
            expected_amount_cents=expected_amount_cents,
            note=note,
        )

    def delete_occurrence(self, income_occurrence_id: int) -> int:
        return self.income_repo.delete_occurrence(income_occurrence_id)
