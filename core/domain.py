from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransactionInput:
    txn_date: str
    amount_cents: int
    txn_type: str
    payee: str
    account_id: int
    category_id: Optional[int] = None
    description: Optional[str] = None
    note: Optional[str] = None
    source_system: Optional[str] = None
    source_uid: Optional[str] = None
    import_period_key: Optional[str] = None
    payment_type: Optional[str] = None
    import_hash: Optional[str] = None
    is_subscription: bool = False
    tax_deductible: bool = False
    tax_category: Optional[str] = None
    tax_note: Optional[str] = None
    receipt_uri: Optional[str] = None
    transfer_group_id: Optional[str] = None


@dataclass(frozen=True)
class TransactionSplitInput:
    category_id: int
    amount_cents: int
    note: Optional[str] = None


@dataclass(frozen=True)
class TransferInput:
    txn_date: str
    amount_cents: int
    from_account_id: int
    to_account_id: int
    payee: str
    description: Optional[str] = None
    note: Optional[str] = None
