"""Rule-based cost calculation."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ..models import BillingRule, MetricType, UsageRecord, enum_value


class RatingEngine:
    """Stateless calculator for fixed, duration, and token rules."""

    @staticmethod
    def calculate_cost(rule: BillingRule | Any, record: UsageRecord | Any) -> Decimal:
        metric_type = enum_value(rule.metric_type)
        rate = Decimal(str(rule.conversion_rate))

        if metric_type == MetricType.fixed.value:
            return rate
        if metric_type == MetricType.quantity.value:
            return Decimal(str(_extract_quantity(record))) * rate
        if metric_type == MetricType.duration.value:
            return Decimal(str(_extract_duration(record))) * rate
        if metric_type == MetricType.units.value:
            return Decimal(str(_extract_units(record))) * rate
        raise ValueError(f"Unknown metric type: {rule.metric_type}")

    @staticmethod
    def matches_filter(rule: BillingRule | Any, metadata: Mapping[str, Any] | None) -> bool:
        condition = getattr(rule, "filter_condition", None)
        if not condition:
            return True
        if not metadata:
            return False
        return all(
            _resolve_dotted_key(metadata, key) == expected for key, expected in condition.items()
        )


def _extract_duration(record: UsageRecord | Any) -> float:
    metadata = getattr(record, "event_metadata", None)
    if metadata:
        duration = metadata.get("duration_seconds")
        if duration is not None:
            return float(duration)
    record_duration = getattr(record, "duration_seconds", None)
    if record_duration is not None:
        return float(record_duration)
    return 0.0


def _extract_quantity(record: UsageRecord | Any) -> float:
    return float(getattr(record, "quantity", None) or 0)


def _extract_units(record: UsageRecord | Any) -> int:
    units = getattr(record, "units", None)
    if units is not None:
        return int(units)
    return (getattr(record, "input_units", None) or 0) + (
        getattr(record, "output_units", None) or 0
    )


def _resolve_dotted_key(data: Mapping[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current
