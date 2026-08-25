"""Generic current-period usage snapshots derived from cache views."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .models import AssetName, CustomerId, enum_value
from .ports import BillingCache


@dataclass(frozen=True, slots=True)
class UsageMetric:
    used: float
    total: float

    def to_dict(self) -> dict[str, float]:
        return {"used": self.used, "total": self.total}


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    period: str
    metrics: dict[str, UsageMetric]

    def to_dict(self) -> dict[str, dict[str, float]]:
        return {asset: metric.to_dict() for asset, metric in self.metrics.items()}


async def get_usage_snapshot(
    customer_id: CustomerId,
    asset_types: Sequence[AssetName],
    *,
    cache: BillingCache,
    now: datetime | None = None,
) -> UsageSnapshot:
    """Return used and total values for the selected assets in the current period.

    Cache adapters record per-asset usage under ``total_custom:asset:<name>``.
    Applications can add the same custom counter when they write usage directly.
    """

    current = now or datetime.now(UTC)
    period = (
        current.astimezone(UTC).strftime("%Y-%m") if current.tzinfo else current.strftime("%Y-%m")
    )
    balances = await cache.get_balances(customer_id)
    stats = await cache.get_stats(customer_id, period)
    metrics: dict[str, UsageMetric] = {}
    for asset_type in asset_types:
        asset = enum_value(asset_type)
        used = _decimal(stats.get(f"total_custom:asset:{asset}"))
        remaining = max(_decimal(balances.get(asset)), Decimal("0"))
        metrics[asset] = UsageMetric(
            used=float(used),
            total=float(used + remaining),
        )
    return UsageSnapshot(period=period, metrics=metrics)


def _decimal(value: str | None) -> Decimal:
    try:
        return Decimal(value or "0")
    except (ArithmeticError, ValueError):
        return Decimal("0")
