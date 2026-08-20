"""In-memory repository and usage adapter for tests and examples."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from ..exceptions import InsufficientFundsError
from ..models import (
    AssetName,
    BalanceTransaction,
    BalanceTransactionCreate,
    BillingProduct,
    BillingRule,
    BillingStatus,
    CustomerBalance,
    CustomerId,
    RecordId,
    ServiceName,
    UsageRecord,
    UsageRecordCreate,
    UsageSummary,
    enum_value,
)
from ..ports import Session


class InMemoryBillingRepository:
    """Reference implementation of the billing persistence protocol."""

    def __init__(
        self,
        *,
        rules: Sequence[BillingRule] = (),
        products: Sequence[BillingProduct] = (),
        records: Sequence[UsageRecord] = (),
    ) -> None:
        self.rules = list(rules)
        self.products = list(products)
        self.records = list(records)
        self.balances: dict[tuple[str, str], Decimal] = {}
        self.transactions: list[BalanceTransaction] = []
        self._next_transaction_id = 1
        self._lock = asyncio.Lock()

    async def get_active_rules(
        self, service: ServiceName, *, session: Session | None = None
    ) -> list[BillingRule]:
        service_name = enum_value(service)
        return sorted(
            [
                rule
                for rule in self.rules
                if rule.is_active and enum_value(rule.service) == service_name
            ],
            key=lambda rule: rule.priority,
        )

    async def get_customer_balances(
        self, customer_id: CustomerId, *, session: Session | None = None
    ) -> list[CustomerBalance]:
        key = str(customer_id)
        return [
            CustomerBalance(customer_id, asset, amount)
            for (customer, asset), amount in self.balances.items()
            if customer == key
        ]

    async def upsert_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        amount: Decimal,
        *,
        session: Session,
    ) -> CustomerBalance:
        async with self._lock:
            key = (str(customer_id), enum_value(asset_type))
            self.balances[key] = Decimal(str(amount))
            return CustomerBalance(customer_id, asset_type, self.balances[key])

    async def decrement_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        deduction: Decimal,
        *,
        session: Session,
    ) -> Decimal:
        async with self._lock:
            key = (str(customer_id), enum_value(asset_type))
            current = self.balances.get(key, Decimal("0"))
            if current < deduction:
                raise InsufficientFundsError(customer_id, "charge")
            self.balances[key] = current - deduction
            return self.balances[key]

    async def increment_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        addition: Decimal,
        *,
        session: Session,
    ) -> Decimal:
        async with self._lock:
            key = (str(customer_id), enum_value(asset_type))
            self.balances[key] = self.balances.get(key, Decimal("0")) + Decimal(str(addition))
            return self.balances[key]

    async def create_transaction(
        self, data: BalanceTransactionCreate, *, session: Session
    ) -> BalanceTransaction:
        transaction = BalanceTransaction(
            customer_id=data.customer_id,
            asset_type=data.asset_type,
            amount=data.amount,
            balance_after=data.balance_after,
            transaction_type=data.transaction_type,
            id=self._next_transaction_id,
            source_usage_id=data.source_usage_id,
            payment_reference=data.payment_reference,
            description=data.description,
        )
        self._next_transaction_id += 1
        self.transactions.append(transaction)
        return transaction

    async def get_transaction_for_usage(
        self,
        reference_id: RecordId,
        service: ServiceName,
        customer_id: CustomerId,
        *,
        session: Session,
    ) -> BalanceTransaction | None:
        service_name = enum_value(service)
        record_ids = {
            record.id
            for record in self.records
            if record.reference_id == reference_id and enum_value(record.service) == service_name
        }
        candidates = [
            transaction
            for transaction in self.transactions
            if transaction.source_usage_id in record_ids
            and str(transaction.customer_id) == str(customer_id)
            and enum_value(transaction.transaction_type) == "usage"
        ]
        return candidates[-1] if candidates else None

    async def get_transaction_by_reference(
        self, payment_reference: str, *, session: Session | None = None
    ) -> BalanceTransaction | None:
        return next(
            (
                transaction
                for transaction in self.transactions
                if transaction.payment_reference == payment_reference
            ),
            None,
        )

    async def get_products_for_external_ids(
        self, external_product_ids: Sequence[str], *, session: Session | None = None
    ) -> list[BillingProduct]:
        wanted = set(external_product_ids)
        return [
            product
            for product in self.products
            if product.is_active and product.external_product_id in wanted
        ]

    async def get_pending_records(self, limit: int = 50, *, session: Session) -> list[UsageRecord]:
        return [
            record
            for record in self.records
            if enum_value(record.billing_status) == BillingStatus.pending.value
        ][:limit]

    async def mark_record_processed(self, record_id: RecordId, *, session: Session) -> None:
        self._set_status(record_id, BillingStatus.processed)

    async def mark_record_failed(
        self, record_id: RecordId, error_message: str, *, session: Session
    ) -> None:
        record = self._record(record_id)
        record.billing_status = BillingStatus.failed
        record.billing_error_message = error_message

    async def mark_record_skipped(self, record_id: RecordId, *, session: Session) -> None:
        self._set_status(record_id, BillingStatus.skipped)

    def _record(self, record_id: RecordId) -> UsageRecord:
        for record in self.records:
            if record.id == record_id:
                return record
        raise KeyError(record_id)

    def _set_status(self, record_id: RecordId, status: BillingStatus) -> None:
        self._record(record_id).billing_status = status


class InMemoryUsageRepository:
    """Usage-record writer paired with ``InMemoryBillingRepository``."""

    def __init__(self, target: InMemoryBillingRepository | None = None) -> None:
        self.target = target or InMemoryBillingRepository()

    async def create(
        self, data: UsageRecordCreate, *, session: Session | None = None
    ) -> UsageRecord:
        record = UsageRecord(
            customer_id=data.customer_id,
            service=data.service,
            variant=data.variant,
            id=uuid4().hex,
            reference_id=data.reference_id,
            quantity=data.quantity,
            duration_seconds=data.duration_seconds,
            units=data.units,
            input_units=data.input_units,
            output_units=data.output_units,
            cached_units=data.cached_units,
            billing_status=data.billing_status,
            billing_error_message=data.billing_error_message,
            event_metadata=data.event_metadata,
        )
        self.target.records.append(record)
        return record

    async def get_by_customer(
        self, customer_id: CustomerId, skip: int = 0, limit: int = 100
    ) -> list[UsageRecord]:
        records = [
            record for record in self.target.records if str(record.customer_id) == str(customer_id)
        ]
        records.sort(key=lambda record: record.created_at or datetime.min, reverse=True)
        return records[skip : skip + limit]

    async def get_usage_summary(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[UsageSummary]:
        records = self._filtered(customer_id, from_date=from_date, to_date=to_date)
        grouped: dict[tuple[str, str], list[UsageRecord]] = {}
        for record in records:
            grouped.setdefault((enum_value(record.service), record.variant), []).append(record)
        return [
            UsageSummary(
                service=service,
                variant=variant,
                usage_count=len(group),
                total_quantity=_sum_float(group, "quantity"),
                total_duration_seconds=_sum_float(group, "duration_seconds"),
                total_units=_sum_int(group, "units"),
                total_input_units=_sum_int(group, "input_units"),
                total_output_units=_sum_int(group, "output_units"),
                total_cached_units=_sum_int(group, "cached_units"),
            )
            for (service, variant), group in grouped.items()
        ]

    async def get_usage_records(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        service: ServiceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UsageRecord], int]:
        records = self._filtered(
            customer_id,
            from_date=from_date,
            to_date=to_date,
            service=service,
        )
        records.sort(key=lambda record: record.created_at or datetime.min, reverse=True)
        return records[offset : offset + limit], len(records)

    def _filtered(
        self,
        customer_id: CustomerId,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        service: ServiceName | None = None,
    ) -> list[UsageRecord]:
        service_name = enum_value(service) if service is not None else None
        return [
            record
            for record in self.target.records
            if str(record.customer_id) == str(customer_id)
            and (
                from_date is None
                or (record.created_at is not None and record.created_at >= from_date)
            )
            and (
                to_date is None or (record.created_at is not None and record.created_at <= to_date)
            )
            and (service_name is None or enum_value(record.service) == service_name)
        ]


def _sum_int(records: Sequence[UsageRecord], field: str) -> int | None:
    values = [getattr(record, field) for record in records if getattr(record, field) is not None]
    return sum(values) if values else None


def _sum_float(records: Sequence[UsageRecord], field: str) -> float | None:
    values = [getattr(record, field) for record in records if getattr(record, field) is not None]
    return float(sum(values)) if values else None
