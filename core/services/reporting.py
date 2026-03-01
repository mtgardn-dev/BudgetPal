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
