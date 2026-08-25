from datetime import datetime
from decimal import Decimal

import pytest

from flexibilling import (
    AssetType,
    BillingService,
    BillingStats,
    InMemoryBillingCache,
    MetricType,
    UsageService,
    get_usage_snapshot,
)
from flexibilling.adapters.memory import InMemoryBillingRepository
from flexibilling.worker import BillingWorker
from tests.conftest import CUSTOMER_ID, make_record, make_rule


@pytest.mark.asyncio
async def test_usage_snapshot_supports_arbitrary_assets_and_periods() -> None:
    cache = InMemoryBillingCache()
    await cache.set_balances(
        CUSTOMER_ID,
        {
            AssetType.units: Decimal("90"),
            AssetType.credits: Decimal("20"),
        },
    )
    await cache.increment_stats(
        CUSTOMER_ID,
        "2026-08",
        BillingStats(
            usage_count=2,
            quantity=10,
            custom={"asset:units": 10, "asset:credits": 4},
        ),
    )
    snapshot = await get_usage_snapshot(
        CUSTOMER_ID,
        [AssetType.units, AssetType.credits],
        cache=cache,
        now=datetime(2026, 8, 20),
    )
    assert snapshot.period == "2026-08"
    assert snapshot.metrics["units"].to_dict() == {"used": 10.0, "total": 100.0}
    assert snapshot.metrics["credits"].to_dict() == {"used": 4.0, "total": 24.0}


@pytest.mark.asyncio
async def test_worker_marks_expected_errors_and_leaves_unexpected_records_pending() -> None:
    repo = InMemoryBillingRepository(
        rules=[make_rule(metric_type=MetricType.fixed, conversion_rate=Decimal("1"))],
        records=[make_record(record_id=1)],
    )
    await repo.upsert_balance(CUSTOMER_ID, AssetType.units, Decimal("2"), session=object())
    service = BillingService(repo, InMemoryBillingCache())

    class Context:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    result = await BillingWorker(service, repo, lambda: Context()).run_once()
    assert result.fetched == 1
    assert result.processed == 1
    assert repo.records[0].billing_status == "processed"


def test_generic_service_values_are_available_for_examples() -> None:
    assert UsageService.api_request.value == "api_request"
