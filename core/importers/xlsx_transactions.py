from __future__ import annotations

from dataclasses import dataclass, replace
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
    import_period_key: str
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
        max_scan_cols = max(7, ws.max_column)
        header_pattern = ["date", "amount", "description", "category"]
        optional_headers = {"account", "subscription", "tax", "type", "note", "notes"}

        for row in range(1, max_scan_rows + 1):
            for col in range(1, max_scan_cols - 2):
                headers = [
                    self._normalize_text(ws.cell(row=row, column=col + idx).value)
                    for idx in range(4)
                ]
                if headers != header_pattern:
                    continue

                column_map: dict[str, int] = {
                    "date": col,
                    "amount": col + 1,
                    "description": col + 2,
                    "category": col + 3,
                }
                next_col = col + 4
                while next_col <= max_scan_cols:
                    header_name = self._normalize_text(ws.cell(row=row, column=next_col).value)
                    if not header_name:
                        break
                    if header_name in optional_headers:
                        canonical_header = "note" if header_name == "notes" else header_name
                        if canonical_header in column_map:
                            next_col += 1
                            continue
                        column_map[canonical_header] = next_col
                        next_col += 1
                        continue
                    break

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
                        "column_map": column_map,
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

    @staticmethod
    def _parse_bool(value: Any, default: bool, row_num: int, field_name: str) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0

        text = str(value).strip().lower()
        if text == "":
            return default
        if text in {"true", "t", "yes", "y", "1", "x", "checked", "check", "✓"}:
            return True
        if text in {"false", "f", "no", "n", "0", "unchecked", "off"}:
            return False
        raise ValueError(f"Invalid {field_name} value '{value}' at row {row_num}")

    @staticmethod
    def _normalize_account_type(value: Any, default_account_type: str, row_num: int) -> str:
        if value is None:
            return default_account_type

        text = str(value).strip().lower()
        if not text:
            return default_account_type

        compact = "".join(ch for ch in text if ch.isalnum())
        if compact in {"cash"}:
            return "cash"
        if compact in {"checking", "check"}:
            return "checking"
        if compact in {"credit", "creditcard", "card"}:
            return "credit"
        if compact in {"savings", "saving"}:
            return "savings"
        raise ValueError(
            "Invalid account value "
            f"'{value}' at row {row_num}. Expected cash/checking/credit/savings."
        )

    @staticmethod
    def _infer_import_period_key(parsed_transactions: list[TransactionInput]) -> str:
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for index, txn in enumerate(parsed_transactions):
            key = txn.txn_date[:7]
            counts[key] = counts.get(key, 0) + 1
            if key not in first_seen:
                first_seen[key] = index

        # Pick the dominant year-month; ties go to earliest appearance in the sheet.
        return min(
            counts.keys(),
            key=lambda key: (-counts[key], first_seen[key]),
        )

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

        account_ids_by_type: dict[str, int] = {}
        for row in self.accounts_repo.list_active():
            account_ids_by_type[str(row["account_type"]).strip().lower()] = int(row["account_id"])
        for account_type, account_name in (
            ("cash", "Cash"),
            ("checking", "Checking"),
            ("credit", "Credit Card"),
            ("savings", "Savings"),
        ):
            if account_type not in account_ids_by_type:
                account_ids_by_type[account_type] = self.accounts_repo.upsert(account_name, account_type)

        sections = self._find_sections(ws)
        row_limit = ws.max_row
        parsed_transactions: list[TransactionInput] = []

        for section in sections:
            kind = section["kind"]
            row = int(section["header_row"]) + 1
            column_map = dict(section.get("column_map", {}))
            date_col = int(column_map.get("date", section["start_col"]))
            amount_col = int(column_map.get("amount", date_col + 1))
            description_col = int(column_map.get("description", date_col + 2))
            category_col = int(column_map.get("category", date_col + 3))
            account_col = int(column_map["account"]) if "account" in column_map else None
            subscription_col = int(column_map["subscription"]) if "subscription" in column_map else None
            tax_col = int(column_map["tax"]) if "tax" in column_map else None
            payment_type_col = int(column_map["type"]) if "type" in column_map else None
            note_col = int(column_map["note"]) if "note" in column_map else None
            blank_streak = 0

            while row <= row_limit:
                date_value = ws.cell(row=row, column=date_col).value
                amount_value = ws.cell(row=row, column=amount_col).value
                desc_value = ws.cell(row=row, column=description_col).value
                category_value = ws.cell(row=row, column=category_col).value
                account_value = ws.cell(row=row, column=account_col).value if account_col else None
                subscription_value = (
                    ws.cell(row=row, column=subscription_col).value if subscription_col else None
                )
                tax_value = ws.cell(row=row, column=tax_col).value if tax_col else None
                payment_type_value = (
                    ws.cell(row=row, column=payment_type_col).value if payment_type_col else None
                )
                note_value = ws.cell(row=row, column=note_col).value if note_col else None

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
                payment_type = str(payment_type_value).strip() if payment_type_value is not None else ""
                note_text = str(note_value).strip() if note_value is not None else ""
                internal_payee = description or "Transaction"
                default_account_type = "checking" if kind == "income" else "credit"
                account_type = self._normalize_account_type(account_value, default_account_type, row)
                account_id = account_ids_by_type[account_type]
                is_subscription = False
                if kind == "expense":
                    is_subscription = self._parse_bool(
                        subscription_value,
                        default=False,
                        row_num=row,
                        field_name="Subscription",
                    )

                tax_default = True if kind == "income" else False
                tax_flag = self._parse_bool(
                    tax_value,
                    default=tax_default,
                    row_num=row,
                    field_name="Tax",
                )
                tax_category = "Other" if (kind == "expense" and tax_flag) else None

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
                    is_subscription=is_subscription,
                    payment_type=payment_type or None,
                    tax_deductible=tax_flag,
                    tax_category=tax_category,
                    note=note_text or None,
                    source_system="xlsx_import",
                    source_uid=f"Transactions:{kind}:{row}",
                )
                parsed_transactions.append(txn)
                row += 1

        if not parsed_transactions:
            raise ValueError("No transaction rows were found in worksheet 'Transactions'.")

        import_period_key = self._infer_import_period_key(parsed_transactions)
        parsed_transactions = [
            replace(
                txn,
                import_period_key=import_period_key,
                source_uid=(
                    f"xlsx_import:{import_period_key}:{txn.source_uid}"
                    if txn.source_uid
                    else None
                ),
            )
            for txn in parsed_transactions
        ]

        deleted_count = 0
        if replace_monthly_baseline:
            # Spreadsheet import is authoritative for the selected sheet period key:
            # remove all prior rows for that period key, regardless of source or txn_date month.
            deleted_count = self.transactions_service.replace_transactions_for_period(
                import_period_key=import_period_key
            )

        imported_count = 0
        for txn in parsed_transactions:
            self.transactions_service.add_transaction(txn)
            imported_count += 1

        return XLSXImportResult(
            imported_count=imported_count,
            deleted_count=deleted_count,
            import_period_key=import_period_key,
            year_month_keys=(import_period_key,),
        )
