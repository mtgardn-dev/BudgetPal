from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.domain import TransactionInput
from core.persistence.repositories.accounts_repo import AccountsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository
from core.services.transactions import TransactionsService


@dataclass(frozen=True)
class XLSXImportResult:
    imported_count: int
    deleted_count: int
    year_month_keys: tuple[str, ...]


class XLSXTransactionImporter:
    def __init__(
        self,
        transactions_service: TransactionsService,
        categories_repo: CategoriesRepository,
        accounts_repo: AccountsRepository,
    ) -> None:
        self.transactions_service = transactions_service
        self.categories_repo = categories_repo
        self.accounts_repo = accounts_repo

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    @staticmethod
    def _section_kind(label: str | None, sequence_index: int) -> str:
        text = (label or "").strip().lower()
        if "income" in text:
            return "income"
        if "expense" in text:
            return "expense"
        # Fallback when section labels are missing: first table expense, second income.
        return "expense" if sequence_index == 0 else "income"

    def _find_sections(self, ws) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        max_scan_rows = min(ws.max_row, 120)
        max_scan_cols = max(4, ws.max_column)
        header_pattern = ["date", "amount", "description", "category"]

        for row in range(1, max_scan_rows + 1):
            for col in range(1, max_scan_cols - 2):
                headers = [
                    self._normalize_text(ws.cell(row=row, column=col + idx).value)
                    for idx in range(4)
                ]
                if headers != header_pattern:
                    continue

                section_label = None
                for lookback in (1, 2, 3):
                    r = row - lookback
                    if r < 1:
                        continue
                    candidate = ws.cell(row=r, column=col).value
                    if candidate is not None and str(candidate).strip():
                        section_label = str(candidate).strip()
                        break

                sections.append(
                    {
                        "kind": self._section_kind(section_label, len(sections)),
                        "header_row": row,
                        "start_col": col,
                    }
                )

        if not sections:
            raise ValueError(
                "Could not find expected Transactions worksheet tables. "
                "Expected headers: Date, Amount, Description, Category."
            )
        return sections

    @staticmethod
    def _parse_date(value: Any, row_num: int) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()

        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"Missing date at row {row_num}")

        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"Invalid date '{text}' at row {row_num}")

    @staticmethod
    def _parse_amount_cents(value: Any, row_num: int) -> int:
        if isinstance(value, (int, float)):
            amount = float(value)
        else:
            text = str(value).strip() if value is not None else ""
            if not text:
                raise ValueError(f"Missing amount at row {row_num}")
            is_parenthetical_negative = text.startswith("(") and text.endswith(")")
            cleaned = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
            try:
                amount = float(cleaned)
            except ValueError as exc:
                raise ValueError(f"Invalid amount '{text}' at row {row_num}") from exc
            if is_parenthetical_negative:
                amount *= -1

        cents = int(round(amount * 100))
        if cents == 0:
            raise ValueError(f"Amount may not be 0 at row {row_num}")
        return cents

    @staticmethod
    def _normalize_description(value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        if text in {"...", "…"}:
            return ""
        return text

    def import_file(
        self,
        xlsx_path: Path,
        default_account: str = "Checking",
        replace_monthly_baseline: bool = True,
    ) -> XLSXImportResult:
        try:
            from openpyxl import load_workbook
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "openpyxl is required for XLSX imports. Install it with: pip install openpyxl"
            ) from exc

        wb = load_workbook(xlsx_path, data_only=True)
        if "Transactions" not in wb.sheetnames:
            raise ValueError("Worksheet 'Transactions' was not found in workbook.")
        ws = wb["Transactions"]

        account = self.accounts_repo.find_by_name(default_account)
        if not account:
            account_id = self.accounts_repo.upsert(default_account, "checking")
        else:
            account_id = int(account["account_id"])

        sections = self._find_sections(ws)
        row_limit = ws.max_row
        parsed_transactions: list[TransactionInput] = []

        for section in sections:
            kind = section["kind"]
            row = int(section["header_row"]) + 1
            col = int(section["start_col"])
            blank_streak = 0

            while row <= row_limit:
                date_value = ws.cell(row=row, column=col).value
                amount_value = ws.cell(row=row, column=col + 1).value
                desc_value = ws.cell(row=row, column=col + 2).value
                category_value = ws.cell(row=row, column=col + 3).value

                if all(
                    v is None or (isinstance(v, str) and not v.strip())
                    for v in (date_value, amount_value, desc_value, category_value)
                ):
                    blank_streak += 1
                    if blank_streak >= 2:
                        break
                    row += 1
                    continue
                blank_streak = 0

                txn_date = self._parse_date(date_value, row)
                amount_cents = self._parse_amount_cents(amount_value, row)
                if kind == "expense" and amount_cents > 0:
                    amount_cents *= -1
                elif kind == "income" and amount_cents < 0:
                    amount_cents = abs(amount_cents)

                description = self._normalize_description(desc_value)
                category_name = (
                    str(category_value).strip()
                    if category_value is not None and str(category_value).strip()
                    else ("Income" if kind == "income" else "Misc")
                )
                internal_payee = description or "Transaction"

                category = self.categories_repo.find_by_name(category_name)
                if not category:
                    category_id = self.categories_repo.upsert(
                        category_name, is_income=(kind == "income")
                    )
                else:
                    category_id = int(category["category_id"])

                txn = TransactionInput(
                    txn_date=txn_date,
                    amount_cents=amount_cents,
                    txn_type="income" if amount_cents > 0 else "expense",
                    payee=internal_payee,
                    description=description or None,
                    category_id=category_id,
                    account_id=account_id,
                    note=None,
                    source_system="xlsx_import",
                    source_uid=f"{xlsx_path.name}:Transactions:{kind}:{row}",
                )
                parsed_transactions.append(txn)
                row += 1

        if not parsed_transactions:
            raise ValueError("No transaction rows were found in worksheet 'Transactions'.")

        year_month_keys = tuple(sorted({txn.txn_date[:7] for txn in parsed_transactions}))
        if len(year_month_keys) != 1:
            months = ", ".join(year_month_keys)
            raise ValueError(
                "Transactions import must contain exactly one month of data. "
                f"Found: {months}"
            )

        target_month = year_month_keys[0]
        deleted_count = 0
        if replace_monthly_baseline:
            # Spreadsheet import is authoritative for the month:
            # remove all transactions in that month, regardless of source.
            deleted_count = self.transactions_service.replace_transactions_for_months({target_month})

        imported_count = 0
        for txn in parsed_transactions:
            self.transactions_service.add_transaction(txn)
            imported_count += 1

        return XLSXImportResult(
            imported_count=imported_count,
            deleted_count=deleted_count,
            year_month_keys=year_month_keys,
        )
