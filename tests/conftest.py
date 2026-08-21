from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from flexibilling import AssetType, BillingRule, MetricType, UsageRecord, UsageService

CUSTOMER_ID = UUID("00000000-0000-0000-0000-000000000001")


def make_rule(
    *,
    service: UsageService | str = UsageService.api_request,
    priority: int = 100,
    target_asset: AssetType | str = AssetType.units,
    metric_type: MetricType | str = MetricType.units,
    conversion_rate: Decimal = Decimal("1"),
    filter_condition: dict | None = None,
    refund_service_type: str | None = None,
    rule_id: int = 1,
) -> BillingRule:
    return BillingRule(
        id=rule_id,
        service=service,
        priority=priority,
        target_asset=target_asset,
        metric_type=metric_type,
        conversion_rate=conversion_rate,
        filter_condition=filter_condition,
        refund_service_type=refund_service_type,
    )


def make_record(
    *,
    record_id: int = 1,
    customer_id: UUID = CUSTOMER_ID,
    service: UsageService | str = UsageService.api_request,
    quantity: float | None = None,
    duration_seconds: float | None = None,
    units: int | None = None,
    input_units: int | None = None,
    output_units: int | None = None,
    cached_units: int | None = None,
    event_metadata: dict | None = None,
    reference_id: int | None = None,
) -> UsageRecord:
    return UsageRecord(
        id=record_id,
        customer_id=customer_id,
        service=service,
        quantity=quantity,
        duration_seconds=duration_seconds,
        units=units,
        input_units=input_units,
        output_units=output_units,
        cached_units=cached_units,
        event_metadata=event_metadata,
        reference_id=reference_id,
    )


def make_balances(**values: float) -> dict[AssetType, Decimal]:
    return {AssetType(key): Decimal(str(value)) for key, value in values.items()}
