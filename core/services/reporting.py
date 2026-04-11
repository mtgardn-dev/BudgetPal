from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.path_registry import BudgetPalPathRegistry
from core.persistence.db import BudgetPalDatabase


class ReportingService:
    def __init__(self, db: BudgetPalDatabase) -> None:
        self.db = db

    def export_archive(self, output_zip: Path | None = None) -> Path:
        target = output_zip or (
            BudgetPalPathRegistry.exports_dir()
            / f"budgetpal_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )

        export_dir = BudgetPalPathRegistry.exports_dir() / "_staging"
        export_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self._write_csv(conn, "transactions", export_dir / "transactions.csv")
            self._write_csv(conn, "bills", export_dir / "bills.csv")
            self._write_csv(conn, "bill_occurrences", export_dir / "bill_occurrences.csv")
            self._write_csv(conn, "budget_months", export_dir / "budgets.csv")
            self._write_csv(conn, "budget_lines", export_dir / "budget_lines.csv")
            self._write_csv(conn, "savings_buckets", export_dir / "buckets.csv")
            self._write_csv(conn, "bucket_movements", export_dir / "bucket_movements.csv")

        meta = {
            "schema_version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "app_version": "0.1.0",
        }
        (export_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        with ZipFile(target, "w", compression=ZIP_DEFLATED) as zf:
            zf.write(self.db.db_path, arcname="budgetpal.sqlite")
            for file_name in [
                "transactions.csv",
                "bills.csv",
                "bill_occurrences.csv",
                "budgets.csv",
                "budget_lines.csv",
                "buckets.csv",
                "bucket_movements.csv",
                "meta.json",
            ]:
                arcname = f"export/{file_name}" if file_name != "meta.json" else file_name
                zf.write(export_dir / file_name, arcname=arcname)

        return target

    def export_global_definitions(self, output_dir: Path) -> list[Path]:
        target_dir = Path(output_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        bills_path = target_dir / f"budgetpal_bill_definitions_{timestamp}.csv"
        income_path = target_dir / f"budgetpal_income_definitions_{timestamp}.csv"
        budget_path = target_dir / f"budgetpal_budget_category_definitions_{timestamp}.csv"

        with sqlite3.connect(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self._write_query_csv(
                conn,
                """
                SELECT
                    b.bill_id AS definition_id,
                    b.name,
                    b.category_id,
                    c.name AS category_name,
                    b.start_date,
                    b.interval_count,
                    b.interval_unit,
                    b.default_amount_cents,
                    b.autopay,
                    b.notes
                FROM bills b
                LEFT JOIN categories c ON c.category_id = b.category_id
                WHERE b.is_active = 1
                  AND lower(trim(b.source_system)) = 'budgetpal'
                ORDER BY lower(coalesce(c.name, '')), lower(b.name), b.bill_id
                """,
                bills_path,
            )
            self._write_query_csv(
                conn,
                """
                SELECT
                    i.income_id AS definition_id,
                    i.description,
                    i.category_id,
                    c.name AS category_name,
                    i.account_id,
                    a.name AS account_name,
                    i.start_date,
                    i.interval_count,
                    i.interval_unit,
                    i.default_amount_cents,
                    i.notes
                FROM income_definitions i
                LEFT JOIN categories c ON c.category_id = i.category_id
                JOIN accounts a ON a.account_id = i.account_id
                WHERE i.is_active = 1
                  AND lower(trim(i.source_system)) = 'budgetpal'
                ORDER BY lower(coalesce(c.name, '')), lower(i.description), i.income_id
                """,
                income_path,
            )
            self._write_query_csv(
                conn,
                """
                SELECT
                    d.definition_id,
                    d.category_id,
                    c.name AS category_name,
                    d.default_amount_cents,
                    d.note
                FROM budget_category_definitions d
                JOIN categories c ON c.category_id = d.category_id
                WHERE d.is_active = 1
                ORDER BY lower(c.name), d.definition_id
                """,
                budget_path,
            )

        return [bills_path, income_path, budget_path]

    def _write_csv(self, conn: sqlite3.Connection, table_name: str, file_path: Path) -> None:
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        if not rows:
            file_path.write_text("", encoding="utf-8")
            return

        fieldnames = rows[0].keys()
        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

    def _write_query_csv(self, conn: sqlite3.Connection, query: str, file_path: Path) -> None:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        fieldnames = [str(col[0]) for col in (cursor.description or [])]
        if not fieldnames:
            file_path.write_text("", encoding="utf-8")
            return

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
