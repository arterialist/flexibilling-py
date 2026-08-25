# Operations

## Before production

Before enabling billing in a deployed backend:

1. Define and review active rules for each billable service.
2. Seed product mappings and verify their external identifiers.
3. Add indexes for balances and usage records in the host database.
4. Use a transaction-aware repository for balance deductions.
5. Configure a durable cache if the gatekeeper or period views need it.
6. Run the worker with a bounded batch size and a shutdown path.
7. Export billing metrics and alert on repeated failed records.
8. Test payment retries and duplicate usage delivery before launch.

## Cache consistency

The database holds the authoritative state. Cache writes update derived views
after a successful balance operation. Call
`BillingService.refresh_customer_balance_cache` after cache eviction or a
deployment that starts with an empty cache.

If the cache is unavailable, use a backend-specific fallback. Use
`NullBillingCache` only when the application can operate without fast balance
checks and period views.

## Transactions

When processing a record, the repository should keep these operations in one
transaction:

- lock and deduct the selected balance;
- insert the balance transaction;
- mark the usage record processed or failed.

Do not acknowledge a queue message before the transaction commits. Leave a
record pending after an unexpected exception so the queue can retry it.

## Product grants

`fund_customer` accepts one or more external product identifiers and a payment
reference. It checks for an existing ledger transaction before applying each
active product mapping.

- `top_up` adds to the current balance;
- `monthly_quota` replaces the balance with the configured grant.

Keep the payment webhook's event identifier stable across retries.

## Security and privacy

- Treat customer identifiers, payment references, and event metadata as sensitive application data.
- Do not put secrets in `event_metadata` or cache feed events.
- Validate product identifiers at the payment boundary before granting balances.
- Restrict access to balance, usage, and ledger endpoints to the owning customer or an authorized operator.
- Use TLS for Redis and database connections outside a trusted local environment.

## Schema

The SQLAlchemy adapter provides a schema example. It does not provide
migrations, retention jobs, or archival policy. The host application owns those
decisions.
