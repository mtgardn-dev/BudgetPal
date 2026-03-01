from __future__ import annotations

from core.persistence.repositories.tax_repo import TaxRepository


class TaxService:
    def __init__(self, tax_repo: TaxRepository) -> None:
        self.tax_repo = tax_repo

    def categories(self) -> list[str]:
        return self.tax_repo.list_categories()

    def summary(self, year: int) -> list[dict]:
        return self.tax_repo.tax_summary(year)

    def detail(self, year: int) -> list[dict]:
        return self.tax_repo.tax_detail(year)
