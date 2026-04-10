from __future__ import annotations

from core.domain import TransactionInput, TransactionSplitInput, TransferInput
from core.persistence.repositories.transactions_repo import TransactionsRepository


class TransactionsService:
    def __init__(self, transactions_repo: TransactionsRepository) -> None:
        self.transactions_repo = transactions_repo

    def add_transaction(self, txn: TransactionInput, splits: list[TransactionSplitInput] | None = None) -> int:
        txn_id = self.transactions_repo.add_transaction(txn)
        if splits:
            self.transactions_repo.add_splits(txn_id, splits)
        return txn_id

    def add_transfer(self, transfer: TransferInput) -> str:
        return self.transactions_repo.add_transfer(transfer)

    def list_recent(self, limit: int = 300) -> list[dict]:
        return self.transactions_repo.list_transactions(limit=limit)

    def list_for_month(self, year: int, month: int, limit: int = 2000) -> list[dict]:
        return self.transactions_repo.list_transactions_for_month(year=year, month=month, limit=limit)

    def list_checking_ledger_for_month(self, year: int, month: int, limit: int = 10000) -> list[dict]:
        return self.transactions_repo.list_checking_ledger_for_month(year=year, month=month, limit=limit)

    def list_available_months(self) -> list[str]:
        return self.transactions_repo.list_available_months()

    def get_transaction(self, txn_id: int) -> dict | None:
        return self.transactions_repo.get_transaction(txn_id)

    def update_transaction(
        self, txn_id: int, txn: TransactionInput, splits: list[TransactionSplitInput] | None = None
    ) -> int:
        updated = self.transactions_repo.update_transaction(txn_id, txn)
        if updated and splits is not None:
            self.transactions_repo.add_splits(txn_id, splits)
        return updated

    def delete_transaction(self, txn_id: int) -> int:
        return self.transactions_repo.delete_transaction(txn_id)

    def set_transaction_cleared(self, txn_id: int, is_cleared: bool) -> int:
        return self.transactions_repo.set_transaction_cleared(txn_id, is_cleared)

    def get_checking_month_beginning_balance(self, year: int, month: int) -> int:
        return self.transactions_repo.get_checking_month_beginning_balance(year=year, month=month)

    def set_checking_month_beginning_balance(self, year: int, month: int, beginning_balance_cents: int) -> None:
        self.transactions_repo.set_checking_month_beginning_balance(
            year=year,
            month=month,
            beginning_balance_cents=beginning_balance_cents,
        )

    def replace_transactions_for_months(self, year_month_keys: set[str]) -> int:
        return self.transactions_repo.delete_transactions_for_months(year_month_keys=year_month_keys)

    def replace_imported_transactions_for_months(
        self, year_month_keys: set[str], source_system: str
    ) -> int:
        return self.transactions_repo.delete_imported_transactions_for_months(
            year_month_keys=year_month_keys,
            source_system=source_system,
        )

    def replace_imported_transactions_for_period(
        self, import_period_key: str, source_system: str
    ) -> int:
        return self.transactions_repo.delete_imported_transactions_for_import_period(
            import_period_key=import_period_key,
            source_system=source_system,
        )

    def replace_transactions_for_period(self, import_period_key: str) -> int:
        return self.transactions_repo.delete_transactions_for_import_period(
            import_period_key=import_period_key
        )
