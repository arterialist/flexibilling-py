import uuid

import pytest

from flexibilling import BillingDecorators, BillingService, InMemoryBillingCache, UsageService
from flexibilling.adapters.memory import InMemoryBillingRepository, InMemoryUsageRepository
from flexibilling.context import get_billing_context


@pytest.mark.asyncio
async def test_session_sets_resets_and_writes_one_usage_record() -> None:
    target = InMemoryBillingRepository()
    usage_repo = InMemoryUsageRepository(target)
    billing = BillingDecorators(BillingService(target, InMemoryBillingCache()), usage_repo)
    customer_id = uuid.uuid4()

    assert get_billing_context() is None
    async with billing.session(
        customer_id,
        UsageService.api_request,
        variant="standard",
        reference_id="request-42",
    ) as context:
        assert get_billing_context() is context
        context.report(duration_seconds=95, input_units=10)

    assert get_billing_context() is None
    record = target.records[0]
    assert record.event_metadata == {"duration_seconds": 95.0}
    assert record.input_units == 10
    assert record.reference_id == "request-42"


@pytest.mark.asyncio
async def test_empty_session_and_opted_out_exception_do_not_write() -> None:
    target = InMemoryBillingRepository()
    usage_repo = InMemoryUsageRepository(target)
    billing = BillingDecorators(BillingService(target, InMemoryBillingCache()), usage_repo)

    async with billing.session(uuid.uuid4(), UsageService.background_task):
        pass
    assert target.records == []

    with pytest.raises(RuntimeError):
        async with billing.session(
            uuid.uuid4(), UsageService.background_task, write_on_exception=False
        ) as context:
            context.report(events=1)
            raise RuntimeError("boom")
    assert target.records == []
