from __future__ import annotations

from core.persistence.repositories.budget_allocations_repo import BudgetAllocationsRepository


class BudgetAllocationsService:
    def __init__(self, repo: BudgetAllocationsRepository) -> None:
        self.repo = repo

    @staticmethod
    def _to_amount_display(cents: int) -> str:
        return f"${int(cents) / 100:.2f}"

    def list_available_months(self) -> list[str]:
        return self.repo.list_available_months()

    def list_definitions(self) -> list[dict]:
        rows = self.repo.list_definitions()
        normalized: list[dict] = []
        for row in rows:
            cents = int(row.get("default_amount_cents") or 0)
            normalized.append(
                {
                    **row,
                    "amount_display": self._to_amount_display(cents),
                    "note": str(row.get("note") or ""),
                }
            )
        normalized.sort(
            key=lambda r: (
                str(r.get("category_name") or "").casefold(),
                int(r.get("definition_id") or 0),
            )
        )
        return normalized

    def upsert_definition(self, *, category_id: int, amount_cents: int, note: str | None) -> int:
        if amount_cents < 0:
            raise ValueError("Amount cannot be negative.")
        return self.repo.upsert_definition(
            category_id=int(category_id),
            default_amount_cents=int(amount_cents),
            note=note,
        )

    def delete_definition(self, definition_id: int) -> int:
        return self.repo.delete_definition(int(definition_id))

    def list_month_allocations(self, *, year: int, month: int) -> list[dict]:
        rows = self.repo.list_month_allocations(int(year), int(month))
        normalized: list[dict] = []
        for row in rows:
            cents = int(row.get("planned_cents") or 0)
            normalized.append(
                {
                    **row,
                    "planned_display": self._to_amount_display(cents),
                    "note": str(row.get("note") or ""),
                }
            )
        normalized.sort(
            key=lambda r: (
                str(r.get("category_name") or "").casefold(),
                int(r.get("budget_line_id") or 0),
            )
        )
        return normalized

    def upsert_month_allocation(
        self,
        *,
        year: int,
        month: int,
        category_id: int,
        planned_cents: int,
        note: str | None,
    ) -> int:
        if planned_cents < 0:
            raise ValueError("Allocation cannot be negative.")
        return self.repo.upsert_month_allocation(
            year=int(year),
            month=int(month),
            category_id=int(category_id),
            planned_cents=int(planned_cents),
            note=note,
        )

    def update_month_allocation(
        self,
        *,
        budget_line_id: int,
        category_id: int,
        planned_cents: int,
        note: str | None,
    ) -> int:
        if planned_cents < 0:
            raise ValueError("Allocation cannot be negative.")
        return self.repo.update_month_allocation(
            budget_line_id=int(budget_line_id),
            category_id=int(category_id),
            planned_cents=int(planned_cents),
            note=note,
        )

    def delete_month_allocation(self, budget_line_id: int) -> int:
        return self.repo.delete_month_allocation(int(budget_line_id))

    def regenerate_for_month(self, year: int, month: int) -> tuple[int, int]:
        return self.repo.regenerate_for_month(int(year), int(month))
