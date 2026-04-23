from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from core.domain import TransactionInput, TransferInput
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
                (txn.import_period_key or txn.txn_date[:7]).strip(),
                (txn.payment_type or "").strip().lower(),
                str(int(txn.is_subscription)),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_transaction(self, txn: TransactionInput) -> int:
        if txn.txn_type not in {"income", "expense", "transfer"}:
            raise ValueError("txn_type must be one of: income, expense, transfer")
        if txn.txn_type == "transfer" and not txn.transfer_group_id:
            raise ValueError("transfer transactions require transfer_group_id")

        effective_import_period_key = txn.import_period_key or txn.txn_date[:7]
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
                    import_period_key,
                    payment_type,
                    import_hash,
                    is_subscription,
                    tax_deductible,
                    tax_category,
                    tax_year,
                    tax_note,
                    receipt_uri,
                    transfer_group_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    effective_import_period_key,
                    txn.payment_type,
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

    def add_transfer(self, transfer: TransferInput) -> str:
        if transfer.amount_cents <= 0:
            raise ValueError("Transfer amount must be positive cents")
        if transfer.from_account_id == transfer.to_account_id:
            raise ValueError("Transfer accounts must be different")

        group_id = str(transfer.transfer_group_id or uuid.uuid4())
        source_system = str(transfer.source_system or "manual").strip() or "manual"
        source_uid_base = str(transfer.source_uid or f"transfer:{group_id}").strip() or f"transfer:{group_id}"
        import_period_key = str(transfer.import_period_key or transfer.txn_date[:7]).strip() or transfer.txn_date[:7]
        with self.db.connection() as conn:
            payment_type = self._next_transfer_payment_type(conn)
            out_txn = TransactionInput(
                txn_date=transfer.txn_date,
                amount_cents=-transfer.amount_cents,
                txn_type="transfer",
                payee=transfer.payee,
                description=transfer.description,
                category_id=transfer.category_id,
                account_id=transfer.from_account_id,
                note=transfer.note,
                source_system=source_system,
                source_uid=f"{source_uid_base}:out",
                import_period_key=import_period_key,
                payment_type=payment_type,
                transfer_group_id=group_id,
            )
            in_txn = TransactionInput(
                txn_date=transfer.txn_date,
                amount_cents=transfer.amount_cents,
                txn_type="transfer",
                payee=transfer.payee,
                description=transfer.description,
                category_id=transfer.category_id,
                account_id=transfer.to_account_id,
                note=transfer.note,
                source_system=source_system,
                source_uid=f"{source_uid_base}:in",
                import_period_key=import_period_key,
                payment_type=payment_type,
                transfer_group_id=group_id,
            )

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
                        import_period_key,
                        payment_type,
                        import_hash,
                        is_subscription,
                        tax_deductible,
                        tax_category,
                        tax_year,
                        tax_note,
                        receipt_uri,
                        transfer_group_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, NULL, ?)
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
                        txn.import_period_key,
                        txn.payment_type,
                        self.build_import_hash(txn),
                        txn.transfer_group_id,
                    ),
                )

        return group_id

    @staticmethod
    def _next_transfer_payment_type(conn) -> str:
        rows = conn.execute(
            """
            SELECT payment_type
            FROM transactions
            WHERE payment_type LIKE 'transfer-%'
            """
        ).fetchall()
        max_seq = 0
        for row in rows:
            raw = str(row["payment_type"] or "").strip().lower()
            if not raw.startswith("transfer-"):
                continue
            suffix = raw[9:]
            if not suffix.isdigit():
                continue
            seq = int(suffix)
            if seq > max_seq:
                max_seq = seq

        next_seq = max_seq + 1
        if next_seq > 99_999:
            next_seq = 1
        return f"transfer-{next_seq:05d}"

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

    def update_manual_transfer_group(self, transfer_group_id: str, transfer: TransferInput) -> int:
        if transfer.amount_cents <= 0:
            raise ValueError("Transfer amount must be positive cents")
        if transfer.from_account_id == transfer.to_account_id:
            raise ValueError("Transfer accounts must be different")

        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT txn_id, amount_cents, source_system, payment_type
                FROM transactions
                WHERE transfer_group_id = ?
                  AND txn_type = 'transfer'
                ORDER BY txn_id ASC
                """,
                (transfer_group_id,),
            ).fetchall()
            if len(rows) < 2:
                return 0
            if any(str(row["source_system"] or "").strip().lower() != "manual" for row in rows):
                return 0

            payment_type = next(
                (str(row["payment_type"]).strip() for row in rows if str(row["payment_type"] or "").strip()),
                "",
            )
            if not payment_type:
                payment_type = self._next_transfer_payment_type(conn)
            import_period_key = str(transfer.import_period_key or transfer.txn_date[:7]).strip() or transfer.txn_date[:7]

            updated = 0
            for row in rows:
                txn_id = int(row["txn_id"])
                old_amount = int(row["amount_cents"])
                is_out = old_amount < 0
                new_amount = -transfer.amount_cents if is_out else transfer.amount_cents
                new_account_id = transfer.from_account_id if is_out else transfer.to_account_id
                cur = conn.execute(
                    """
                    UPDATE transactions
                    SET txn_date = ?,
                        amount_cents = ?,
                        payee = ?,
                        description = ?,
                        category_id = ?,
                        account_id = ?,
                        note = ?,
                        import_period_key = ?,
                        payment_type = ?,
                        updated_at = datetime('now')
                    WHERE txn_id = ?
                    """,
                    (
                        transfer.txn_date,
                        new_amount,
                        transfer.payee,
                        transfer.description,
                        transfer.category_id,
                        new_account_id,
                        transfer.note,
                        import_period_key,
                        payment_type,
                        txn_id,
                    ),
                )
                updated += int(cur.rowcount or 0)
            return updated

    def delete_manual_transfer_group(self, transfer_group_id: str) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM transactions
                WHERE transfer_group_id = ?
                  AND txn_type = 'transfer'
                  AND lower(coalesce(source_system, '')) = 'manual'
                """,
                (transfer_group_id,),
            )
            return int(cur.rowcount or 0)

    def list_transactions(self, limit: int = 300) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.amount_cents,
                    t.txn_type,
                    t.source_system,
                    t.description,
                    t.note,
                    NULLIF(t.description, '') AS description_display,
                    t.category_id,
                    c.name AS category_name,
                    t.account_id,
                    a.name AS account_name,
                    COALESCE(a.is_external, 0) AS account_is_external,
                    t.import_period_key,
                    t.payment_type,
                    t.is_cleared,
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
        month_key = f"{int(year):04d}-{int(month):02d}"
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.amount_cents,
                    t.txn_type,
                    t.source_system,
                    t.description,
                    t.note,
                    NULLIF(t.description, '') AS description_display,
                    t.category_id,
                    c.name AS category_name,
                    t.account_id,
                    a.name AS account_name,
                    COALESCE(a.is_external, 0) AS account_is_external,
                    t.import_period_key,
                    t.payment_type,
                    t.is_cleared,
                    t.is_subscription,
                    t.tax_deductible,
                    t.tax_category,
                    t.transfer_group_id
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                LEFT JOIN categories c ON c.category_id = t.category_id
                WHERE (
                        t.import_period_key = ?
                        OR (
                            coalesce(trim(t.import_period_key), '') = ''
                            AND substr(t.txn_date, 1, 7) = ?
                        )
                )
                ORDER BY t.txn_date ASC, t.txn_id ASC
                LIMIT ?
                """,
                (month_key, month_key, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_transfer_summaries_for_month(self, year: int, month: int, limit: int = 2000) -> list[dict]:
        month_key = f"{int(year):04d}-{int(month):02d}"
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.transfer_group_id,
                    MIN(t.txn_date) AS txn_date,
                    COALESCE(
                        MAX(
                            CASE
                                WHEN lower(coalesce(t.payment_type, '')) LIKE 'transfer-%'
                                THEN substr(lower(t.payment_type), 10, 5)
                                ELSE NULL
                            END
                        ),
                        ''
                    ) AS transfer_id_suffix,
                    MAX(CASE WHEN t.amount_cents < 0 THEN a.name END) AS from_account_alias,
                    MAX(CASE WHEN t.amount_cents < 0 THEN t.account_id END) AS from_account_id,
                    MAX(CASE WHEN t.amount_cents > 0 THEN a.name END) AS to_account_alias,
                    MAX(CASE WHEN t.amount_cents > 0 THEN t.account_id END) AS to_account_id,
                    COALESCE(
                        MAX(CASE WHEN t.amount_cents > 0 THEN t.amount_cents END),
                        ABS(MIN(CASE WHEN t.amount_cents < 0 THEN t.amount_cents END)),
                        0
                    ) AS amount_cents
                    ,
                    COALESCE(MAX(NULLIF(t.description, '')), '') AS description,
                    COALESCE(MAX(NULLIF(t.note, '')), '') AS note,
                    COALESCE(MAX(NULLIF(t.payment_type, '')), '') AS payment_type,
                    lower(COALESCE(MAX(NULLIF(t.source_system, '')), 'manual')) AS source_system,
                    CASE
                        WHEN lower(COALESCE(MAX(NULLIF(t.source_system, '')), 'manual')) = 'manual'
                        THEN 'manual'
                        ELSE 'rule-based'
                    END AS transfer_type
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                WHERE t.txn_type = 'transfer'
                  AND t.transfer_group_id IS NOT NULL
                  AND (
                        t.import_period_key = ?
                        OR (
                            coalesce(trim(t.import_period_key), '') = ''
                            AND substr(t.txn_date, 1, 7) = ?
                        )
                  )
                GROUP BY t.transfer_group_id
                ORDER BY MIN(t.txn_date) ASC, t.transfer_group_id ASC
                LIMIT ?
                """,
                (month_key, month_key, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_account_ledger_for_month(
        self,
        year: int,
        month: int,
        account_id: int,
        *,
        include_prior_uncleared: bool = False,
        limit: int = 10000,
    ) -> list[dict]:
        month_key = f"{int(year):04d}-{int(month):02d}"
        month_start = f"{month_key}-01"
        with self.db.connection() as conn:
            sql = """
                SELECT
                    t.txn_id,
                    t.txn_date,
                    t.txn_type,
                    t.description,
                    t.note,
                    t.payment_type,
                    t.amount_cents,
                    t.is_cleared,
                    t.category_id,
                    c.name AS category_name,
                    t.account_id,
                    a.name AS account_name,
                    t.import_period_key
                FROM transactions t
                JOIN accounts a ON a.account_id = t.account_id
                LEFT JOIN categories c ON c.category_id = t.category_id
                WHERE t.account_id = ?
                  AND t.txn_type IN ('income', 'expense', 'transfer')
            """
            params: list[object] = [int(account_id)]
            if include_prior_uncleared:
                sql += """
                      AND (
                            substr(t.txn_date, 1, 7) = ?
                            OR (t.txn_date < ? AND COALESCE(t.is_cleared, 0) = 0)
                      )
                    ORDER BY t.txn_date ASC, t.txn_id ASC
                    LIMIT ?
                """
                params.extend((month_key, month_start, limit))
            else:
                sql += """
                      AND substr(t.txn_date, 1, 7) = ?
                    ORDER BY t.txn_date ASC, t.txn_id ASC
                    LIMIT ?
                """
                params.extend((month_key, limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def list_checking_ledger_for_month(
        self,
        year: int,
        month: int,
        account_id: int | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        with self.db.connection() as conn:
            effective_account_id = int(account_id) if account_id is not None else None
            if effective_account_id is None:
                account_row = conn.execute(
                    """
                    SELECT account_id
                    FROM accounts
                    WHERE lower(trim(account_type)) = 'checking'
                    ORDER BY account_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if account_row is None:
                    return []
                effective_account_id = int(account_row["account_id"])
        return self.list_account_ledger_for_month(
            year=year,
            month=month,
            account_id=effective_account_id,
            include_prior_uncleared=True,
            limit=limit,
        )

    def set_transaction_cleared(self, txn_id: int, is_cleared: bool) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                UPDATE transactions
                SET is_cleared = ?,
                    updated_at = datetime('now')
                WHERE txn_id = ?
                """,
                (1 if is_cleared else 0, int(txn_id)),
            )
            return int(cur.rowcount or 0)

    def set_transaction_note(self, txn_id: int, note: str | None) -> int:
        note_text = str(note or "").strip() or None
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT txn_type, transfer_group_id
                FROM transactions
                WHERE txn_id = ?
                """,
                (int(txn_id),),
            ).fetchone()
            if row is None:
                return 0

            transfer_group_id = str(row["transfer_group_id"] or "").strip()
            if str(row["txn_type"] or "").strip().lower() == "transfer" and transfer_group_id:
                cur = conn.execute(
                    """
                    UPDATE transactions
                    SET note = ?,
                        updated_at = datetime('now')
                    WHERE txn_type = 'transfer'
                      AND transfer_group_id = ?
                    """,
                    (note_text, transfer_group_id),
                )
                return int(cur.rowcount or 0)

            cur = conn.execute(
                """
                UPDATE transactions
                SET note = ?,
                    updated_at = datetime('now')
                WHERE txn_id = ?
                """,
                (note_text, int(txn_id)),
            )
            return int(cur.rowcount or 0)

    def get_account_month_beginning_balance(
        self,
        year: int,
        month: int,
        account_id: int,
    ) -> int:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT beginning_balance_cents
                FROM account_month_settings
                WHERE year = ? AND month = ? AND account_id = ?
                """,
                (int(year), int(month), int(account_id)),
            ).fetchone()
        return int(row["beginning_balance_cents"]) if row else 0

    def get_checking_month_beginning_balance(
        self,
        year: int,
        month: int,
        account_id: int | None = None,
    ) -> int:
        with self.db.connection() as conn:
            effective_account_id = int(account_id) if account_id is not None else None
            if effective_account_id is None:
                account_row = conn.execute(
                    """
                    SELECT account_id
                    FROM accounts
                    WHERE lower(trim(account_type)) = 'checking'
                    ORDER BY account_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if account_row is None:
                    return 0
                effective_account_id = int(account_row["account_id"])
        return self.get_account_month_beginning_balance(
            year=year,
            month=month,
            account_id=effective_account_id,
        )

    def set_account_month_beginning_balance(
        self,
        year: int,
        month: int,
        beginning_balance_cents: int,
        account_id: int,
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO account_month_settings(
                    year,
                    month,
                    account_id,
                    beginning_balance_cents,
                    updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(year, month, account_id) DO UPDATE SET
                    beginning_balance_cents = excluded.beginning_balance_cents,
                    updated_at = datetime('now')
                """,
                (
                    int(year),
                    int(month),
                    int(account_id),
                    int(beginning_balance_cents),
                ),
            )

    def get_account_month_statement(
        self,
        year: int,
        month: int,
        account_id: int,
    ) -> dict:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT statement_ending_balance_cents, statement_ending_date
                FROM account_month_settings
                WHERE year = ? AND month = ? AND account_id = ?
                """,
                (int(year), int(month), int(account_id)),
            ).fetchone()
        if row is None:
            return {
                "statement_ending_balance_cents": None,
                "statement_ending_date": None,
            }
        ending_cents = row["statement_ending_balance_cents"]
        return {
            "statement_ending_balance_cents": (
                int(ending_cents) if ending_cents is not None else None
            ),
            "statement_ending_date": str(row["statement_ending_date"] or "").strip() or None,
        }

    def set_account_month_statement(
        self,
        year: int,
        month: int,
        account_id: int,
        statement_ending_balance_cents: int | None,
        statement_ending_date: str | None,
    ) -> None:
        normalized_date = str(statement_ending_date or "").strip() or None
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO account_month_settings(
                    year,
                    month,
                    account_id,
                    beginning_balance_cents,
                    statement_ending_balance_cents,
                    statement_ending_date,
                    updated_at
                )
                VALUES (?, ?, ?, 0, ?, ?, datetime('now'))
                ON CONFLICT(year, month, account_id) DO UPDATE SET
                    statement_ending_balance_cents = excluded.statement_ending_balance_cents,
                    statement_ending_date = excluded.statement_ending_date,
                    updated_at = datetime('now')
                """,
                (
                    int(year),
                    int(month),
                    int(account_id),
                    (
                        int(statement_ending_balance_cents)
                        if statement_ending_balance_cents is not None
                        else None
                    ),
                    normalized_date,
                ),
            )

    def set_checking_month_beginning_balance(
        self,
        year: int,
        month: int,
        beginning_balance_cents: int,
        account_id: int | None = None,
    ) -> None:
        with self.db.connection() as conn:
            effective_account_id = int(account_id) if account_id is not None else None
            if effective_account_id is None:
                account_row = conn.execute(
                    """
                    SELECT account_id
                    FROM accounts
                    WHERE lower(trim(account_type)) = 'checking'
                    ORDER BY account_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if account_row is None:
                    raise ValueError("No checking account is defined.")
                effective_account_id = int(account_row["account_id"])
        self.set_account_month_beginning_balance(
            year=year,
            month=month,
            beginning_balance_cents=beginning_balance_cents,
            account_id=effective_account_id,
        )

    def list_available_months(self) -> list[str]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    CASE
                        WHEN coalesce(trim(import_period_key), '') <> ''
                        THEN trim(import_period_key)
                        ELSE substr(txn_date, 1, 7)
                    END AS year_month
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
                    import_period_key,
                    payment_type,
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
        if txn.txn_type not in {"income", "expense", "transfer"}:
            raise ValueError("txn_type must be one of: income, expense, transfer")
        if txn.txn_type == "transfer" and not txn.transfer_group_id:
            raise ValueError("transfer transactions require transfer_group_id")

        effective_import_period_key = txn.import_period_key or txn.txn_date[:7]
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
                    import_period_key = ?,
                    payment_type = ?,
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
                    effective_import_period_key,
                    txn.payment_type,
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

    def delete_imported_transactions_for_import_period(
        self, import_period_key: str, source_system: str
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM transactions
                WHERE source_system = ?
                  AND import_period_key = ?
                """,
                (source_system, import_period_key),
            )
            return int(cur.rowcount or 0)

    def delete_transactions_for_import_period(self, import_period_key: str) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM transactions
                WHERE import_period_key = ?
                  AND NOT (
                        txn_type = 'transfer'
                    AND lower(coalesce(source_system, '')) = 'manual'
                  )
                """,
                (import_period_key,),
            )
            return int(cur.rowcount or 0)

    def delete_transactions_for_months(self, year_month_keys: set[str]) -> int:
        if not year_month_keys:
            return 0

        sorted_keys = sorted(year_month_keys)
        placeholders = ",".join("?" for _ in sorted_keys)
        month_filter_sql = f"substr(txn_date, 1, 7) IN ({placeholders})"
        params = [*sorted_keys]

        with self.db.connection() as conn:
            cur = conn.execute("DELETE FROM transactions WHERE " + month_filter_sql, params)
            return int(cur.rowcount or 0)
