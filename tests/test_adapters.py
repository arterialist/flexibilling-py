from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from flexibilling import (
    AssetType,
    BillingService,
    InMemoryBillingCache,
    MetricType,
    UsageRecord,
    UsageService,
)
from flexibilling.adapters.sqlalchemy import (
    BalanceTransactionModel,
    Base,
    BillingProductModel,
    BillingRuleModel,
    CustomerBalanceModel,
    SQLAlchemyBillingRepository,
    UsageRecordModel,
)
from tests.conftest import CUSTOMER_ID


@pytest.mark.asyncio
async def test_sqlalchemy_reference_adapter_processes_a_usage_record() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory.begin() as session:
        session.add(
            BillingRuleModel(
                service=UsageService.api_request.value,
                target_asset=AssetType.units.value,
                metric_type=MetricType.units.value,
                conversion_rate=Decimal("1"),
                priority=1,
                is_active=True,
            )
        )
        session.add(
            CustomerBalanceModel(
                customer_id=str(CUSTOMER_ID),
                asset_type=AssetType.units.value,
                amount=Decimal("100"),
            )
        )
    repo = SQLAlchemyBillingRepository(session_factory)
    service = BillingService(repo, InMemoryBillingCache())
    record = UsageRecord(
        id=1,
        customer_id=CUSTOMER_ID,
        service=UsageService.api_request,
        reference_id="request-1",
        units=30,
    )
    async with session_factory.begin() as session:
        await service.process_record(record, session=session)
    async with session_factory() as session:
        balance = await session.get(
            CustomerBalanceModel,
            1,
        )
        assert balance is not None
        assert Decimal(str(balance.amount)) == Decimal("70.0000")
        transaction = await session.get(BalanceTransactionModel, 1)
        assert transaction is not None
        assert transaction.amount == Decimal("-30.0000")
    await engine.dispose()


def test_reference_sqlalchemy_schema_contains_all_billing_tables() -> None:
    assert {
        "customer_balances",
        "balance_transactions",
        "billing_rules",
        "billing_products",
        "usage_records",
    } <= set(Base.metadata.tables)
    assert CustomerBalanceModel.__tablename__ == "customer_balances"
    assert BalanceTransactionModel.__tablename__ == "balance_transactions"
    assert BillingRuleModel.__tablename__ == "billing_rules"
    assert BillingProductModel.__tablename__ == "billing_products"
    assert UsageRecordModel.__tablename__ == "usage_records"
