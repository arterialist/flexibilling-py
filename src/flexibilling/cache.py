"""Cache contracts and an in-memory materialized-view implementation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .models import AssetName, BillingStats, CustomerId, customer_key, enum_value


class InMemoryBillingCache:
    """Small async cache useful for tests, local development, and examples."""

    def __init__(self, *, feed_max_length: int = 50) -> None:
        self._balances: dict[str, dict[str, str]] = {}
        self._stats: dict[tuple[str, str], dict[str, str]] = {}
        self._feed: dict[str, list[dict[str, Any]]] = {}
        self._feed_max_length = feed_max_length
        self._lock = asyncio.Lock()

    async def set_balances(
        self, customer_id: CustomerId, balances: dict[AssetName, Decimal]
    ) -> None:
        async with self._lock:
            mapping = {enum_value(asset): str(amount) for asset, amount in balances.items()}
            mapping["can_transact"] = (
                "1" if any(amount > 0 for amount in balances.values()) else "0"
            )
            self._balances[customer_key(customer_id)] = mapping

    async def update_single_balance(
        self, customer_id: CustomerId, asset_type: AssetName, new_amount: Decimal
    ) -> None:
        async with self._lock:
            key = customer_key(customer_id)
            balances = self._balances.setdefault(key, {})
            balances[enum_value(asset_type)] = str(new_amount)
            balances["can_transact"] = (
                "1"
                if any(
                    field != "can_transact" and _to_decimal(value) > 0
                    for field, value in balances.items()
                )
                else "0"
            )

    async def get_balances(self, customer_id: CustomerId) -> dict[str, str]:
        async with self._lock:
            return dict(self._balances.get(customer_key(customer_id), {}))

    async def can_transact(self, customer_id: CustomerId) -> bool:
        async with self._lock:
            return self._balances.get(customer_key(customer_id), {}).get("can_transact") == "1"

    async def get_asset_amount(
        self, customer_id: CustomerId, asset_type: AssetName
    ) -> Decimal | None:
        async with self._lock:
            value = self._balances.get(customer_key(customer_id), {}).get(enum_value(asset_type))
            return _to_decimal(value) if value is not None else None

    async def delete_balances(self, customer_id: CustomerId) -> None:
        async with self._lock:
            self._balances.pop(customer_key(customer_id), None)

    async def increment_stats(
        self, customer_id: CustomerId, month: str, stats: BillingStats
    ) -> None:
        async with self._lock:
            key = (customer_key(customer_id), month)
            current = self._stats.setdefault(key, {})
            _increment_int(current, "total_usage_count", stats.usage_count)
            _increment_float(current, "total_quantity", stats.quantity)
            _increment_float(current, "total_spend", stats.spend)
            for name, amount in stats.custom.items():
                _increment_float(current, f"total_custom:{name}", amount)

    async def get_stats(self, customer_id: CustomerId, month: str) -> dict[str, str]:
        async with self._lock:
            return dict(self._stats.get((customer_key(customer_id), month), {}))

    async def push_feed_event(
        self,
        customer_id: CustomerId,
        *,
        action: str,
        cost: str,
        result: str,
        time: object | None = None,
    ) -> None:
        event_time = time if isinstance(time, datetime) else datetime.now(UTC)
        event = {
            "time": event_time.isoformat().replace("+00:00", "Z"),
            "action": action,
            "cost": cost,
            "result": result,
        }
        async with self._lock:
            events = self._feed.setdefault(customer_key(customer_id), [])
            events.insert(0, event)
            del events[self._feed_max_length :]

    async def get_feed(self, customer_id: CustomerId, limit: int = 20) -> list[dict[str, Any]]:
        async with self._lock:
            return [dict(event) for event in self._feed.get(customer_key(customer_id), [])[:limit]]

    async def delete_customer_cache(self, customer_id: CustomerId) -> None:
        async with self._lock:
            key = customer_key(customer_id)
            self._balances.pop(key, None)
            self._feed.pop(key, None)
            for stat_key in [stat_key for stat_key in self._stats if stat_key[0] == key]:
                self._stats.pop(stat_key, None)


class NullBillingCache(InMemoryBillingCache):
    """A cache that preserves the cache interface without retaining state."""

    async def set_balances(
        self, customer_id: CustomerId, balances: dict[AssetName, Decimal]
    ) -> None:
        return None

    async def update_single_balance(
        self, customer_id: CustomerId, asset_type: AssetName, new_amount: Decimal
    ) -> None:
        return None

    async def get_balances(self, customer_id: CustomerId) -> dict[str, str]:
        return {}

    async def can_transact(self, customer_id: CustomerId) -> bool:
        return False

    async def get_asset_amount(
        self, customer_id: CustomerId, asset_type: AssetName
    ) -> Decimal | None:
        return None

    async def increment_stats(
        self, customer_id: CustomerId, month: str, stats: BillingStats
    ) -> None:
        return None

    async def get_stats(self, customer_id: CustomerId, month: str) -> dict[str, str]:
        return {}

    async def push_feed_event(
        self,
        customer_id: CustomerId,
        *,
        action: str,
        cost: str,
        result: str,
        time: object | None = None,
    ) -> None:
        return None


def _to_decimal(value: str | None) -> Decimal:
    try:
        return Decimal(value or "0")
    except (ArithmeticError, ValueError):
        return Decimal("0")


def _increment_int(mapping: dict[str, str], key: str, amount: int) -> None:
    if amount:
        mapping[key] = str(int(_to_decimal(mapping.get(key))) + amount)


def _increment_float(mapping: dict[str, str], key: str, amount: float) -> None:
    if amount:
        mapping[key] = str(float(_to_decimal(mapping.get(key))) + amount)
