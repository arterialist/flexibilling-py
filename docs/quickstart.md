# Quickstart

This walkthrough uses the in-memory adapters. The same service calls work with a
custom repository, Redis cache, or SQLAlchemy repository.

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install flexibilling
```

For a local checkout, use the development setup in
[Development and releases](development.md).

## 2. Define rules and balances

The example meters generic units. The primary balance is consumed first, then a
prepaid balance is used as a fallback.

```python
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

customer_id = "customer-001"
repository = InMemoryBillingRepository(
    rules=[
        BillingRule(
            service=UsageService.api_request,
            target_asset=AssetType.units,
            metric_type=MetricType.units,
            conversion_rate=Decimal("1"),
            priority=10,
        ),
        BillingRule(
            service=UsageService.api_request,
            target_asset=AssetType.prepaid_units,
            metric_type=MetricType.units,
            conversion_rate=Decimal("1"),
            priority=20,
        ),
    ]
)
cache = InMemoryBillingCache()
service = BillingService(repository, cache)

await repository.upsert_balance(
    customer_id, AssetType.units, Decimal("100"), session=object()
)
await repository.upsert_balance(
    customer_id, AssetType.prepaid_units, Decimal("50"), session=object()
)
```

`AssetType` and `UsageService` are convenience enums for examples. Real
applications can pass their own strings, such as `"storage_bytes"` or
`"report_generation"`.

## 3. Process a usage record

```python
record = UsageRecord(
    id=1,
    customer_id=customer_id,
    service=UsageService.api_request,
    variant="standard",
    reference_id="request-1001",
    units=12,
)
repository.records.append(record)

await service.process_record(record, session=object())

assert record.billing_status == "processed"
assert await cache.get_asset_amount(customer_id, AssetType.units) == Decimal("88")
```

The service selects active rules in priority order, calculates a cost, locks and
deducts the selected balance through the repository, writes a ledger transaction,
updates cache views, and marks the record processed.

## 4. Track a session

Use `BillingDecorators.session` when usage is discovered while an operation is
running:

```python
from flexibilling import BillingDecorators
from flexibilling.adapters.memory import InMemoryUsageRepository

usage_repository = InMemoryUsageRepository(repository)
billing = BillingDecorators(service, usage_repository)

async with billing.session(
    customer_id,
    UsageService.api_request,
    variant="standard",
    reference_id="request-1002",
) as usage:
    usage.report(units=24, duration_seconds=0.45)
```

On successful exit, the session writes one pending `UsageRecord`. Set
`write_on_exception=False` when an exception should not create a record.

## 5. Inspect balances and usage

```python
balances = await cache.get_balances(customer_id)
period_stats = await cache.get_stats(customer_id, "2026-08")
print(balances)
print(period_stats)
```

The generic snapshot helper can report selected assets:

```python
from flexibilling import get_usage_snapshot

snapshot = await get_usage_snapshot(
    customer_id,
    [AssetType.units, AssetType.prepaid_units],
    cache=cache,
)
print(snapshot.to_dict())
```
