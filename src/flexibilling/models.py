"""Backend-neutral domain models used by the billing engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeAlias
from uuid import UUID

CustomerId: TypeAlias = str | int | UUID
RecordId: TypeAlias = str | int | UUID
AssetName: TypeAlias = str | StrEnum
ServiceName: TypeAlias = str | StrEnum
EventMetadata: TypeAlias = dict[str, Any]


class AssetType(StrEnum):
    """Convenient generic asset names; applications may use any string instead."""

    units = "units"
    prepaid_units = "prepaid_units"
    credits = "credits"


class TransactionType(StrEnum):
    """Kinds of balance movements recorded in the immutable ledger."""

    usage = "usage"
    top_up = "top_up"
    monthly_grant = "monthly_grant"
    expiration = "expiration"
    refund = "refund"


class MetricType(StrEnum):
    """How a rule derives a cost from a usage record."""

    fixed = "fixed"
    quantity = "quantity"
    duration = "duration"
    units = "units"


class BillingProductStrategy(StrEnum):
    """How a product changes an asset balance."""

    top_up = "top_up"
    monthly_quota = "monthly_quota"


class UsageService(StrEnum):
    """Convenient generic service names; applications may use any string instead."""

    api_request = "api_request"
    background_task = "background_task"
    data_export = "data_export"


class BillingStatus(StrEnum):
    """Lifecycle state of a usage record in the billing queue."""

    pending = "pending"
    processed = "processed"
    failed = "failed"
    skipped = "skipped"


@dataclass(slots=True)
class CustomerBalance:
    customer_id: CustomerId
    asset_type: AssetName
    amount: Decimal = Decimal("0")
    id: RecordId | None = None


@dataclass(slots=True)
class BalanceTransaction:
    customer_id: CustomerId
    asset_type: AssetName
    amount: Decimal
    balance_after: Decimal
    transaction_type: TransactionType | str
    id: RecordId | None = None
    source_usage_id: RecordId | None = None
    payment_reference: str | None = None
    description: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class BillingRule:
    service: ServiceName
    target_asset: AssetName
    metric_type: MetricType | str
    conversion_rate: Decimal = Decimal("1")
    priority: int = 100
    filter_condition: dict[str, Any] | None = None
    refund_service_type: ServiceName | None = None
    is_active: bool = True
    id: RecordId | None = None


@dataclass(slots=True)
class BillingProduct:
    external_product_id: str
    asset_type: AssetName
    amount: Decimal
    strategy: BillingProductStrategy | str = BillingProductStrategy.top_up
    description: str | None = None
    is_active: bool = True
    id: RecordId | None = None


@dataclass(slots=True)
class UsageRecord:
    customer_id: CustomerId
    service: ServiceName
    variant: str = "default"
    id: RecordId | None = None
    reference_id: RecordId | None = None
    quantity: Decimal | float | None = None
    duration_seconds: float | None = None
    units: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    cached_units: int | None = None
    billing_status: BillingStatus | str = BillingStatus.pending
    billing_error_message: str | None = None
    event_metadata: EventMetadata | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class BalanceTransactionCreate:
    customer_id: CustomerId
    asset_type: AssetName
    amount: Decimal
    balance_after: Decimal
    transaction_type: TransactionType | str
    source_usage_id: RecordId | None = None
    payment_reference: str | None = None
    description: str | None = None


@dataclass(slots=True)
class UsageRecordCreate:
    customer_id: CustomerId
    service: ServiceName
    variant: str = "default"
    reference_id: RecordId | None = None
    quantity: Decimal | float | None = None
    duration_seconds: float | None = None
    units: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    cached_units: int | None = None
    billing_status: BillingStatus | str = BillingStatus.pending
    billing_error_message: str | None = None
    event_metadata: EventMetadata | None = None


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """Aggregated usage values grouped by service and variant."""

    service: ServiceName
    variant: str
    usage_count: int
    total_quantity: float | None = None
    total_duration_seconds: float | None = None
    total_units: int | None = None
    total_input_units: int | None = None
    total_output_units: int | None = None
    total_cached_units: int | None = None


@dataclass(slots=True)
class BillingStats:
    """Generic period counters maintained by a cache adapter."""

    usage_count: int = 0
    quantity: float = 0.0
    spend: float = 0.0
    custom: dict[str, float] = field(default_factory=dict)


def enum_value(value: object) -> str:
    """Return the string value of an enum or a normal string-like value."""

    return str(getattr(value, "value", value))


def customer_key(customer_id: CustomerId) -> str:
    """Normalize a backend customer identifier for cache keys and logs."""

    return str(customer_id)


def copy_metadata(metadata: EventMetadata | None) -> EventMetadata:
    """Copy metadata without allowing a session to mutate its caller's dict."""

    return dict(metadata) if metadata else {}
