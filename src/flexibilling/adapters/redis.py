"""Redis materialized-view adapter.

Install with ``uv add "flexibilling[redis]"``. The adapter only depends on
the cache protocol, so a backend can replace it with DynamoDB, Memcached, or a
local cache without changing the billing service.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..models import AssetName, BillingStats, CustomerId, customer_key, enum_value


class RedisBillingCache:
    """Redis implementation of the asset, period, and activity-feed views."""

    def __init__(
        self, redis: Any, *, key_prefix: str = "billing", feed_max_length: int = 50
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix.rstrip(":")
        self._feed_max_length = feed_max_length

    async def set_balances(
        self, customer_id: CustomerId, balances: dict[AssetName, Decimal]
    ) -> None:
        mapping = {enum_value(asset): str(amount) for asset, amount in balances.items()}
        mapping["can_transact"] = "1" if any(amount > 0 for amount in balances.values()) else "0"
        await self._redis.hset(self._asset_key(customer_id), mapping=mapping)

    async def update_single_balance(
        self, customer_id: CustomerId, asset_type: AssetName, new_amount: Decimal
    ) -> None:
        key = self._asset_key(customer_id)
        current = await self._redis.hgetall(key)
        decoded = {_text(field): _text(value) for field, value in current.items()}
        decoded[enum_value(asset_type)] = str(new_amount)
        decoded["can_transact"] = (
            "1"
            if any(
                field != "can_transact" and _to_decimal(value) > 0
                for field, value in decoded.items()
            )
            else "0"
        )
        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=decoded)
        await pipe.execute()

    async def get_balances(self, customer_id: CustomerId) -> dict[str, str]:
        raw = await self._redis.hgetall(self._asset_key(customer_id))
        return {_text(key): _text(value) for key, value in raw.items()}

    async def can_transact(self, customer_id: CustomerId) -> bool:
        return _text(await self._redis.hget(self._asset_key(customer_id), "can_transact")) == "1"

    async def get_asset_amount(
        self, customer_id: CustomerId, asset_type: AssetName
    ) -> Decimal | None:
        value = await self._redis.hget(self._asset_key(customer_id), enum_value(asset_type))
        return _to_decimal(_text(value)) if value is not None else None

    async def delete_balances(self, customer_id: CustomerId) -> None:
        await self._redis.delete(self._asset_key(customer_id))

    async def increment_stats(
        self, customer_id: CustomerId, month: str, stats: BillingStats
    ) -> None:
        key = self._stats_key(customer_id, month)
        pipe = self._redis.pipeline()
        if stats.usage_count:
            pipe.hincrby(key, "total_usage_count", stats.usage_count)
        if stats.quantity:
            pipe.hincrbyfloat(key, "total_quantity", stats.quantity)
        if stats.spend:
            pipe.hincrbyfloat(key, "total_spend", stats.spend)
        for name, amount in stats.custom.items():
            if amount:
                pipe.hincrbyfloat(key, f"total_custom:{name}", amount)
        await pipe.execute()

    async def get_stats(self, customer_id: CustomerId, month: str) -> dict[str, str]:
        raw = await self._redis.hgetall(self._stats_key(customer_id, month))
        return {_text(key): _text(value) for key, value in raw.items()}

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
        pipe = self._redis.pipeline()
        key = self._feed_key(customer_id)
        pipe.lpush(key, json.dumps(event))
        pipe.ltrim(key, 0, self._feed_max_length - 1)
        await pipe.execute()

    async def get_feed(self, customer_id: CustomerId, limit: int = 20) -> list[dict[str, Any]]:
        values = await self._redis.lrange(self._feed_key(customer_id), 0, limit - 1)
        return [json.loads(_text(value)) for value in values]

    async def delete_customer_cache(self, customer_id: CustomerId) -> None:
        key = customer_key(customer_id)
        stats_keys = []
        async for raw_key in self._redis.scan_iter(
            match=f"{self._prefix}:stats:{key}:*", count=100
        ):
            stats_keys.append(raw_key)
        if stats_keys:
            await self._redis.delete(*stats_keys)
        await self.delete_balances(customer_id)
        await self._redis.delete(self._feed_key(customer_id))

    def _asset_key(self, customer_id: CustomerId) -> str:
        return f"{self._prefix}:assets:{customer_key(customer_id)}"

    def _stats_key(self, customer_id: CustomerId, month: str) -> str:
        return f"{self._prefix}:stats:{customer_key(customer_id)}:{month}"

    def _feed_key(self, customer_id: CustomerId) -> str:
        return f"{self._prefix}:feed:{customer_key(customer_id)}"


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value) if value is not None else ""


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (ArithmeticError, ValueError):
        return Decimal("0")
