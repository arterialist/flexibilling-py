# FlexiBilling

FlexiBilling is an asynchronous billing engine for Python backends. It manages
balances, rates usage, applies priority rules, records ledger transactions,
grants products idempotently, updates cache views, and processes a background
queue.

Storage, ORM, cache, and payment integrations live outside the core package.
Connect the host's existing models through the protocols in
`flexibilling.ports`.

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

## Guides

- [Quickstart](quickstart.md) creates rules, funds a customer, and processes a usage record.
- [Concepts](concepts.md) explains assets, metrics, rules, waterfalls, and ledger entries.
- [Backend integration](backends.md) shows how to implement the protocols or use the adapters.
- [Framework integrations](integrations.md) covers FastAPI, decorators, workers, and metrics.
- [Operations](operations.md) covers transactions, retries, cache behavior, and production checks.
- [Development and releases](development.md) covers local checks, docs, CI, and publishing.

## Guarantees

1. Keep billing decisions independent from persistence.
2. Accept application-defined service and asset names.
3. Make balance deductions and ledger writes happen in the caller's transaction.
4. Keep cache and observability failures from changing the billing decision.
5. Keep the in-memory adapters available for tests without requiring them in production.
