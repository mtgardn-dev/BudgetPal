from __future__ import annotations

from core.domain import TransactionInput, TransferInput
from core.persistence.repositories.transactions_repo import TransactionsRepository


class TransactionsService:
    def __init__(self, transactions_repo: TransactionsRepository) -> None:
        self.transactions_repo = transactions_repo

    def add_transaction(self, txn: TransactionInput) -> int:
        return self.transactions_repo.add_transaction(txn)

    def add_transfer(self, transfer: TransferInput) -> str:
        return self.transactions_repo.add_transfer(transfer)

    def update_manual_transfer_group(self, transfer_group_id: str, transfer: TransferInput) -> int:
        return self.transactions_repo.update_manual_transfer_group(transfer_group_id, transfer)

    def delete_manual_transfer_group(self, transfer_group_id: str) -> int:
        return self.transactions_repo.delete_manual_transfer_group(transfer_group_id)

    def list_recent(self, limit: int = 300) -> list[dict]:
        return self.transactions_repo.list_transactions(limit=limit)

    def list_for_month(self, year: int, month: int, limit: int = 2000) -> list[dict]:
        return self.transactions_repo.list_transactions_for_month(year=year, month=month, limit=limit)

    def list_transfer_summaries_for_month(self, year: int, month: int, limit: int = 2000) -> list[dict]:
        return self.transactions_repo.list_transfer_summaries_for_month(year=year, month=month, limit=limit)

    def list_checking_ledger_for_month(
        self,
        year: int,
        month: int,
        account_id: int | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        return self.transactions_repo.list_checking_ledger_for_month(
            year=year,
            month=month,
            account_id=account_id,
            limit=limit,
        )

    def list_account_ledger_for_month(
        self,
        year: int,
        month: int,
        account_id: int,
        *,
        include_prior_uncleared: bool = False,
        limit: int = 10000,
    ) -> list[dict]:
        return self.transactions_repo.list_account_ledger_for_month(
            year=year,
            month=month,
            account_id=account_id,
            include_prior_uncleared=include_prior_uncleared,
            limit=limit,
        )

    def list_available_months(self) -> list[str]:
        return self.transactions_repo.list_available_months()

    def get_transaction(self, txn_id: int) -> dict | None:
        return self.transactions_repo.get_transaction(txn_id)

    def update_transaction(self, txn_id: int, txn: TransactionInput) -> int:
        return self.transactions_repo.update_transaction(txn_id, txn)

    def delete_transaction(self, txn_id: int) -> int:
        return self.transactions_repo.delete_transaction(txn_id)

    def set_transaction_cleared(self, txn_id: int, is_cleared: bool) -> int:
        return self.transactions_repo.set_transaction_cleared(txn_id, is_cleared)

    def set_transaction_note(self, txn_id: int, note: str | None) -> int:
        return self.transactions_repo.set_transaction_note(txn_id, note)

    def get_checking_month_beginning_balance(
        self,
        year: int,
        month: int,
        account_id: int | None = None,
    ) -> int:
        return self.transactions_repo.get_checking_month_beginning_balance(
            year=year,
            month=month,
            account_id=account_id,
        )

    def get_account_month_beginning_balance(
        self,
        year: int,
        month: int,
        account_id: int,
    ) -> int:
        return self.transactions_repo.get_account_month_beginning_balance(
            year=year,
            month=month,
            account_id=account_id,
        )

    def set_checking_month_beginning_balance(
        self,
        year: int,
        month: int,
        beginning_balance_cents: int,
        account_id: int | None = None,
    ) -> None:
        self.transactions_repo.set_checking_month_beginning_balance(
            year=year,
            month=month,
            beginning_balance_cents=beginning_balance_cents,
            account_id=account_id,
        )

    def set_account_month_beginning_balance(
        self,
        year: int,
        month: int,
        beginning_balance_cents: int,
        account_id: int,
    ) -> None:
        self.transactions_repo.set_account_month_beginning_balance(
            year=year,
            month=month,
            beginning_balance_cents=beginning_balance_cents,
            account_id=account_id,
        )

    def get_account_month_statement(
        self,
        year: int,
        month: int,
        account_id: int,
    ) -> dict:
        return self.transactions_repo.get_account_month_statement(
            year=year,
            month=month,
            account_id=account_id,
        )

    def set_account_month_statement(
        self,
        year: int,
        month: int,
        account_id: int,
        statement_ending_balance_cents: int | None,
        statement_ending_date: str | None,
        reported_current_balance_cents: int | None = None,
        reported_available_credit_cents: int | None = None,
    ) -> None:
        self.transactions_repo.set_account_month_statement(
            year=year,
            month=month,
            account_id=account_id,
            statement_ending_balance_cents=statement_ending_balance_cents,
            statement_ending_date=statement_ending_date,
            reported_current_balance_cents=reported_current_balance_cents,
            reported_available_credit_cents=reported_available_credit_cents,
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
