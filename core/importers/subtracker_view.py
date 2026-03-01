from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_VIEW_NAME = "v_budgetpal_subscriptions"
REQUIRED_VIEW_VERSION = "1"


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
                    autopay,
                    active
                FROM v_budgetpal_subscriptions
                WHERE active = 1
                ORDER BY renewal_date ASC, vendor ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]
