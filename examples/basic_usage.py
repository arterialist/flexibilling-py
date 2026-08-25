"""Run a complete in-memory billing example.

Run with:

    uv run python examples/basic_usage.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from flexibilling import (
    AssetType,
    BillingRule,
    BillingService,
    InMemoryBillingCache,
    MetricType,
    UsageRecord,
    UsageService,
)
from flexibilling.adapters.memory import InMemoryBillingRepository


async def main() -> None:
    customer_id = "customer-001"
    repository = InMemoryBillingRepository(
        rules=[
            BillingRule(
                service=UsageService.api_request,
                target_asset=AssetType.units,
                metric_type=MetricType.units,
                conversion_rate=Decimal("1"),
            )
        ]
    )
    cache = InMemoryBillingCache()
    service = BillingService(repository, cache)

    await repository.upsert_balance(customer_id, AssetType.units, Decimal("100"), session=object())
    record = UsageRecord(
        id=1,
        customer_id=customer_id,
        service=UsageService.api_request,
        variant="standard",
        reference_id="request-1",
        units=12,
    )
    repository.records.append(record)

    await service.process_record(record, session=object())
    print(await cache.get_balances(customer_id))
    print(await cache.get_feed(customer_id))


if __name__ == "__main__":
    asyncio.run(main())
