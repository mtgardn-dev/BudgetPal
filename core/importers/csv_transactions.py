from __future__ import annotations

import csv
from pathlib import Path

from core.domain import TransactionInput
from core.persistence.repositories.accounts_repo import AccountsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository
from core.services.transactions import TransactionsService


class CSVTransactionImporter:
    def __init__(
        self,
        transactions_service: TransactionsService,
        categories_repo: CategoriesRepository,
        accounts_repo: AccountsRepository,
    ) -> None:
        self.transactions_service = transactions_service
        self.categories_repo = categories_repo
        self.accounts_repo = accounts_repo

    def import_file(self, csv_path: Path) -> int:
        imported = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = {"Date", "Amount", "Payee/Description", "Category", "Account"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

            for row in reader:
                account_name = (row.get("Account") or "Checking").strip() or "Checking"
                category_name = (row.get("Category") or "Misc").strip() or "Misc"
                payee = (row.get("Payee/Description") or "").strip()
                note = (row.get("Notes") or "").strip() or None
                if not payee:
                    continue

                account = self.accounts_repo.find_by_name(account_name)
                if not account:
                    account_id = self.accounts_repo.upsert(account_name, "checking")
                else:
                    account_id = int(account["account_id"])

                category = self.categories_repo.find_by_name(category_name)
                if not category:
                    category_id = self.categories_repo.upsert(category_name, is_income=False)
                else:
                    category_id = int(category["category_id"])

                amount_float = float(row["Amount"])
                amount_cents = int(round(amount_float * 100))
                txn_type = "income" if amount_cents > 0 else "expense"

                txn = TransactionInput(
                    txn_date=row["Date"],
                    amount_cents=amount_cents,
                    txn_type=txn_type,
                    payee=payee,
                    description=None,
                    category_id=category_id,
                    account_id=account_id,
                    note=note,
                    source_system="csv_import",
                    source_uid=f"{csv_path.name}:{reader.line_num}",
                    tax_deductible=(row.get("TaxDeductible", "").strip().lower() in {"1", "true", "yes", "y"}),
                    tax_category=(row.get("TaxCategory") or "").strip() or None,
                    receipt_uri=(row.get("ReceiptURI") or "").strip() or None,
                )
                self.transactions_service.add_transaction(txn)
                imported += 1

        return imported
