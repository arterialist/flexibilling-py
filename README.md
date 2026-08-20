# FlexiBilling

[![CI](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml/badge.svg)](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Python](https://img.shields.io/pypi/pyversions/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Docs](https://img.shields.io/badge/docs-flexibilling-blue.svg)](https://arterialist.github.io/flexibilling/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

Provider-agnostic usage metering, multi-asset balances, and configurable billing
waterfalls for Python backends.

FlexiBilling keeps the billing engine independent from storage, web frameworks,
caches, and payment providers. Implement the small async protocols in
`flexibilling.ports`, use the included adapters, or compose both approaches.

## Install

```bash
pip install flexibilling
```

Optional integrations:

```bash
pip install "flexibilling[redis]"
pip install "flexibilling[sqlalchemy]"
pip install "flexibilling[fastapi]"
pip install "flexibilling[all]"
```

The complete guide is available at the
[FlexiBilling documentation site](https://arterialist.github.io/flexibilling/).

## Quickstart

The in-memory adapters are useful for local development and tests. This example
charges one unit for every metered unit and falls back to prepaid units when the
primary balance is exhausted.

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

## Integration boundary

The reusable pieces are:

- `flexibilling.engine` — rating, priority waterfall, and cache gatekeeper.
- `flexibilling.service.BillingService` — funding, charging, refunds, usage
  processing, ledger writes, and cache synchronization.
- `flexibilling.decorators` — configurable `requires`, `consumes`, and
  `billing.session(...)` helpers.
- `flexibilling.ports` — repository, usage-writer, cache, and transaction
  protocols for any backend.
- `flexibilling.worker.BillingWorker` — generic pending-record queue drain.
- `flexibilling.adapters.redis` — Redis materialized views for balances, period
  aggregates, and activity feed.
- `flexibilling.adapters.sqlalchemy` — neutral SQLAlchemy 2 async reference
  schema and repository implementation.
- `flexibilling.integrations.fastapi` — optional middleware and 402 helpers.

Payment-provider identifiers remain opaque strings. `BillingService.fund_customer`
maps them to one or more internal asset grants and is idempotent on the supplied
payment reference. Monthly-quota products reset a balance; top-ups add to it.

For an existing database, implementing `BillingRepository` and
`UsageRepository` against the backend's current models is usually preferable to
changing its schema. The SQLAlchemy adapter is a portable reference schema, not
a requirement.

## Documentation

- [Quickstart](https://arterialist.github.io/flexibilling/quickstart/) — install the package and process a first usage record.
- [Concepts](https://arterialist.github.io/flexibilling/concepts/) — balances, rules, rating, waterfalls, and ledger transactions.
- [Backend integration](https://arterialist.github.io/flexibilling/backends/) — implement the protocols or use Redis and SQLAlchemy.
- [Framework integrations](https://arterialist.github.io/flexibilling/integrations/) — FastAPI middleware, decorators, workers, and metrics.
- [Operations](https://arterialist.github.io/flexibilling/operations/) — cache behavior, transactions, retries, and production checks.
- [Contributing and releasing](https://arterialist.github.io/flexibilling/development/) — local setup, CI, documentation, and PyPI publishing.

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

The session writes one pending usage record when a non-empty session exits.
Reported duration is copied to `event_metadata["duration_seconds"]`, so rules
can bill elapsed time independently of the host framework. Set
`write_on_exception=False` when failed operations must not create a usage record.

## Development

```bash
uv sync --group testing --group lint --group dev
uv run pre-commit install
uv run pytest
uv run ruff check src tests examples
uv run ruff format src tests examples --check
uv run pyright src/flexibilling
python -m build
uv run mkdocs build --strict
```

CI runs lint/type checks, tests on Python 3.11–3.13, and a distribution build.
Publishing is configured for PyPI trusted publishing from a GitHub release.

## License

Apache-2.0. See [LICENSE](LICENSE).
