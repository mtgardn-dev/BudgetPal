from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from core.persistence.repositories.bills_repo import BillsRepository


class BillsService:
    def __init__(self, bills_repo: BillsRepository) -> None:
        self.bills_repo = bills_repo

    def generate_for_month(self, year: int, month: int) -> int:
        return self.bills_repo.generate_month_occurrences(year, month)

    def list_occurrences(self, year: int, month: int) -> list[dict]:
        return self.bills_repo.list_occurrences(year, month)

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
    def _next_due_date(cls, row: dict, today: date | None = None) -> date | None:
        today = today or date.today()
        start_text = str(row.get("start_date") or "").strip()
        if start_text:
            try:
                due = cls._parse_date(start_text)
            except ValueError:
                due = None
            if due:
                interval_count = int(row.get("interval_count") or 1)
                interval_unit = str(row.get("interval_unit") or "months")
                if interval_unit == "once":
                    return due if due >= today else None
                while due < today:
                    due = cls._add_interval(due, interval_count, interval_unit)
                return due

        due_day = row.get("due_day")
        if due_day is None:
            return None
        try:
            day = max(1, min(28, int(due_day)))
        except (TypeError, ValueError):
            return None

        current_month_date = date(today.year, today.month, day)
        if current_month_date >= today:
            return current_month_date
        return cls._add_months(current_month_date, 1)

    @classmethod
    def _due_date_for_period(cls, row: dict, year: int, month: int) -> date | None:
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        start_text = str(row.get("start_date") or "").strip()
        if start_text:
            try:
                due = cls._parse_date(start_text)
            except ValueError:
                due = None
            if due:
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

        due_day = row.get("due_day")
        if due_day is None:
            return None
        try:
            day = max(1, min(monthrange(year, month)[1], int(due_day)))
        except (TypeError, ValueError):
            return None
        return date(year, month, day)

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

    def list_bill_definitions(
        self,
        sort_by: str = "payment_due",
        year: int | None = None,
        month: int | None = None,
    ) -> list[dict]:
        sort_key = str(sort_by or "payment_due").strip().lower()
        rows = self.bills_repo.list_bill_definitions()
        normalized: list[dict] = []
        for row in rows:
            if year is not None and month is not None:
                due = self._due_date_for_period(row, int(year), int(month))
                if due is None:
                    continue
            else:
                due = self._next_due_date(row)
            amount_cents = row.get("default_amount_cents")
            amount_display = ""
            if amount_cents is not None:
                amount_display = f"${int(amount_cents) / 100:.2f}"
            interval_count = int(row.get("interval_count") or 1)
            interval_unit = str(row.get("interval_unit") or "months")
            normalized.append(
                {
                    **row,
                    "payment_due": due.isoformat() if due else "",
                    "interval_display": self._interval_display(interval_count, interval_unit),
                    "amount_display": amount_display,
                    "category_name": str(row.get("category_name") or "Uncategorized"),
                    "notes": str(row.get("notes") or ""),
                }
            )

        if sort_key == "name":
            normalized.sort(key=lambda r: (str(r.get("name") or "").lower(), int(r.get("bill_id") or 0)))
        elif sort_key == "category":
            normalized.sort(
                key=lambda r: (
                    str(r.get("category_name") or "").lower(),
                    str(r.get("name") or "").lower(),
                    int(r.get("bill_id") or 0),
                )
            )
        else:  # payment_due default
            normalized.sort(
                key=lambda r: (
                    str(r.get("payment_due") or "9999-12-31"),
                    str(r.get("name") or "").lower(),
                    int(r.get("bill_id") or 0),
                )
            )
        return normalized

    def add_bill_definition(
        self,
        *,
        name: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        amount_cents: int | None,
        category_id: int | None,
        notes: str | None,
    ) -> int:
        return self.bills_repo.add_manual_bill(
            name=name,
            start_date=start_date,
            interval_count=interval_count,
            interval_unit=interval_unit,
            default_amount_cents=amount_cents,
            category_id=category_id,
            notes=notes,
        )

    def update_bill_definition(
        self,
        *,
        bill_id: int,
        name: str,
        start_date: str,
        interval_count: int,
        interval_unit: str,
        amount_cents: int | None,
        category_id: int | None,
        notes: str | None,
    ) -> int:
        return self.bills_repo.update_bill_definition(
            bill_id=bill_id,
            name=name,
            start_date=start_date,
            interval_count=interval_count,
            interval_unit=interval_unit,
            default_amount_cents=amount_cents,
            category_id=category_id,
            notes=notes,
        )

    def delete_bill_definition(self, bill_id: int) -> int:
        return self.bills_repo.delete_bill(bill_id)
