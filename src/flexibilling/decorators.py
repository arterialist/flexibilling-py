"""Configurable decorators and usage sessions.

The module receives all storage dependencies from the host backend. It never
imports a repository provider, settings object, or framework response class.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any, TypeAlias

from .context import (
    BillingContext,
    get_billing_context,
    reset_billing_context,
    set_billing_context,
)
from .exceptions import BillingConfigurationError, BillingContextError, GatekeeperDeniedError
from .models import (
    AssetName,
    CustomerId,
    EventMetadata,
    ServiceName,
    UsageRecordCreate,
    copy_metadata,
    enum_value,
)
from .ports import UsageRepository
from .service import BillingService

ResponseFactory: TypeAlias = Callable[[int, dict[str, Any]], Any]


class BillingDecorators:
    """``requires``, ``consumes``, and ``session`` bound to host adapters."""

    def __init__(
        self,
        service: BillingService | Callable[[], BillingService] | None = None,
        usage_repository: UsageRepository | Callable[[], UsageRepository] | None = None,
        *,
        response_factory: ResponseFactory | None = None,
    ) -> None:
        self._service_source = service
        self._usage_repository_source = usage_repository
        self._response_factory = response_factory

    def configure(
        self,
        service: BillingService | Callable[[], BillingService],
        usage_repository: UsageRepository | Callable[[], UsageRepository],
        *,
        response_factory: ResponseFactory | None = None,
    ) -> BillingDecorators:
        """Bind an existing decorator singleton to backend dependencies."""

        self._service_source = service
        self._usage_repository_source = usage_repository
        self._response_factory = response_factory
        return self

    def requires(self, asset_type: AssetName, min_amount: float = 0.0) -> Callable[..., Any]:
        """Gate a call before execution, optionally requiring a specific amount."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                service = self._service()
                customer_id = _resolve_customer_id(args, kwargs)
                if customer_id is None:
                    return self._respond_or_raise(
                        422,
                        {
                            "detail": "customer_id is required for billing validation",
                            "asset_type": enum_value(asset_type),
                        },
                        BillingContextError("customer_id is required for billing validation"),
                    )

                cache = service.cache
                balances = await cache.get_balances(customer_id)
                if not balances:
                    rows = await service.repo.get_customer_balances(customer_id)
                    if not rows:
                        return self._respond_or_raise(
                            402,
                            {
                                "detail": "Billing state not initialized",
                                "asset_type": enum_value(asset_type),
                            },
                            GatekeeperDeniedError(customer_id),
                        )
                    await cache.set_balances(
                        customer_id,
                        {row.asset_type: Decimal(str(row.amount)) for row in rows},
                    )
                    balances = await cache.get_balances(customer_id)

                if not await cache.can_transact(customer_id):
                    return self._respond_or_raise(
                        402,
                        {"detail": "Insufficient balance", "asset_type": enum_value(asset_type)},
                        GatekeeperDeniedError(customer_id),
                    )

                if min_amount > 0:
                    available = await cache.get_asset_amount(customer_id, asset_type)
                    if available is None or available < Decimal(str(min_amount)):
                        return self._respond_or_raise(
                            402,
                            {
                                "detail": f"Insufficient {enum_value(asset_type)}",
                                "required": min_amount,
                                "available": str(available),
                            },
                            GatekeeperDeniedError(customer_id),
                        )
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def consumes(self, asset_type: AssetName, amount: float = 1.0) -> Callable[..., Any]:
        """Reserve a fixed amount before execution and refund it on failure."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                service = self._service()
                customer_id = _resolve_customer_id(args, kwargs)
                if customer_id is None:
                    return self._respond_or_raise(
                        422,
                        {
                            "detail": "customer_id is required for billing validation",
                            "asset_type": enum_value(asset_type),
                        },
                        BillingContextError("customer_id is required for billing validation"),
                    )
                charge_amount = Decimal(str(amount))
                await service.charge(customer_id, enum_value(asset_type), charge_amount)
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    try:
                        await service.refund(
                            customer_id,
                            enum_value(asset_type),
                            charge_amount,
                            description=(
                                f"refund: {enum_value(asset_type)} x {charge_amount} "
                                "(execution failed)"
                            ),
                        )
                    finally:
                        raise

            return wrapper

        return decorator

    @contextlib.asynccontextmanager
    async def session(
        self,
        customer_id: CustomerId,
        service: ServiceName,
        *,
        variant: str | None = None,
        reference_id: CustomerId | None = None,
        metadata: EventMetadata | None = None,
        write_on_exception: bool = True,
    ) -> AsyncIterator[BillingContext]:
        """Track a usage session and enqueue one pending usage record on exit."""

        ctx = BillingContext(
            customer_id=customer_id,
            service=service,
            variant=variant,
            reference_id=reference_id,
            metadata=copy_metadata(metadata),
        )
        token = set_billing_context(ctx)
        exception_occurred = False
        try:
            yield ctx
        except Exception:
            exception_occurred = True
            raise
        finally:
            reset_billing_context(token)
            if not ctx.metrics.is_empty() and (not exception_occurred or write_on_exception):
                try:
                    await self._write_usage_record(ctx)
                except Exception:
                    # Usage reporting is best effort at the request boundary; the
                    # host can observe this through its repository/logging layer.
                    pass

    async def _write_usage_record(self, ctx: BillingContext) -> None:
        repository = self._usage_repository()
        if ctx.service is None:
            raise BillingConfigurationError("service is required for writing a usage record")
        metadata = copy_metadata(ctx.metadata)
        if ctx.metrics.duration_seconds and "duration_seconds" not in metadata:
            metadata["duration_seconds"] = float(ctx.metrics.duration_seconds)
        await repository.create(
            UsageRecordCreate(
                customer_id=ctx.customer_id,
                reference_id=ctx.reference_id,
                service=ctx.service,
                variant=ctx.variant or "default",
                quantity=ctx.metrics.quantity or None,
                duration_seconds=ctx.metrics.duration_seconds or None,
                units=ctx.metrics.units or None,
                input_units=ctx.metrics.input_units or None,
                output_units=ctx.metrics.output_units or None,
                cached_units=ctx.metrics.cached_units or None,
                event_metadata=metadata or None,
            )
        )

    def _service(self) -> BillingService:
        source = self._service_source
        if source is None:
            raise BillingConfigurationError(
                "Configure BillingDecorators with a BillingService first"
            )
        return source() if callable(source) else source

    def _usage_repository(self) -> UsageRepository:
        source = self._usage_repository_source
        if source is None:
            raise BillingConfigurationError(
                "Configure BillingDecorators with a UsageRepository first"
            )
        return source() if callable(source) else source

    def _respond_or_raise(self, status_code: int, content: dict[str, Any], error: Exception) -> Any:
        if self._response_factory is not None:
            return self._response_factory(status_code, content)
        raise error


def _resolve_customer_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> CustomerId | None:
    context = get_billing_context()
    if context is not None:
        return context.customer_id

    candidate = kwargs.get("customer_id")
    if candidate is None:
        candidate = kwargs.get("customer")
    if candidate is None:
        for value in (*args, *kwargs.values()):
            candidate = getattr(value, "customer_id", None) or getattr(value, "id", None)
            if candidate is not None:
                break
    if candidate is None:
        return None
    return getattr(candidate, "id", candidate)


billing = BillingDecorators()
