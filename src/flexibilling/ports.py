"""Protocols that host backends implement to plug into FlexiBilling."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, TypeAlias

from .models import (
    AssetName,
    BalanceTransaction,
    BalanceTransactionCreate,
    BillingProduct,
    BillingRule,
    BillingStats,
    CustomerBalance,
    CustomerId,
    RecordId,
    ServiceName,
    UsageRecord,
    UsageRecordCreate,
    UsageSummary,
)

Session: TypeAlias = Any
TransactionFactory: TypeAlias = Callable[[], AbstractAsyncContextManager[Session]]
ServiceFactory: TypeAlias = Callable[[], Any]


class BillingRepository(Protocol):
    """Persistence port for balances, rules, products, transactions, and queue state."""

    async def get_active_rules(
        self, service: ServiceName, *, session: Session | None = None
    ) -> Sequence[BillingRule]: ...

    async def get_customer_balances(
        self, customer_id: CustomerId, *, session: Session | None = None
    ) -> Sequence[CustomerBalance]: ...

    async def upsert_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        amount: Decimal,
        *,
        session: Session,
    ) -> CustomerBalance | Decimal: ...

    async def decrement_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        deduction: Decimal,
        *,
        session: Session,
    ) -> Decimal: ...

    async def increment_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        addition: Decimal,
        *,
        session: Session,
    ) -> Decimal: ...

    async def create_transaction(
        self, data: BalanceTransactionCreate, *, session: Session
    ) -> BalanceTransaction: ...

    async def get_transaction_for_usage(
        self,
        reference_id: RecordId,
        service: ServiceName,
        customer_id: CustomerId,
        *,
        session: Session,
    ) -> BalanceTransaction | None: ...

    async def get_transaction_by_reference(
        self, payment_reference: str, *, session: Session | None = None
    ) -> BalanceTransaction | None: ...

    async def get_products_for_external_ids(
        self, external_product_ids: Sequence[str], *, session: Session | None = None
    ) -> Sequence[BillingProduct]: ...

    async def get_pending_records(
        self, limit: int = 50, *, session: Session
    ) -> Sequence[UsageRecord]: ...

    async def mark_record_processed(self, record_id: RecordId, *, session: Session) -> None: ...

    async def mark_record_failed(
        self, record_id: RecordId, error_message: str, *, session: Session
    ) -> None: ...

    async def mark_record_skipped(self, record_id: RecordId, *, session: Session) -> None: ...


class UsageRepository(Protocol):
    """Persistence port for usage records written by ``billing.session``."""

    async def create(
        self, data: UsageRecordCreate, *, session: Session | None = None
    ) -> UsageRecord | None: ...

    async def get_by_customer(
        self, customer_id: CustomerId, skip: int = 0, limit: int = 100
    ) -> Sequence[UsageRecord]: ...

    async def get_usage_summary(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> Sequence[UsageSummary]: ...

    async def get_usage_records(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        service: ServiceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[UsageRecord], int]: ...


class BillingCache(Protocol):
    """Materialized-view port used by the gatekeeper and dashboard counters."""

    async def set_balances(
        self, customer_id: CustomerId, balances: dict[AssetName, Decimal]
    ) -> None: ...

    async def update_single_balance(
        self, customer_id: CustomerId, asset_type: AssetName, new_amount: Decimal
    ) -> None: ...

    async def get_balances(self, customer_id: CustomerId) -> dict[str, str]: ...

    async def can_transact(self, customer_id: CustomerId) -> bool: ...

    async def get_asset_amount(
        self, customer_id: CustomerId, asset_type: AssetName
    ) -> Decimal | None: ...

    async def delete_balances(self, customer_id: CustomerId) -> None: ...

    async def increment_stats(
        self, customer_id: CustomerId, month: str, stats: BillingStats
    ) -> None: ...

    async def get_stats(self, customer_id: CustomerId, month: str) -> dict[str, str]: ...

    async def push_feed_event(
        self,
        customer_id: CustomerId,
        *,
        action: str,
        cost: str,
        result: str,
        time: object | None = None,
    ) -> None: ...

    async def get_feed(self, customer_id: CustomerId, limit: int = 20) -> list[dict[str, Any]]: ...

    async def delete_customer_cache(self, customer_id: CustomerId) -> None: ...
