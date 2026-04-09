from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_VIEW_NAME = "v_budgetpal_subscriptions"
REQUIRED_VIEW_VERSION = "2"
PAYMENT_CONTRACT_VERSION = "1"


class SubTrackerIntegrationError(RuntimeError):
    pass


class SubTrackerViewImporter:
    def __init__(self, subtracker_db_path: Path | str) -> None:
        self.subtracker_db_path = Path(subtracker_db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self.subtracker_db_path.exists():
            raise SubTrackerIntegrationError(
                "SubTracker database file was not found. "
                f"Configured path: {self.subtracker_db_path}"
            )
        conn = sqlite3.connect(self.subtracker_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _assert_contract(self, conn: sqlite3.Connection) -> None:
        view = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='view' AND name=?
            """,
            (REQUIRED_VIEW_NAME,),
        ).fetchone()
        if not view:
            raise SubTrackerIntegrationError(
                f"SubTracker view '{REQUIRED_VIEW_NAME}' is missing. "
                "BudgetPal requires this integration view and will not continue."
            )

        meta_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='subtracker_meta'
            """
        ).fetchone()
        if not meta_table:
            raise SubTrackerIntegrationError(
                "SubTracker table 'subtracker_meta' is missing. "
                "BudgetPal requires budgetpal_view_version for compatibility checks."
            )

        row = conn.execute(
            "SELECT value FROM subtracker_meta WHERE key='budgetpal_view_version'"
        ).fetchone()
        if not row:
            raise SubTrackerIntegrationError(
                "subtracker_meta is missing key 'budgetpal_view_version'."
            )

        version = str(row["value"])
        if version != REQUIRED_VIEW_VERSION:
            raise SubTrackerIntegrationError(
                "SubTracker view contract version mismatch. "
                f"Expected {REQUIRED_VIEW_VERSION}, got {version}."
            )

    def load_active_subscriptions(self) -> list[dict]:
        with self._connect() as conn:
            self._assert_contract(conn)
            rows = conn.execute(
                """
                SELECT
                    sub_id,
                    vendor,
                    renewal_date,
                    amount_cents,
                    frequency,
                    category,
                    budgetpal_category_id,
                    autopay,
                    active
                FROM v_budgetpal_subscriptions
                WHERE active = 1
                ORDER BY renewal_date ASC, vendor ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _ensure_payment_contract(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgetpal_payment_ingest (
                ingest_id INTEGER PRIMARY KEY,
                external_source TEXT NOT NULL,
                external_txn_key TEXT NOT NULL,
                subscription_id INTEGER NOT NULL,
                payment_date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                remarks TEXT NOT NULL DEFAULT '',
                applied_payment_id INTEGER NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(external_source, external_txn_key),
                FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE,
                FOREIGN KEY(applied_payment_id) REFERENCES subscription_payments(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO subtracker_meta(key, value)
            VALUES ('budgetpal_payment_contract_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (PAYMENT_CONTRACT_VERSION,),
        )

    def upsert_subscription_payment(
        self,
        *,
        external_source: str,
        external_txn_key: str,
        subscription_id: int,
        payment_date: str,
        amount_cents: int,
        remarks: str,
    ) -> dict:
        if amount_cents < 0:
            raise ValueError("amount_cents must be non-negative for SubTracker payment posting")
        if not external_source.strip():
            raise ValueError("external_source is required")
        if not external_txn_key.strip():
            raise ValueError("external_txn_key is required")

        with self._connect() as conn:
            self._assert_contract(conn)
            self._ensure_payment_contract(conn)

            conn.execute(
                """
                INSERT INTO budgetpal_payment_ingest(
                    external_source,
                    external_txn_key,
                    subscription_id,
                    payment_date,
                    amount_cents,
                    remarks,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(external_source, external_txn_key) DO UPDATE SET
                    subscription_id = excluded.subscription_id,
                    payment_date = excluded.payment_date,
                    amount_cents = excluded.amount_cents,
                    remarks = excluded.remarks,
                    updated_at = datetime('now')
                """,
                (
                    external_source.strip(),
                    external_txn_key.strip(),
                    int(subscription_id),
                    payment_date,
                    int(amount_cents),
                    remarks,
                ),
            )

            row = conn.execute(
                """
                SELECT ingest_id, applied_payment_id
                FROM budgetpal_payment_ingest
                WHERE external_source = ? AND external_txn_key = ?
                """,
                (external_source.strip(), external_txn_key.strip()),
            ).fetchone()
            if not row:
                raise SubTrackerIntegrationError(
                    "Failed to load payment ingest row after upsert."
                )

            payment_id = row["applied_payment_id"]
            amount_value = int(amount_cents) / 100.0
            if payment_id is not None:
                updated = conn.execute(
                    """
                    UPDATE subscription_payments
                    SET subscription_id = ?,
                        payment_date = ?,
                        amount = ?,
                        remarks = ?
                    WHERE id = ?
                    """,
                    (int(subscription_id), payment_date, amount_value, remarks, int(payment_id)),
                ).rowcount
                if not updated:
                    payment_id = None

            created = False
            if payment_id is None:
                cur = conn.execute(
                    """
                    INSERT INTO subscription_payments(
                        subscription_id,
                        payment_date,
                        amount,
                        remarks,
                        created_at
                    ) VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (int(subscription_id), payment_date, amount_value, remarks),
                )
                payment_id = int(cur.lastrowid)
                created = True

            conn.execute(
                """
                UPDATE budgetpal_payment_ingest
                SET applied_payment_id = ?,
                    updated_at = datetime('now')
                WHERE ingest_id = ?
                """,
                (int(payment_id), int(row["ingest_id"])),
            )

            return {
                "payment_id": int(payment_id),
                "created": created,
            }
