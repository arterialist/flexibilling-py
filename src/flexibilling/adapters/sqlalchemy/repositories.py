"""SQLAlchemy implementations of the FlexiBilling storage protocols."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...exceptions import InsufficientFundsError
from ...models import (
    BalanceTransaction,
    BalanceTransactionCreate,
    BillingProduct,
    BillingRule,
    BillingStatus,
    CustomerBalance,
    CustomerId,
    ServiceName,
    UsageRecord,
    UsageRecordCreate,
    UsageSummary,
    enum_value,
)
from ...ports import Session
from .models import (
    BalanceTransactionModel,
    BillingProductModel,
    BillingRuleModel,
    CustomerBalanceModel,
    UsageRecordModel,
)


class SQLAlchemyBillingRepository:
    """Async repository backed by the neutral reference tables."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_active_rules(
        self, service: ServiceName, *, session: Session | None = None
    ) -> list[BillingRule]:
        async def query(db: AsyncSession) -> list[BillingRule]:
            result = await db.execute(
                select(BillingRuleModel)
                .where(
                    BillingRuleModel.service == enum_value(service),
                    BillingRuleModel.is_active.is_(True),
                )
                .order_by(BillingRuleModel.priority.asc())
            )
            return [_rule(row) for row in result.scalars().all()]

        return await self._read(query, session)

    async def get_customer_balances(
        self, customer_id: CustomerId, *, session: Session | None = None
    ) -> list[CustomerBalance]:
        async def query(db: AsyncSession) -> list[CustomerBalance]:
            result = await db.execute(
                select(CustomerBalanceModel).where(
                    CustomerBalanceModel.customer_id == str(customer_id)
                )
            )
            return [_balance(row) for row in result.scalars().all()]

        return await self._read(query, session)

    async def upsert_balance(
        self,
        customer_id: CustomerId,
        asset_type: str,
        amount: Decimal,
        *,
        session: Session,
    ) -> CustomerBalance:
        db = _session(session)
        row = await self._locked_balance(db, customer_id, asset_type)
        if row is None:
            row = CustomerBalanceModel(
                customer_id=str(customer_id),
                asset_type=enum_value(asset_type),
                amount=amount,
            )
            db.add(row)
        else:
            row.amount = amount
        await db.flush()
        return _balance(row)

    async def decrement_balance(
        self,
        customer_id: CustomerId,
        asset_type: str,
        deduction: Decimal,
        *,
        session: Session,
    ) -> Decimal:
        db = _session(session)
        row = await self._locked_balance(db, customer_id, asset_type)
        if row is None or Decimal(str(row.amount)) < deduction:
            raise InsufficientFundsError(customer_id, "charge")
        row.amount = Decimal(str(row.amount)) - deduction
        await db.flush()
        return Decimal(str(row.amount))

    async def increment_balance(
        self,
        customer_id: CustomerId,
        asset_type: str,
        addition: Decimal,
        *,
        session: Session,
    ) -> Decimal:
        db = _session(session)
        row = await self._locked_balance(db, customer_id, asset_type)
        if row is None:
            row = CustomerBalanceModel(
                customer_id=str(customer_id),
                asset_type=enum_value(asset_type),
                amount=addition,
            )
            db.add(row)
        else:
            row.amount = Decimal(str(row.amount)) + addition
        await db.flush()
        return Decimal(str(row.amount))

    async def create_transaction(
        self, data: BalanceTransactionCreate, *, session: Session
    ) -> BalanceTransaction:
        db = _session(session)
        row = BalanceTransactionModel(
            customer_id=str(data.customer_id),
            asset_type=enum_value(data.asset_type),
            amount=data.amount,
            balance_after=data.balance_after,
            transaction_type=enum_value(data.transaction_type),
            source_usage_id=_int_or_none(data.source_usage_id),
            payment_reference=data.payment_reference,
            description=data.description,
        )
        db.add(row)
        await db.flush()
        return _transaction(row)

    async def get_transaction_for_usage(
        self,
        reference_id: object,
        service: ServiceName,
        customer_id: CustomerId,
        *,
        session: Session,
    ) -> BalanceTransaction | None:
        db = _session(session)
        result = await db.execute(
            select(BalanceTransactionModel)
            .join(UsageRecordModel, BalanceTransactionModel.source_usage_id == UsageRecordModel.id)
            .where(
                UsageRecordModel.reference_id == str(reference_id),
                UsageRecordModel.service == enum_value(service),
                BalanceTransactionModel.customer_id == str(customer_id),
                BalanceTransactionModel.transaction_type == "usage",
            )
            .order_by(BalanceTransactionModel.created_at.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return _transaction(row) if row is not None else None

    async def get_transaction_by_reference(
        self, payment_reference: str, *, session: Session | None = None
    ) -> BalanceTransaction | None:
        async def query(db: AsyncSession) -> BalanceTransaction | None:
            result = await db.execute(
                select(BalanceTransactionModel)
                .where(BalanceTransactionModel.payment_reference == payment_reference)
                .limit(1)
            )
            row = result.scalars().first()
            return _transaction(row) if row is not None else None

        return await self._read(query, session)

    async def get_products_for_external_ids(
        self, external_product_ids: Sequence[str], *, session: Session | None = None
    ) -> list[BillingProduct]:
        async def query(db: AsyncSession) -> list[BillingProduct]:
            result = await db.execute(
                select(BillingProductModel).where(
                    BillingProductModel.external_product_id.in_(list(external_product_ids)),
                    BillingProductModel.is_active.is_(True),
                )
            )
            return [_product(row) for row in result.scalars().all()]

        return await self._read(query, session)

    async def get_pending_records(self, limit: int = 50, *, session: Session) -> list[UsageRecord]:
        db = _session(session)
        result = await db.execute(
            select(UsageRecordModel)
            .where(UsageRecordModel.billing_status == BillingStatus.pending.value)
            .order_by(UsageRecordModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [_usage_record(row) for row in result.scalars().all()]

    async def mark_record_processed(self, record_id: object, *, session: Session) -> None:
        await _session(session).execute(
            update(UsageRecordModel)
            .where(UsageRecordModel.id == _int_or_none(record_id))
            .values(billing_status=BillingStatus.processed.value)
        )

    async def mark_record_failed(
        self, record_id: object, error_message: str, *, session: Session
    ) -> None:
        await _session(session).execute(
            update(UsageRecordModel)
            .where(UsageRecordModel.id == _int_or_none(record_id))
            .values(
                billing_status=BillingStatus.failed.value,
                billing_error_message=error_message,
            )
        )

    async def mark_record_skipped(self, record_id: object, *, session: Session) -> None:
        await _session(session).execute(
            update(UsageRecordModel)
            .where(UsageRecordModel.id == _int_or_none(record_id))
            .values(billing_status=BillingStatus.skipped.value)
        )

    async def _locked_balance(
        self, db: AsyncSession, customer_id: CustomerId, asset_type: str
    ) -> CustomerBalanceModel | None:
        result = await db.execute(
            select(CustomerBalanceModel)
            .where(
                CustomerBalanceModel.customer_id == str(customer_id),
                CustomerBalanceModel.asset_type == enum_value(asset_type),
            )
            .with_for_update()
        )
        return result.scalars().first()

    async def _read(self, query: Any, session: Session | None) -> Any:
        if session is not None:
            return await query(_session(session))
        async with self.session_factory() as db:
            return await query(db)


class SQLAlchemyUsageRepository:
    """Usage-record writer for ``billing.session``."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create(
        self, data: UsageRecordCreate, *, session: Session | None = None
    ) -> UsageRecord:
        owns_session = session is None
        db = _session(session) if session is not None else self.session_factory()
        if owns_session:
            async with db as managed:
                record = await self._create(managed, data)
                await managed.commit()
                return record
        return await self._create(db, data)

    async def _create(self, db: AsyncSession, data: UsageRecordCreate) -> UsageRecord:
        row = UsageRecordModel(
            customer_id=str(data.customer_id),
            reference_id=_str_or_none(data.reference_id),
            service=enum_value(data.service),
            variant=data.variant,
            quantity=data.quantity,
            duration_seconds=data.duration_seconds,
            units=data.units,
            input_units=data.input_units,
            output_units=data.output_units,
            cached_units=data.cached_units,
            billing_status=enum_value(data.billing_status),
            billing_error_message=data.billing_error_message,
            event_metadata=data.event_metadata,
        )
        db.add(row)
        await db.flush()
        return _usage_record(row)

    async def get_by_customer(
        self, customer_id: CustomerId, skip: int = 0, limit: int = 100
    ) -> list[UsageRecord]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(UsageRecordModel)
                .where(UsageRecordModel.customer_id == str(customer_id))
                .order_by(UsageRecordModel.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            return [_usage_record(row) for row in result.scalars().all()]

    async def get_usage_summary(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[UsageSummary]:
        async with self.session_factory() as db:
            conditions = [UsageRecordModel.customer_id == str(customer_id)]
            if from_date is not None:
                conditions.append(UsageRecordModel.created_at >= from_date)
            if to_date is not None:
                conditions.append(UsageRecordModel.created_at <= to_date)
            result = await db.execute(
                select(
                    UsageRecordModel.service,
                    UsageRecordModel.variant,
                    func.count().label("request_count"),
                    func.sum(UsageRecordModel.quantity).label("total_quantity"),
                    func.sum(UsageRecordModel.duration_seconds).label("total_duration_seconds"),
                    func.sum(UsageRecordModel.units).label("total_units"),
                    func.sum(UsageRecordModel.input_units).label("total_input_units"),
                    func.sum(UsageRecordModel.output_units).label("total_output_units"),
                    func.sum(UsageRecordModel.cached_units).label("total_cached_units"),
                )
                .where(*conditions)
                .group_by(UsageRecordModel.service, UsageRecordModel.variant)
            )
            return [
                UsageSummary(
                    service=row.service,
                    variant=row.variant,
                    usage_count=row.request_count,
                    total_quantity=_float_or_none(row.total_quantity),
                    total_duration_seconds=_float_or_none(row.total_duration_seconds),
                    total_units=row.total_units,
                    total_input_units=row.total_input_units,
                    total_output_units=row.total_output_units,
                    total_cached_units=row.total_cached_units,
                )
                for row in result.all()
            ]

    async def get_usage_records(
        self,
        customer_id: CustomerId,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        service: ServiceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UsageRecord], int]:
        async with self.session_factory() as db:
            conditions = [UsageRecordModel.customer_id == str(customer_id)]
            if from_date is not None:
                conditions.append(UsageRecordModel.created_at >= from_date)
            if to_date is not None:
                conditions.append(UsageRecordModel.created_at <= to_date)
            if service is not None:
                conditions.append(UsageRecordModel.service == enum_value(service))
            total_result = await db.execute(
                select(func.count(UsageRecordModel.id)).where(*conditions)
            )
            total = int(total_result.scalar() or 0)
            result = await db.execute(
                select(UsageRecordModel)
                .where(*conditions)
                .order_by(UsageRecordModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [_usage_record(row) for row in result.scalars().all()], total


def _session(session: Session) -> AsyncSession:
    return session  # type: ignore[return-value]


def _balance(row: CustomerBalanceModel) -> CustomerBalance:
    return CustomerBalance(row.customer_id, row.asset_type, Decimal(str(row.amount)), row.id)


def _transaction(row: BalanceTransactionModel) -> BalanceTransaction:
    return BalanceTransaction(
        customer_id=row.customer_id,
        asset_type=row.asset_type,
        amount=Decimal(str(row.amount)),
        balance_after=Decimal(str(row.balance_after)),
        transaction_type=row.transaction_type,
        id=row.id,
        source_usage_id=row.source_usage_id,
        payment_reference=row.payment_reference,
        description=row.description,
        created_at=row.created_at,
    )


def _rule(row: BillingRuleModel) -> BillingRule:
    return BillingRule(
        service=row.service,
        priority=row.priority,
        target_asset=row.target_asset,
        metric_type=row.metric_type,
        conversion_rate=Decimal(str(row.conversion_rate)),
        filter_condition=dict(row.filter_condition) if row.filter_condition else None,
        refund_service_type=row.refund_service_type,
        is_active=row.is_active,
        id=row.id,
    )


def _product(row: BillingProductModel) -> BillingProduct:
    return BillingProduct(
        external_product_id=row.external_product_id,
        asset_type=row.asset_type,
        amount=Decimal(str(row.amount)),
        strategy=row.strategy,
        description=row.description,
        is_active=row.is_active,
        id=row.id,
    )


def _usage_record(row: UsageRecordModel) -> UsageRecord:
    return UsageRecord(
        customer_id=row.customer_id,
        service=row.service,
        variant=row.variant,
        id=row.id,
        reference_id=row.reference_id,
        quantity=_float_or_none(row.quantity),
        duration_seconds=row.duration_seconds,
        units=row.units,
        input_units=row.input_units,
        output_units=row.output_units,
        cached_units=row.cached_units,
        billing_status=row.billing_status,
        billing_error_message=row.billing_error_message,
        event_metadata=dict(row.event_metadata) if row.event_metadata else None,
        created_at=row.created_at,
    )


def _str_or_none(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _float_or_none(value: object | None) -> float | None:
    return float(value) if value is not None else None  # type: ignore[arg-type]


def _int_or_none(value: object | None) -> int | None:
    if value is None:
        return None
    return int(str(value))
