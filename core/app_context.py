from __future__ import annotations

from pathlib import Path

from core.importers.subtracker_view import SubTrackerViewImporter
from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.accounts_repo import AccountsRepository
from core.persistence.repositories.bills_repo import BillsRepository
from core.persistence.repositories.buckets_repo import BucketsRepository
from core.persistence.repositories.budgets_repo import BudgetsRepository
from core.persistence.repositories.categories_repo import CategoriesRepository
from core.persistence.repositories.sub_payment_mappings_repo import (
    SubPaymentMappingsRepository,
)
from core.persistence.repositories.tax_repo import TaxRepository
from core.persistence.repositories.transactions_repo import TransactionsRepository
from core.services.bills import BillsService
from core.services.budgeting import BudgetingService
from core.services.subscription_payments import SubscriptionPaymentsService
from core.services.subscriptions import SubscriptionsService
from core.services.tax import TaxService
from core.services.transactions import TransactionsService


class BudgetPalContext:
    def __init__(self, db: BudgetPalDatabase, settings: dict) -> None:
        self.db = db
        self.settings = settings

        self.categories_repo = CategoriesRepository(db)
        self.accounts_repo = AccountsRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.budgets_repo = BudgetsRepository(db)
        self.bills_repo = BillsRepository(db)
        self.buckets_repo = BucketsRepository(db)
        self.tax_repo = TaxRepository(db)
        self.sub_payment_mappings_repo = SubPaymentMappingsRepository(db)

        self.transactions_service = TransactionsService(self.transactions_repo)
        self.budgeting_service = BudgetingService(self.budgets_repo, self.transactions_repo)
        self.bills_service = BillsService(self.bills_repo)
        self.tax_service = TaxService(self.tax_repo)

        self.subscriptions_service: SubscriptionsService | None = None
        self.subscription_payments_service: SubscriptionPaymentsService | None = None
        self.refresh_settings(settings)

    def refresh_settings(self, settings: dict) -> None:
        self.settings = settings
        subtracker_db = str(settings.get("subtracker", {}).get("database_path", "")).strip()
        self.subscriptions_service = None
        self.subscription_payments_service = None
        if subtracker_db:
            importer = SubTrackerViewImporter(Path(subtracker_db))
            self.subscriptions_service = SubscriptionsService(
                importer,
                self.bills_repo,
                self.categories_repo,
            )
            self.subscription_payments_service = SubscriptionPaymentsService(
                importer,
                self.sub_payment_mappings_repo,
            )
