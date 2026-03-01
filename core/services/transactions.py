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
