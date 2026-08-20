"""Top-level billing facade.

``BillingService`` owns the orchestration rules while repositories and cache
adapters own persistence. The service does not assume SQLAlchemy, Redis, or a
particular payment provider.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from .engine.gatekeeper import Gatekeeper
from .engine.rating import RatingEngine
from .engine.waterfall import WaterfallEngine, WaterfallResult
from .exceptions import (
    BillingConfigurationError,
    BillingError,
    InsufficientFundsError,
    NoBillableUsageError,
    RuleNotFoundError,
)
from .metrics import BILLING_USAGE_DURATION, BILLING_USAGE_RECORDS, observe_balance_operation
from .models import (
    BalanceTransactionCreate,
    BillingProductStrategy,
    BillingStats,
    CustomerId,
    TransactionType,
    UsageRecord,
    enum_value,
)
from .ports import BillingCache, BillingRepository, Session, TransactionFactory


class BillingService:
    """Orchestrate rating, waterfall deduction, ledger writes, and cache sync."""

    def __init__(
        self,
        repo: BillingRepository,
        cache: BillingCache,
        rating_engine: RatingEngine | None = None,
        waterfall_engine: WaterfallEngine | None = None,
        gatekeeper: Gatekeeper | None = None,
        *,
        transaction_factory: TransactionFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.cache = cache
        self._rating = rating_engine or RatingEngine()
        self._waterfall = waterfall_engine or WaterfallEngine(self._rating)
        self._gatekeeper = gatekeeper or Gatekeeper(cache)
        self._transaction_factory = transaction_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def process_record(self, record: UsageRecord, *, session: Session) -> None:
        """Process one pending usage record in the caller's transaction."""

        started_at = perf_counter()
        outcome = "failed_unexpected"
        service = enum_value(record.service)
        try:
            rules = list(await self.repo.get_active_rules(record.service, session=session))
            rows = await self.repo.get_customer_balances(record.customer_id, session=session)
            balances = {row.asset_type: Decimal(str(row.amount)) for row in rows}
            result = self._waterfall.evaluate(rules, record, balances)

            new_amount = await self.repo.decrement_balance(
                record.customer_id,
                result.asset_type,
                result.amount,
                session=session,
            )
            new_amount = Decimal(str(new_amount))
            await self.repo.create_transaction(
                BalanceTransactionCreate(
                    customer_id=record.customer_id,
                    asset_type=result.asset_type,
                    amount=-result.amount,
                    balance_after=new_amount,
                    transaction_type=TransactionType.usage,
                    source_usage_id=record.id,
                    description=(
                        f"{service} usage: -{result.amount} {enum_value(result.asset_type)}"
                    ),
                ),
                session=session,
            )

            if result.refund_service_type and record.reference_id is not None:
                await self._handle_refund(record, result.refund_service_type, session=session)

            if record.id is None:
                raise BillingConfigurationError(
                    "A usage record must have an id before it can be processed"
                )
            await self.repo.mark_record_processed(record.id, session=session)
            await self._sync_cache(record, result, new_amount)
            outcome = "processed"
        except NoBillableUsageError:
            outcome = "skipped_no_billable_usage"
            raise
        except InsufficientFundsError:
            outcome = "failed_insufficient_funds"
            raise
        except RuleNotFoundError:
            outcome = "failed_rule_not_found"
            raise
        except BillingError:
            outcome = "failed_billing"
            raise
        finally:
            try:
                BILLING_USAGE_RECORDS.labels(service, outcome).inc()
                BILLING_USAGE_DURATION.labels(service, outcome).observe(perf_counter() - started_at)
            except Exception:
                return None

    async def check_permission(self, customer_id: CustomerId) -> bool:
        return await self._gatekeeper.check(customer_id)

    async def check_permission_silent(self, customer_id: CustomerId) -> bool:
        return await self._gatekeeper.check_silent(customer_id)

    async def refresh_customer_balance_cache(
        self, customer_id: CustomerId, *, session: Session | None = None
    ) -> None:
        rows = await self.repo.get_customer_balances(customer_id, session=session)
        if not rows:
            await self.cache.delete_balances(customer_id)
            return
        await self.cache.set_balances(
            customer_id,
            {row.asset_type: Decimal(str(row.amount)) for row in rows},
        )

    async def fund_customer(
        self,
        customer_id: CustomerId,
        product_ids: Sequence[str],
        payment_reference: str,
        *,
        session: Session,
    ) -> bool:
        """Apply an idempotent provider event to all matching product grants."""

        if await self.repo.get_transaction_by_reference(payment_reference, session=session):
            return False

        products = list(await self.repo.get_products_for_external_ids(product_ids, session=session))
        if not products:
            return False

        for product in products:
            strategy = enum_value(product.strategy)
            if strategy == BillingProductStrategy.top_up.value:
                new_amount = await self.repo.increment_balance(
                    customer_id,
                    product.asset_type,
                    Decimal(str(product.amount)),
                    session=session,
                )
                transaction_type: TransactionType | str = TransactionType.top_up
                description = (
                    f"Top-up: +{product.amount} {enum_value(product.asset_type)} "
                    f"(product: {product.external_product_id})"
                )
            elif strategy == BillingProductStrategy.monthly_quota.value:
                upserted = await self.repo.upsert_balance(
                    customer_id,
                    product.asset_type,
                    Decimal(str(product.amount)),
                    session=session,
                )
                new_amount = getattr(upserted, "amount", upserted)
                transaction_type = TransactionType.monthly_grant
                description = (
                    f"Monthly quota reset: {product.amount} {enum_value(product.asset_type)} "
                    f"(product: {product.external_product_id})"
                )
            else:
                raise BillingConfigurationError(
                    f"Unknown billing product strategy: {product.strategy}"
                )

            new_amount = Decimal(str(new_amount))
            await self.repo.create_transaction(
                BalanceTransactionCreate(
                    customer_id=customer_id,
                    asset_type=product.asset_type,
                    amount=Decimal(str(product.amount)),
                    balance_after=new_amount,
                    transaction_type=transaction_type,
                    payment_reference=payment_reference,
                    description=description,
                ),
                session=session,
            )
            await self.cache.update_single_balance(customer_id, product.asset_type, new_amount)

        return True

    async def charge(
        self,
        customer_id: CustomerId,
        asset_type: str,
        amount: Decimal,
        *,
        session: Session | None = None,
        description: str | None = None,
    ) -> None:
        """Atomically deduct an asset, write a usage ledger row, and update views."""

        if amount <= 0:
            raise ValueError("charge amount must be positive")
        started_at = perf_counter()
        try:
            if session is not None:
                new_balance = await self._do_charge(
                    customer_id, asset_type, amount, description, session=session
                )
            else:
                new_balance = await self._run_in_transaction(
                    lambda tx: self._do_charge(
                        customer_id, asset_type, amount, description, session=tx
                    )
                )
            await self.cache.update_single_balance(customer_id, asset_type, new_balance)
            await self.cache.increment_stats(
                customer_id,
                self._month(),
                BillingStats(
                    usage_count=1,
                    quantity=float(amount),
                    spend=float(amount),
                    custom={f"asset:{enum_value(asset_type)}": float(amount)},
                ),
            )
        except Exception:
            observe_balance_operation(
                operation="charge",
                asset=enum_value(asset_type),
                outcome="error",
                duration_seconds=perf_counter() - started_at,
            )
            raise
        else:
            observe_balance_operation(
                operation="charge",
                asset=enum_value(asset_type),
                outcome="success",
                duration_seconds=perf_counter() - started_at,
            )

    async def refund(
        self,
        customer_id: CustomerId,
        asset_type: str,
        amount: Decimal,
        *,
        session: Session | None = None,
        description: str | None = None,
    ) -> None:
        """Atomically restore an asset and write a refund ledger row."""

        if amount <= 0:
            raise ValueError("refund amount must be positive")
        started_at = perf_counter()
        try:
            if session is not None:
                new_balance = await self._do_refund(
                    customer_id, asset_type, amount, description, session=session
                )
            else:
                new_balance = await self._run_in_transaction(
                    lambda tx: self._do_refund(
                        customer_id, asset_type, amount, description, session=tx
                    )
                )
            await self.cache.update_single_balance(customer_id, asset_type, new_balance)
        except Exception:
            observe_balance_operation(
                operation="refund",
                asset=enum_value(asset_type),
                outcome="error",
                duration_seconds=perf_counter() - started_at,
            )
            raise
        else:
            observe_balance_operation(
                operation="refund",
                asset=enum_value(asset_type),
                outcome="success",
                duration_seconds=perf_counter() - started_at,
            )

    async def _run_in_transaction(self, operation: Callable[[Session], object]) -> Decimal:
        if self._transaction_factory is None:
            raise BillingConfigurationError(
                "A transaction_factory is required when charge/refund is called without a session"
            )
        async with self._transaction_factory() as session:
            result = await operation(session)  # type: ignore[arg-type]
        return Decimal(str(result))

    async def _do_refund(
        self,
        customer_id: CustomerId,
        asset_type: str,
        amount: Decimal,
        description: str | None,
        *,
        session: Session,
    ) -> Decimal:
        new_balance = await self.repo.increment_balance(
            customer_id, asset_type, amount, session=session
        )
        await self.repo.create_transaction(
            BalanceTransactionCreate(
                customer_id=customer_id,
                asset_type=asset_type,
                amount=amount,
                balance_after=new_balance,
                transaction_type=TransactionType.refund,
                description=description or f"refund: {enum_value(asset_type)} x {amount}",
            ),
            session=session,
        )
        return Decimal(str(new_balance))

    async def _do_charge(
        self,
        customer_id: CustomerId,
        asset_type: str,
        amount: Decimal,
        description: str | None,
        *,
        session: Session,
    ) -> Decimal:
        new_balance = await self.repo.decrement_balance(
            customer_id, asset_type, amount, session=session
        )
        await self.repo.create_transaction(
            BalanceTransactionCreate(
                customer_id=customer_id,
                asset_type=asset_type,
                amount=-amount,
                balance_after=new_balance,
                transaction_type=TransactionType.usage,
                description=description or f"charge: {enum_value(asset_type)} x {amount}",
            ),
            session=session,
        )
        return Decimal(str(new_balance))

    async def _handle_refund(
        self, record: UsageRecord, refund_service: str, *, session: Session
    ) -> None:
        if record.reference_id is None:
            return
        original = await self.repo.get_transaction_for_usage(
            record.reference_id,
            refund_service,
            record.customer_id,
            session=session,
        )
        if original is None:
            return

        refund_amount = abs(Decimal(str(original.amount)))
        new_amount = await self.repo.increment_balance(
            record.customer_id,
            original.asset_type,
            refund_amount,
            session=session,
        )
        await self.repo.create_transaction(
            BalanceTransactionCreate(
                customer_id=record.customer_id,
                asset_type=original.asset_type,
                amount=refund_amount,
                balance_after=new_amount,
                transaction_type=TransactionType.refund,
                source_usage_id=record.id,
                description=(
                    f"Refund for reference {record.reference_id}: +{refund_amount} "
                    f"{enum_value(original.asset_type)}"
                ),
            ),
            session=session,
        )
        await self.cache.update_single_balance(record.customer_id, original.asset_type, new_amount)

    async def _sync_cache(
        self, record: UsageRecord, result: WaterfallResult, new_balance: Decimal
    ) -> None:
        await self.cache.update_single_balance(record.customer_id, result.asset_type, new_balance)
        asset = enum_value(result.asset_type)
        await self.cache.increment_stats(
            record.customer_id,
            self._month(),
            BillingStats(
                usage_count=1,
                quantity=float(result.amount),
                spend=float(result.amount),
                custom={f"asset:{asset}": float(result.amount)},
            ),
        )
        await self.cache.push_feed_event(
            record.customer_id,
            action=enum_value(result.rule.service),
            cost=f"{result.amount} {asset}",
            result="Success",
        )

    def _month(self) -> str:
        current = self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).strftime("%Y-%m")
