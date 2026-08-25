# FlexiBilling

[![CI](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml/badge.svg)](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Python](https://img.shields.io/pypi/pyversions/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Docs](https://img.shields.io/badge/docs-flexibilling-blue.svg)](https://arterialist.github.io/flexibilling/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

Billing and usage metering for Python backends. FlexiBilling tracks named
balances, rates usage, applies priority rules, and records ledger entries.

The core package does not depend on a database, web framework, cache, or payment
provider. Implement the async protocols in `flexibilling.ports` against an
existing backend, or use the optional adapters.

## Install

```bash
uv add flexibilling
```

Optional integrations:

```bash
uv add "flexibilling[redis]"
uv add "flexibilling[sqlalchemy]"
uv add "flexibilling[fastapi]"
uv add "flexibilling[all]"
```

Read the [full documentation](https://arterialist.github.io/flexibilling/)
for backend adapters, framework integrations, operations, and releases.

## Quickstart

This example charges one unit for each metered unit. When the first balance is
empty, the second rule uses prepaid units.

```python
from decimal import Decimal
from uuid import uuid4

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

customer_id = uuid4()
repo = InMemoryBillingRepository(
    rules=[
        BillingRule(
            service=UsageService.api_request,
            target_asset=AssetType.units,
            metric_type=MetricType.units,
            conversion_rate=Decimal("1"),
        ),
        BillingRule(
            service=UsageService.api_request,
            target_asset=AssetType.prepaid_units,
            metric_type=MetricType.units,
            conversion_rate=Decimal("1"),
            priority=200,
        ),
    ]
)
cache = InMemoryBillingCache()
service = BillingService(repo, cache)

await repo.upsert_balance(
    customer_id, AssetType.units, Decimal("100"), session=object()
)
record = UsageRecord(
    id=1,
    customer_id=customer_id,
    service=UsageService.api_request,
    reference_id="request-123",
    units=12,
)
repo.records.append(record)
await service.process_record(record, session=object())
```

Asset and service names are open strings. `AssetType` and `UsageService` only
provide a few neutral conveniences for examples; applications can define their
own values without subclassing or configuring the package.

## Main components

The package includes these parts:

- `flexibilling.engine` rates usage, applies priority rules, and checks cached
  balances.
- `flexibilling.service.BillingService` funds accounts, processes usage, writes
  ledger entries, handles charges and refunds, and updates the cache.
- `flexibilling.decorators` provides `requires`, `consumes`, and
  `billing.session(...)` helpers.
- `flexibilling.ports` defines the repository, usage, cache, and transaction
  protocols.
- `flexibilling.worker.BillingWorker` processes pending usage records.
- `flexibilling.adapters.redis` stores balances, period totals, and activity
  events in Redis.
- `flexibilling.adapters.sqlalchemy` provides an async SQLAlchemy 2 repository
  and schema that a host can adapt.
- `flexibilling.integrations.fastapi` provides optional middleware and HTTP 402
  helpers.

Payment identifiers are opaque strings. `BillingService.fund_customer` maps them
to asset grants and ignores a payment reference that it has already processed.
Monthly-quota products replace a balance. Top-ups add to it.

For an existing database, implement `BillingRepository` and `UsageRepository`
against the current models. The SQLAlchemy adapter shows one possible schema;
it is not required.

## Documentation

- [Quickstart](https://arterialist.github.io/flexibilling/quickstart/) covers a first usage record.
- [Concepts](https://arterialist.github.io/flexibilling/concepts/) explains balances, rules, rating, waterfalls, and ledger transactions.
- [Backend integration](https://arterialist.github.io/flexibilling/backends/) shows how to implement the protocols or use Redis and SQLAlchemy.
- [Framework integrations](https://arterialist.github.io/flexibilling/integrations/) covers FastAPI, decorators, workers, and metrics.
- [Operations](https://arterialist.github.io/flexibilling/operations/) covers transactions, retries, cache behavior, and production checks.
- [Development and releases](https://arterialist.github.io/flexibilling/development/) covers local setup, CI, docs, and PyPI publishing.

## Usage sessions

```python
from flexibilling import BillingDecorators, UsageService

billing = BillingDecorators(service=service, usage_repository=usage_repo)

async with billing.session(
    customer_id=customer_id,
    service=UsageService.api_request,
    variant="standard",
    reference_id="request-123",
) as usage:
    usage.report(units=12)
```

The session writes one pending usage record when it reports usage. It stores
reported duration in `event_metadata["duration_seconds"]`, so a rule can bill
elapsed time without depending on the host framework. Set
`write_on_exception=False` when failed operations should not create a record.

## Development

```bash
uv sync --group testing --group lint --group dev
uv run pre-commit install
uv run pytest
uv run ruff check src tests examples
uv run ruff format src tests examples --check
uv run pyright --project pyproject.toml src/flexibilling
uv build
uv run mkdocs build --strict
```

CI runs lint and type checks, tests Python 3.11 through 3.14, and builds the
distribution. A GitHub release publishes to PyPI through trusted publishing.

## License

Apache-2.0. See [LICENSE](LICENSE).
