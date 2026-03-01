from __future__ import annotations

from core.persistence.repositories.budgets_repo import BudgetsRepository
from core.persistence.repositories.transactions_repo import TransactionsRepository


class BudgetingService:
    def __init__(self, budgets_repo: BudgetsRepository, transactions_repo: TransactionsRepository) -> None:
        self.budgets_repo = budgets_repo
        self.transactions_repo = transactions_repo

    def prepare_month(self, year: int, month: int, copy_previous: bool = True) -> int:
        budget_month_id = self.budgets_repo.ensure_month(year, month)
        if copy_previous:
            self.budgets_repo.copy_from_previous_month(year, month)
        return budget_month_id

    def monthly_cashflow(self, year: int, month: int, starting_balance_cents: int) -> dict[str, int]:
        totals = self.transactions_repo.month_totals_by_type(year, month)
        income_cents = max(0, totals["income"])
        expense_cents = abs(min(0, totals["expense"]))
        net_cents = income_cents - expense_cents
        end_balance_cents = starting_balance_cents + net_cents
        return {
            "starting_balance_cents": starting_balance_cents,
            "income_cents": income_cents,
            "expense_cents": expense_cents,
            "net_cents": net_cents,
            "end_balance_cents": end_balance_cents,
        }
