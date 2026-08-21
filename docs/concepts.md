# Concepts

## Core objects

| Object | Purpose |
| --- | --- |
| `CustomerBalance` | Current amount of one named asset for a customer. |
| `BillingRule` | Maps a service and metric to a target asset and conversion rate. |
| `UsageRecord` | A billable event waiting to be rated and processed. |
| `BalanceTransaction` | Immutable ledger movement produced by funding, usage, or refunds. |
| `BillingProduct` | External product identifier mapped to a balance grant. |
| `BillingCache` | Materialized balances, period counters, and activity feed. |

`customer_id`, `service`, `asset_type`, `variant`, and `reference_id` are
application-defined identifiers. The package does not impose a catalog of
services or assets.

## Rating metrics

Each rule uses one `MetricType`:

| Metric | Cost calculation |
| --- | --- |
| `fixed` | `conversion_rate` once per record. |
| `quantity` | Record `quantity` multiplied by the rate. |
| `duration` | `duration_seconds` multiplied by the rate. |
| `units` | `units`, or `input_units + output_units`, multiplied by the rate. |

Duration can be supplied in `UsageRecord.duration_seconds` or in
`event_metadata["duration_seconds"]`. Metadata takes precedence, which lets a
backend record a more accurate elapsed duration without changing its model.

## The priority waterfall

The waterfall sorts active rules by ascending `priority` and evaluates them in
order:

1. Skip a rule whose metadata filter does not match.
2. Calculate its positive cost.
3. Select the first target asset with enough balance.
4. Raise `NoBillableUsageError` if no rule produces a positive cost.
5. Raise `InsufficientFundsError` if costs exist but no asset can fund one.

This supports a primary quota with a prepaid fallback without hard-coding either
asset name into the engine.

## Transactions and idempotency

`BillingService.process_record` expects the caller to provide a transaction
session. The repository should lock the balance row, deduct the amount, insert
the ledger transaction, and update the record status in that transaction.

`fund_customer` is idempotent on `payment_reference`. If the reference already
has a ledger transaction, no product grant is applied a second time.

`charge` and `refund` can either use a caller-owned session or use the configured
`transaction_factory`. Configure the factory when these methods are called
without an explicit session.

## Failure states

The worker marks expected billing outcomes explicitly:

- processed records become `processed`;
- records without billable usage become `skipped`;
- insufficient funds and other expected billing failures become `failed`;
- unexpected exceptions remain pending for a later retry.

The worker catches observability failures so metrics cannot change the billing
result.
