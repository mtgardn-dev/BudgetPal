from __future__ import annotations

from core.persistence.repositories.bills_repo import BillsRepository


class BillsService:
    def __init__(self, bills_repo: BillsRepository) -> None:
        self.bills_repo = bills_repo

    def generate_for_month(self, year: int, month: int) -> int:
        return self.bills_repo.generate_month_occurrences(year, month)

    def list_occurrences(self, year: int, month: int) -> list[dict]:
        return self.bills_repo.list_occurrences(year, month)
