from __future__ import annotations

from core.importers.subtracker_view import SubTrackerViewImporter
from core.persistence.repositories.bills_repo import BillsRepository


class SubscriptionsService:
    def __init__(
        self,
        subtracker_importer: SubTrackerViewImporter,
        bills_repo: BillsRepository,
    ) -> None:
        self.subtracker_importer = subtracker_importer
        self.bills_repo = bills_repo

    def refresh_subtracker_bills(self) -> int:
        subscriptions = self.subtracker_importer.load_active_subscriptions()
        for row in subscriptions:
            self.bills_repo.upsert_bill(
                name=row["vendor"],
                frequency=row["frequency"],
                due_day=int(row["renewal_date"].split("-")[2]),
                default_amount_cents=int(row["amount_cents"]),
                autopay=bool(row["autopay"]),
                source_system="subtracker",
                source_uid=str(row["sub_id"]),
                notes="Imported from SubTracker",
            )
        return len(subscriptions)
