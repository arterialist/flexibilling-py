# FlexiBilling for Python

[![CI](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml/badge.svg)](https://github.com/arterialist/flexibilling/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Python](https://img.shields.io/pypi/pyversions/flexibilling.svg)](https://pypi.org/project/flexibilling/)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://arterialist.github.io/flexibilling/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

FlexiBilling is a provider-agnostic billing engine for Python backends. It
tracks named balances, rates usage, applies priority rules, writes ledger
entries, and processes pending usage records.

The core package does not require a database, web framework, cache, or payment
provider. Implement the protocols in `flexibilling.ports` against an existing
backend, or use the included in-memory, Redis, and SQLAlchemy adapters.

## Install

```bash
uv add flexibilling
```

Optional integrations:

```bash
uv add "flexibilling[fastapi]"
uv add "flexibilling[redis]"
uv add "flexibilling[sqlalchemy]"
uv add "flexibilling[all]"
```

## Quickstart

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
repository = InMemoryBillingRepository(rules=[
    BillingRule(
        service=UsageService.api_request,
        target_asset=AssetType.units,
        metric_type=MetricType.units,
        conversion_rate=Decimal("1"),
        priority=10,
    ),
])
cache = InMemoryBillingCache()
service = BillingService(repository, cache)

await repository.upsert_balance(
    customer_id, AssetType.units, Decimal("100"), session=object()
)
record = UsageRecord(
    customer_id=customer_id,
    service=UsageService.api_request,
    reference_id="request-123",
    units=12,
)
repository.records.append(record)
await service.process_record(record, session=object())
```

`AssetType` and `UsageService` are conveniences for examples. Applications can
use their own asset and service strings.

## Usage sessions

Use a session when an operation discovers usage while it runs:

```python
from flexibilling import BillingDecorators, UsageService

billing = BillingDecorators(service=service, usage_repository=usage_repository)

async with billing.session(
    customer_id=customer_id,
    service=UsageService.api_request,
    reference_id="request-123",
) as usage:
    usage.report(units=12, duration_seconds=0.45)
```

`duration_seconds` is a first-class field on the context and usage record. The
session also copies it to `event_metadata["duration_seconds"]` when no value is
already present there, so duration rules can use metadata filters and rating.
Set `write_on_exception=False` when failed operations should not create a
record.

## What is included

- `BillingService` funds accounts, rates usage, charges, refunds, and updates cache views.
- `flexibilling.ports` defines repository, usage, cache, and transaction protocols.
- `flexibilling.engine` contains rating, waterfall, and balance gatekeeper logic.
- `BillingDecorators` provides `requires`, `consumes`, and usage-session helpers.
- `BillingWorker` processes pending records with retry-safe state transitions.
- The adapters package includes in-memory, Redis, and SQLAlchemy implementations.
- `flexibilling.integrations.fastapi` provides optional middleware and HTTP 402 helpers.

## Documentation

Read the [Python documentation](https://arterialist.github.io/flexibilling/)
for the quickstart, concepts, backend ports, integrations, operations, and
release process.

## Development

```bash
uv sync --group testing --group lint --group dev
uv run pytest
uv run ruff check src tests examples
uv run ruff format src tests examples --check
uv run pyright --project pyproject.toml src/flexibilling
uv build
uv run mkdocs build --strict
```

The package supports Python 3.11 through 3.14. Releases publish to PyPI with
GitHub Actions trusted publishing.

## License

Apache-2.0. See [LICENSE](LICENSE).
