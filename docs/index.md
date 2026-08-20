# FlexiBilling

FlexiBilling is a provider-agnostic asynchronous billing engine for Python
backends. It provides balance management, usage rating, priority waterfalls,
ledger transactions, idempotent product grants, cache views, and a background
queue worker.

The core package has no required framework, ORM, cache, or payment dependency.
Storage is connected through small protocols, so an existing backend can adopt
the engine without replacing its data models.

## Install

```bash
uv add flexibilling
```

Install only the integrations you need:

```bash
uv add "flexibilling[fastapi]"
uv add "flexibilling[redis]"
uv add "flexibilling[sqlalchemy]"
uv add "flexibilling[metrics]"
```

Or install every optional integration:

```bash
uv add "flexibilling[all]"
```

## Documentation map

- **[Quickstart](quickstart.md)** — create rules, fund a customer, and process a first usage record.
- **[Concepts](concepts.md)** — understand assets, metrics, rules, waterfalls, and ledger entries.
- **[Backend integration](backends.md)** — implement protocols or use the reference adapters.
- **[Framework integrations](integrations.md)** — connect FastAPI, decorators, workers, and metrics.
- **[Operations](operations.md)** — configure transactions, retries, cache behavior, and production checks.
- **[Development and releases](development.md)** — set up a checkout, run CI locally, build docs, and publish.

## Design goals

1. Keep billing decisions independent from persistence.
2. Accept application-defined service and asset names.
3. Make balance deductions and ledger writes happen in the caller's transaction.
4. Keep cache and observability failures from changing the billing decision.
5. Make the reference adapters useful for tests without requiring them in production.
