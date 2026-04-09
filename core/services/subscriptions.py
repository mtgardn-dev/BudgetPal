from __future__ import annotations

from core.importers.subtracker_view import SubTrackerViewImporter
from core.persistence.repositories.bills_repo import BillsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository


class SubscriptionsService:
    def __init__(
        self,
        subtracker_importer: SubTrackerViewImporter,
        bills_repo: BillsRepository,
        categories_repo: CategoriesRepository,
    ) -> None:
        self.subtracker_importer = subtracker_importer
        self.bills_repo = bills_repo
        self.categories_repo = categories_repo
        self.last_mapping_errors: list[str] = []

    def _resolve_budgetpal_category_id(
        self,
        row: dict,
        category_ids: set[int],
        uncategorized_id: int,
    ) -> tuple[int, str | None]:
        raw_id = row.get("budgetpal_category_id")
        sub_id = row.get("sub_id")
        vendor = row.get("vendor")
        if raw_id is None or str(raw_id).strip() == "":
            return (
                uncategorized_id,
                "SubTracker category id missing for subscription "
                f"sub_id={sub_id}, vendor='{vendor}'. Falling back to Uncategorized.",
            )
        try:
            category_id = int(raw_id)
        except (TypeError, ValueError):
            return (
                uncategorized_id,
                "SubTracker category id "
                f"'{raw_id}' for subscription sub_id={sub_id}, vendor='{vendor}' is invalid. "
                "Falling back to Uncategorized.",
            )
        if category_id not in category_ids:
            return (
                uncategorized_id,
                "SubTracker category id "
                f"'{category_id}' for subscription sub_id={sub_id}, vendor='{vendor}' "
                "does not match any BudgetPal category id. Falling back to Uncategorized.",
            )
        return category_id, None

    def refresh_subtracker_bills(self, year: int | None = None, month: int | None = None) -> int:
        self.last_mapping_errors = []
        all_subscriptions = self.subtracker_importer.load_active_subscriptions()
        subscriptions = list(all_subscriptions)
        if year is not None and month is not None:
            target = f"{int(year):04d}-{int(month):02d}"
            month_matches = [
                row for row in all_subscriptions if str(row.get("renewal_date", "")).startswith(target)
            ]
            # If selected-month rows are missing (for example stale next_renewal dates),
            # still import all active subscriptions so recurring rows remain visible.
            subscriptions = month_matches if month_matches else list(all_subscriptions)

        categories = self.categories_repo.list_active()
        category_ids = {int(row["category_id"]) for row in categories}
        uncategorized_id = next(
            (
                int(row["category_id"])
                for row in categories
                if str(row["name"]).strip().lower() == "uncategorized"
            ),
            None,
        )
        if uncategorized_id is None:
            uncategorized_id = self.categories_repo.upsert("Uncategorized", is_income=False)
            category_ids.add(uncategorized_id)
        else:
            category_ids.add(int(uncategorized_id))

        # Backfill category mapping for any previously imported SubTracker bills
        # so rows imported before this mapping fix no longer remain Uncategorized.
        for row in all_subscriptions:
            category_id, mapping_error = self._resolve_budgetpal_category_id(
                row,
                category_ids=category_ids,
                uncategorized_id=int(uncategorized_id),
            )
            if mapping_error:
                self.last_mapping_errors.append(mapping_error)
            self.bills_repo.update_category_for_source(
                source_system="subtracker",
                source_uid=str(row["sub_id"]),
                category_id=category_id,
            )

        for row in subscriptions:
            category_id, mapping_error = self._resolve_budgetpal_category_id(
                row,
                category_ids=category_ids,
                uncategorized_id=int(uncategorized_id),
            )
            if mapping_error:
                self.last_mapping_errors.append(mapping_error)
            interval_count = 1
            interval_unit = "months"
            raw_frequency = str(row.get("frequency") or "").strip().lower()
            if raw_frequency in {"annual", "annually", "yearly", "year"}:
                interval_unit = "years"
            elif raw_frequency in {"monthly", "month"}:
                interval_unit = "months"
            elif raw_frequency in {"quarterly", "quarter"}:
                interval_count = 3
                interval_unit = "months"
            elif raw_frequency in {"biweekly", "bi-weekly"}:
                interval_count = 2
                interval_unit = "weeks"
            elif raw_frequency in {"weekly", "week"}:
                interval_unit = "weeks"
            elif raw_frequency in {"daily", "day"}:
                interval_unit = "days"
            elif raw_frequency in {"adhoc", "ad hoc", "one-time", "onetime", "once"}:
                interval_unit = "once"
            elif raw_frequency.startswith("every "):
                # Examples: "every 2 months", "every 6 weeks"
                parts = raw_frequency.split()
                if len(parts) >= 3:
                    try:
                        interval_count = max(1, int(parts[1]))
                    except ValueError:
                        interval_count = 1
                    unit = parts[2].lower()
                    if unit in {"day", "days"}:
                        interval_unit = "days"
                    elif unit in {"week", "weeks"}:
                        interval_unit = "weeks"
                    elif unit in {"year", "years"}:
                        interval_unit = "years"
                    elif unit in {"month", "months"}:
                        interval_unit = "months"
                    else:
                        interval_unit = "months"

            self.bills_repo.upsert_bill(
                name=row["vendor"],
                frequency=row["frequency"],
                due_day=int(row["renewal_date"].split("-")[2]),
                default_amount_cents=int(row["amount_cents"]),
                category_id=category_id,
                autopay=bool(row["autopay"]),
                source_system="subtracker",
                source_uid=str(row["sub_id"]),
                notes="Imported from SubTracker",
                start_date=str(row["renewal_date"]),
                interval_count=interval_count,
                interval_unit=interval_unit,
            )
        if self.last_mapping_errors:
            self.last_mapping_errors = list(dict.fromkeys(self.last_mapping_errors))
        return len(subscriptions)
