from __future__ import annotations

from difflib import SequenceMatcher

from core.importers.subtracker_view import SubTrackerViewImporter
from core.persistence.repositories.sub_payment_mappings_repo import (
    SubPaymentMappingsRepository,
)


class SubscriptionPaymentsService:
    def __init__(
        self,
        subtracker_importer: SubTrackerViewImporter,
        mappings_repo: SubPaymentMappingsRepository,
    ) -> None:
        self.subtracker_importer = subtracker_importer
        self.mappings_repo = mappings_repo

    @staticmethod
    def _normalize_text(value: object | None) -> list[str]:
        raw = str(value or "").strip().lower()
        return "".join(ch if ch.isalnum() else " " for ch in raw).split()

    def _suggest_sub_id(self, description: str, subscriptions: list[dict]) -> int | None:
        description_words = self._normalize_text(description)
        if not description_words:
            return None
        description_norm = " ".join(description_words)

        best_sub_id: int | None = None
        best_score = 0.0
        for sub in subscriptions:
            vendor_norm = " ".join(self._normalize_text(sub.get("vendor")))
            if not vendor_norm:
                continue
            if vendor_norm in description_norm or description_norm in vendor_norm:
                score = 1.0
            else:
                score = SequenceMatcher(None, description_norm, vendor_norm).ratio()
            if score > best_score:
                best_score = score
                best_sub_id = int(sub["sub_id"])
        if best_score < 0.45:
            return None
        return best_sub_id

    @staticmethod
    def _external_txn_key(row: dict) -> str:
        source_uid = str(row.get("source_uid") or "").strip()
        if source_uid:
            return f"budgetpal:{source_uid}"
        return f"budgetpal:txn:{int(row['txn_id'])}"

    def load_month_candidates(self, year: int, month: int) -> dict:
        subscriptions = self.subtracker_importer.load_active_subscriptions()
        subscriptions_sorted = sorted(
            subscriptions,
            key=lambda r: str(r.get("vendor", "")).lower(),
        )
        candidates = self.mappings_repo.list_subscription_expense_candidates(year, month)

        for row in candidates:
            mapped_sub_id = row.get("sub_id")
            if mapped_sub_id is None:
                mapped_sub_id = self._suggest_sub_id(
                    str(row.get("description") or ""),
                    subscriptions_sorted,
                )
            row["selected_sub_id"] = int(mapped_sub_id) if mapped_sub_id is not None else None

        return {
            "subscriptions": subscriptions_sorted,
            "candidates": candidates,
        }

    def process_month(
        self,
        year: int,
        month: int,
        selections: dict[int, dict[str, int | None]],
    ) -> dict:
        candidates = self.mappings_repo.list_subscription_expense_candidates(year, month)
        candidate_by_id = {int(row["txn_id"]): row for row in candidates}

        posted_count = 0
        updated_count = 0
        error_count = 0
        unmapped_count = 0

        for txn_id, payload in selections.items():
            selected_sub_id = payload.get("sub_id")
            selected_amount_cents = payload.get("amount_cents")
            row = candidate_by_id.get(int(txn_id))
            if not row:
                continue

            self.mappings_repo.upsert_selection(
                int(txn_id),
                selected_sub_id,
                int(selected_amount_cents) if selected_amount_cents is not None else None,
            )
            if selected_sub_id is None:
                unmapped_count += 1
                continue

            external_key = str(row.get("external_txn_key") or self._external_txn_key(row))
            remarks = str(row.get("account_name") or "").strip()
            amount_cents = (
                abs(int(selected_amount_cents))
                if selected_amount_cents is not None
                else abs(int(row.get("display_amount_cents") or row.get("amount_cents") or 0))
            )
            if amount_cents <= 0:
                self.mappings_repo.record_post_error(
                    txn_id=int(txn_id),
                    sub_id=int(selected_sub_id),
                    external_txn_key=external_key,
                    error_text="Amount must be greater than $0.00",
                )
                error_count += 1
                continue
            try:
                result = self.subtracker_importer.upsert_subscription_payment(
                    external_source="budgetpal",
                    external_txn_key=external_key,
                    subscription_id=int(selected_sub_id),
                    payment_date=str(row["txn_date"]),
                    amount_cents=amount_cents,
                    remarks=remarks,
                )
                self.mappings_repo.record_post_success(
                    txn_id=int(txn_id),
                    sub_id=int(selected_sub_id),
                    external_txn_key=external_key,
                    subtracker_payment_id=int(result["payment_id"]),
                )
                if bool(result.get("created")):
                    posted_count += 1
                else:
                    updated_count += 1
            except Exception as exc:  # pragma: no cover - guarded by integration tests
                self.mappings_repo.record_post_error(
                    txn_id=int(txn_id),
                    sub_id=int(selected_sub_id),
                    external_txn_key=external_key,
                    error_text=str(exc),
                )
                error_count += 1

        return {
            "posted_count": posted_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "unmapped_count": unmapped_count,
            "total_candidates": len(candidates),
        }
