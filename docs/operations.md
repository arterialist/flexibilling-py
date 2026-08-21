# Operations

## Production checklist

Before enabling billing in a deployed backend:

1. Define and review active rules for every billable service.
2. Seed product mappings and verify their external identifiers.
3. Ensure balances and usage records are covered by the host database's indexes.
4. Use a transaction-aware repository implementation for balance deductions.
5. Configure a durable cache only if the gatekeeper or period views need it.
6. Run the worker with a bounded batch size and graceful shutdown handling.
7. Export billing metrics and alert on repeated failed records.
8. Test idempotent payment events and duplicate usage delivery before launch.

## Cache consistency

The database is the source of truth. Cache writes are materialized views updated
after a successful balance operation. Call
`BillingService.refresh_customer_balance_cache` after cache eviction or a
deployment that starts with an empty cache.

If the cache is unavailable, use a backend-specific fallback or a
`NullBillingCache` only when the application can safely operate without fast
balance checks and period views.

## Transactions

When processing a record, the repository should keep these operations in one
transaction:

- lock and deduct the selected balance;
- insert the balance transaction;
- mark the usage record processed or failed.

Do not acknowledge a queue message before the transaction commits. Unexpected
exceptions should leave the record pending so the queue can retry it.

## Product grants

`fund_customer` accepts one or more external product identifiers and a payment
reference. It first checks the reference for an existing ledger transaction,
then applies each active product mapping.

- `top_up` adds to the current balance;
- `monthly_quota` replaces the balance with the configured grant.

Keep the payment webhook's event identifier stable across retries.

## Security and privacy

- Treat customer identifiers, payment references, and event metadata as sensitive application data.
- Do not put secrets in `event_metadata` or cache feed events.
- Validate product identifiers at the payment boundary before granting balances.
- Restrict access to balance, usage, and ledger endpoints to the owning customer or an authorized operator.
- Use TLS for Redis and database connections outside a trusted local environment.

## Schema ownership

The SQLAlchemy adapter is a reference schema. It does not provide migrations,
retention jobs, or archival policy. The host application owns those concerns and
should decide how long to retain usage records and ledger entries.
