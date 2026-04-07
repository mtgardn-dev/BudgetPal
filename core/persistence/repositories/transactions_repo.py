from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from core.domain import TransactionInput, TransactionSplitInput, TransferInput
from core.persistence.db import BudgetPalDatabase


class TransactionsRepository:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    @staticmethod
    def build_import_hash(txn: TransactionInput) -> str:
        raw = "|".join(
            [
                txn.txn_date,
                str(txn.amount_cents),
                txn.txn_type,
                txn.payee.strip().lower(),
                str(txn.account_id),
                (txn.description or "").strip().lower(),
                str(int(txn.is_subscription)),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_transaction(self, txn: TransactionInput) -> int:
        if txn.amount_cents == 0:
            raise ValueError("amount_cents must not be 0")
        if txn.txn_type not in {"income", "expense", "transfer"}:
            raise ValueError("txn_type must be one of: income, expense, transfer")
        if txn.txn_type == "transfer" and not txn.transfer_group_id:
            raise ValueError("transfer transactions require transfer_group_id")

        tax_year = datetime.strptime(txn.txn_date, "%Y-%m-%d").year if txn.tax_deductible else None
        import_hash = txn.import_hash or self.build_import_hash(txn)

        with self.db.connection() as conn:
            if txn.source_system and txn.source_uid:
                dupe = conn.execute(
                    """
                    SELECT txn_id FROM transactions
                    WHERE source_system = ? AND source_uid = ?
                    """,
                    (txn.source_system, txn.source_uid),
                ).fetchone()
                if dupe:
                    return int(dupe["txn_id"])
            else:
                dupe = conn.execute(
                    """
                    SELECT txn_id FROM transactions
                    WHERE import_hash = ?
                    LIMIT 1
                    """,
                    (import_hash,),
                ).fetchone()
                if dupe:
                    return int(dupe["txn_id"])

            cur = conn.execute(
                """
                INSERT INTO transactions(
                    txn_date,
                    amount_cents,
                    txn_type,
                    payee,
                    description,
                    category_id,
                    account_id,
                    note,
                    source_system,
                    source_uid,
                    import_hash,
                    is_subscription,
                    tax_deductible,
                    tax_category,
                    tax_year,
                    tax_note,
                    receipt_uri,
                    transfer_group_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    txn.txn_date,
                    txn.amount_cents,
                    txn.txn_type,
                    txn.payee,
                    txn.description,
                    txn.category_id,
                    txn.account_id,
                    txn.note,
                    txn.source_system,
                    txn.source_uid,
                    import_hash,
                    int(txn.is_subscription),
                    int(txn.tax_deductible),
                    txn.tax_category,
                    tax_year,
                    txn.tax_note,
                    txn.receipt_uri,
                    txn.transfer_group_id,
                ),
            )
            return int(cur.lastrowid)

    def add_splits(self, txn_id: int, splits: list[TransactionSplitInput]) -> None:
        if not splits:
            return

        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT amount_cents FROM transactions WHERE txn_id = ?",
                (txn_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Transaction {txn_id} not found")

            total_split = sum(s.amount_cents for s in splits)
            if total_split != int(row["amount_cents"]):
                raise ValueError(
                    "Split amounts must sum to the transaction amount exactly "
                    f"({total_split} != {int(row['amount_cents'])})"
                )

            conn.execute("DELETE FROM transaction_splits WHERE txn_id = ?", (txn_id,))
            for split in splits:
                conn.execute(
                    """
                    INSERT INTO transaction_splits(txn_id, category_id, amount_cents, note)
                    VALUES (?, ?, ?, ?)
                    """,
                    (txn_id, split.category_id, split.amount_cents, split.note),
                )

    def add_transfer(self, transfer: TransferInput) -> str:
        if transfer.amount_cents <= 0:
            raise ValueError("Transfer amount must be positive cents")
        if transfer.from_account_id == transfer.to_account_id:
            raise ValueError("Transfer accounts must be different")

        group_id = str(uuid.uuid4())

        out_txn = TransactionInput(
            txn_date=transfer.txn_date,
            amount_cents=-transfer.amount_cents,
            txn_type="transfer",
            payee=transfer.payee,
            description=transfer.description,
            category_id=None,
            account_id=transfer.from_account_id,
            note=transfer.note,
            source_system="manual",
            source_uid=f"transfer:{group_id}:out",
            transfer_group_id=group_id,
        )
        in_txn = TransactionInput(
            txn_date=transfer.txn_date,
            amount_cents=transfer.amount_cents,
            txn_type="transfer",
            payee=transfer.payee,
            description=transfer.description,
            category_id=None,
            account_id=transfer.to_account_id,
            note=transfer.note,
            source_system="manual",
            source_uid=f"transfer:{group_id}:in",
            transfer_group_id=group_id,
        )

        with self.db.connection() as conn:
            for txn in (out_txn, in_txn):
                conn.execute(
                    """
                    INSERT INTO transactions(
                        txn_date,
                        amount_cents,
                        txn_type,
                        payee,
                        description,
                        category_id,
                        account_id,
                        note,
                        source_system,
                        source_uid,
                        import_hash,
                        is_subscription,
                        tax_deductible,
                        tax_category,
                        tax_year,
                        tax_note,
                        receipt_uri,
                        transfer_group_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, NULL, ?)
                    """,
                    (
                        txn.txn_date,
                        txn.amount_cents,
                        txn.txn_type,
                        txn.payee,
                        txn.description,
                        None,
                        txn.account_id,
                        txn.note,
                        txn.source_system,
                        txn.source_uid,
                        self.build_import_hash(txn),
                        txn.transfer_group_id,
                    ),
                )

        return group_id

    def get_transfer_rows(self, transfer_group_id: str) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT txn_id, txn_date, amount_cents, account_id, payee, description, note
                FROM transactions
                WHERE transfer_group_id = ? AND txn_type = 'transfer'
                ORDER BY amount_cents ASC
                """,
                (transfer_group_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_transactions(self, limit: int = 300) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.amount_cents,
                    t.txn_type,
                    t.description,
                    NULLIF(t.description, '') AS description_display,
                    t.category_id,
                    c.name AS category_name,
                    t.account_id,
                    a.name AS account_name,
                    t.is_subscription,
                    t.tax_deductible,
                    t.tax_category,
                    t.transfer_group_id
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                LEFT JOIN categories c ON c.category_id = t.category_id
                ORDER BY t.txn_date ASC, t.txn_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_transactions_for_month(self, year: int, month: int, limit: int = 2000) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.amount_cents,
                    t.txn_type,
                    t.description,
                    NULLIF(t.description, '') AS description_display,
                    t.category_id,
                    c.name AS category_name,
                    t.account_id,
                    a.name AS account_name,
                    t.is_subscription,
                    t.tax_deductible,
                    t.tax_category,
                    t.transfer_group_id
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                LEFT JOIN categories c ON c.category_id = t.category_id
                WHERE strftime('%Y', t.txn_date) = ?
                  AND strftime('%m', t.txn_date) = ?
                ORDER BY t.txn_date ASC, t.txn_id ASC
                LIMIT ?
                """,
                (str(year), f"{month:02d}", limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_available_months(self) -> list[str]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT substr(txn_date, 1, 7) AS year_month
                FROM transactions
                WHERE txn_date IS NOT NULL
                ORDER BY year_month DESC
                """
            ).fetchall()
            return [str(row["year_month"]) for row in rows if row["year_month"]]

    def get_transaction(self, txn_id: int) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    txn_id,
                    txn_date,
                    amount_cents,
                    txn_type,
                    payee,
                    description,
                    category_id,
                    account_id,
                    note,
                    source_system,
                    source_uid,
                    import_hash,
                    is_subscription,
                    tax_deductible,
                    tax_category,
                    tax_note,
                    receipt_uri,
                    transfer_group_id
                FROM transactions
                WHERE txn_id = ?
                """,
                (txn_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_transaction(self, txn_id: int, txn: TransactionInput) -> int:
        if txn.amount_cents == 0:
            raise ValueError("amount_cents must not be 0")
        if txn.txn_type not in {"income", "expense", "transfer"}:
            raise ValueError("txn_type must be one of: income, expense, transfer")
        if txn.txn_type == "transfer" and not txn.transfer_group_id:
            raise ValueError("transfer transactions require transfer_group_id")

        tax_year = datetime.strptime(txn.txn_date, "%Y-%m-%d").year if txn.tax_deductible else None
        import_hash = txn.import_hash or self.build_import_hash(txn)

        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE transactions
                SET txn_date = ?,
                    amount_cents = ?,
                    txn_type = ?,
                    payee = ?,
                    description = ?,
                    category_id = ?,
                    account_id = ?,
                    note = ?,
                    source_system = ?,
                    source_uid = ?,
                    import_hash = ?,
                    is_subscription = ?,
                    tax_deductible = ?,
                    tax_category = ?,
                    tax_year = ?,
                    tax_note = ?,
                    receipt_uri = ?,
                    transfer_group_id = ?,
                    updated_at = datetime('now')
                WHERE txn_id = ?
                """,
                (
                    txn.txn_date,
                    txn.amount_cents,
                    txn.txn_type,
                    txn.payee,
                    txn.description,
                    txn.category_id,
                    txn.account_id,
                    txn.note,
                    txn.source_system,
                    txn.source_uid,
                    import_hash,
                    int(txn.is_subscription),
                    int(txn.tax_deductible),
                    txn.tax_category,
                    tax_year,
                    txn.tax_note,
                    txn.receipt_uri,
                    txn.transfer_group_id,
                    txn_id,
                ),
            )
            return int(cur.rowcount or 0)

    def delete_transaction(self, txn_id: int) -> int:
        with self.db.connection() as conn:
            conn.execute("DELETE FROM transaction_splits WHERE txn_id = ?", (txn_id,))
            cur = conn.execute("DELETE FROM transactions WHERE txn_id = ?", (txn_id,))
            return int(cur.rowcount or 0)

    def month_totals_by_type(self, year: int, month: int) -> dict[str, int]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT txn_type, COALESCE(SUM(amount_cents), 0) AS total_cents
                FROM transactions
                WHERE strftime('%Y', txn_date) = ?
                  AND strftime('%m', txn_date) = ?
                GROUP BY txn_type
                """,
                (str(year), f"{month:02d}"),
            ).fetchall()
        totals = {"income": 0, "expense": 0, "transfer": 0}
        for row in rows:
            totals[str(row["txn_type"])] = int(row["total_cents"])
        return totals

    def delete_imported_transactions_for_months(
        self, year_month_keys: set[str], source_system: str
    ) -> int:
        if not year_month_keys:
            return 0

        sorted_keys = sorted(year_month_keys)
        placeholders = ",".join("?" for _ in sorted_keys)
        sql = (
            "DELETE FROM transactions "
            "WHERE source_system = ? "
            f"AND substr(txn_date, 1, 7) IN ({placeholders})"
        )
        params = [source_system, *sorted_keys]

        with self.db.connection() as conn:
            cur = conn.execute(sql, params)
            return int(cur.rowcount or 0)

    def delete_transactions_for_months(self, year_month_keys: set[str]) -> int:
        if not year_month_keys:
            return 0

        sorted_keys = sorted(year_month_keys)
        placeholders = ",".join("?" for _ in sorted_keys)
        month_filter_sql = f"substr(txn_date, 1, 7) IN ({placeholders})"
        params = [*sorted_keys]

        with self.db.connection() as conn:
            conn.execute(
                "DELETE FROM transaction_splits "
                "WHERE txn_id IN (SELECT txn_id FROM transactions WHERE "
                + month_filter_sql
                + ")",
                params,
            )
            cur = conn.execute("DELETE FROM transactions WHERE " + month_filter_sql, params)
            return int(cur.rowcount or 0)
