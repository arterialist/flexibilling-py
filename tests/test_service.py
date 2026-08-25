from datetime import UTC, datetime
from decimal import Decimal

import pytest

from flexibilling import (
    AssetType,
    BillingProduct,
    BillingProductStrategy,
    BillingService,
    InMemoryBillingCache,
    TransactionType,
)
from flexibilling.adapters.memory import InMemoryBillingRepository
from tests.conftest import CUSTOMER_ID, make_record, make_rule


@pytest.mark.asyncio
async def test_process_record_deducts_ledger_and_updates_cache() -> None:
    repo = InMemoryBillingRepository(rules=[make_rule()])
    cache = InMemoryBillingCache()
    service = BillingService(repo, cache, clock=lambda: datetime(2026, 8, 20, tzinfo=UTC))
    await repo.upsert_balance(CUSTOMER_ID, AssetType.units, Decimal("100"), session=object())
    record = make_record(units=30)
    repo.records.append(record)

    await service.process_record(record, session=object())

    assert record.billing_status == "processed"
    balances = await repo.get_customer_balances(CUSTOMER_ID)
    assert balances[0].amount == Decimal("70")
    assert repo.transactions[0].transaction_type == TransactionType.usage
    assert await cache.get_asset_amount(CUSTOMER_ID, AssetType.units) == Decimal("70")
    stats = await cache.get_stats(CUSTOMER_ID, "2026-08")
    assert stats["total_usage_count"] == "1"
    assert stats["total_quantity"] == "30.0"


@pytest.mark.asyncio
async def test_funding_is_idempotent_and_supports_quota_reset() -> None:
    repo = InMemoryBillingRepository(
        products=[
            BillingProduct(
                external_product_id="plan-standard",
                asset_type=AssetType.units,
                amount=Decimal("1000"),
                strategy=BillingProductStrategy.monthly_quota,
            )
        ]
    )
    service = BillingService(repo, InMemoryBillingCache())
    await repo.upsert_balance(CUSTOMER_ID, AssetType.units, Decimal("7"), session=object())

    assert await service.fund_customer(CUSTOMER_ID, ["plan-standard"], "event-1", session=object())
    assert not await service.fund_customer(
        CUSTOMER_ID, ["plan-standard"], "event-1", session=object()
    )
    balance = await repo.get_customer_balances(CUSTOMER_ID)
    assert balance[0].amount == Decimal("1000")
    assert repo.transactions[0].transaction_type == TransactionType.monthly_grant


@pytest.mark.asyncio
async def test_charge_refunds_on_shared_transaction_session() -> None:
    repo = InMemoryBillingRepository()
    service = BillingService(repo, InMemoryBillingCache())
    await repo.upsert_balance(CUSTOMER_ID, AssetType.credits, Decimal("10"), session=object())

    await service.charge(CUSTOMER_ID, AssetType.credits, Decimal("3"), session=object())
    await service.refund(CUSTOMER_ID, AssetType.credits, Decimal("3"), session=object())

    assert (await repo.get_customer_balances(CUSTOMER_ID))[0].amount == Decimal("10")
    assert [tx.transaction_type for tx in repo.transactions] == [
        TransactionType.usage,
        TransactionType.refund,
    ]


@pytest.mark.asyncio
async def test_refresh_cache_warms_and_deletes_empty_snapshots() -> None:
    repo = InMemoryBillingRepository()
    cache = InMemoryBillingCache()
    service = BillingService(repo, cache)
    await repo.upsert_balance(CUSTOMER_ID, AssetType.units, Decimal("120"), session=object())

    await service.refresh_customer_balance_cache(CUSTOMER_ID)
    assert await cache.get_balances(CUSTOMER_ID) == {
        "units": "120",
        "can_transact": "1",
    }
    await service.refresh_customer_balance_cache("other")
    assert await cache.get_balances("other") == {}
