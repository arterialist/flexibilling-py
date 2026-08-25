# Backend integration

FlexiBilling uses structural protocols. A host backend can keep its existing
models and implement the methods in `flexibilling.ports` without adopting the
SQLAlchemy schema.

## Protocols

The main ports are:

- `BillingRepository` handles rules, balances, products, ledger transactions, and queue status.
- `UsageRepository` handles session-created records and usage queries.
- `BillingCache` handles balance snapshots, period statistics, and activity events.
- `TransactionFactory` creates an async context for charges and refunds that do not receive a caller session.

Repository methods receive a `Session` value typed as `Any`. The host can pass an
SQLAlchemy session, a database transaction, or a unit-of-work object without
adding that type to the core package.

## Existing database models

For an existing schema, implement the protocols against your own models:

```python
from collections.abc import Sequence
from decimal import Decimal

from flexibilling import BillingRule, CustomerBalance
from flexibilling.models import AssetName, CustomerId, ServiceName


class BillingRepository:
    async def get_active_rules(
        self, service: ServiceName, *, session=None
    ) -> Sequence[BillingRule]:
        ...

    async def get_customer_balances(
        self, customer_id: CustomerId, *, session=None
    ) -> Sequence[CustomerBalance]:
        ...

    async def decrement_balance(
        self,
        customer_id: CustomerId,
        asset_type: AssetName,
        deduction: Decimal,
        *,
        session,
    ) -> Decimal:
        ...
```

Implement all methods required by `BillingRepository` and `UsageRepository`,
then pass the implementation to `BillingService`.

## In-memory adapter

`InMemoryBillingRepository`, `InMemoryUsageRepository`, and
`InMemoryBillingCache` are for tests, examples, and local experiments. They do
not persist data or lock across processes.

## Redis cache

Install the optional dependency:

```bash
uv add "flexibilling[redis]"
```

```python
from redis.asyncio import Redis

from flexibilling.adapters.redis import RedisBillingCache

redis = Redis.from_url("redis://localhost:6379/0", decode_responses=False)
cache = RedisBillingCache(redis, key_prefix="myapp:billing")
```

The adapter stores balances, period statistics, and activity events below the
configured prefix. Custom period counters use `total_custom:<name>`. The
service stores per-asset totals as `total_custom:asset:<asset-name>`.

## SQLAlchemy adapter

Install the optional dependency:

```bash
uv add "flexibilling[sqlalchemy]"
# Add the async driver for your database, for example:
uv add aiosqlite
```

Create an async session factory and use the included repository:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flexibilling import BillingService, InMemoryBillingCache
from flexibilling.adapters.sqlalchemy import (
    Base,
    SQLAlchemyBillingRepository,
    SQLAlchemyUsageRepository,
)

engine = create_async_engine("sqlite+aiosqlite:///./billing.db")
session_factory = async_sessionmaker(engine, expire_on_commit=False)

async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.create_all)

repository = SQLAlchemyBillingRepository(session_factory)
usage_repository = SQLAlchemyUsageRepository(session_factory)
service = BillingService(repository, InMemoryBillingCache())
```

The schema includes balances, transactions, rules, products, and
`usage_records`. It does not run migrations. Manage schema changes with the
host application's migration tool.
