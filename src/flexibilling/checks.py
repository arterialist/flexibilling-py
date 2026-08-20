"""Backend-neutral balance checks for routes and background jobs."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from .exceptions import GatekeeperDeniedError
from .models import AssetName, CustomerId, enum_value
from .ports import BillingCache, BillingRepository


async def has_balance(
    customer_id: CustomerId,
    asset_types: Sequence[AssetName],
    *,
    cache: BillingCache,
    repository: BillingRepository | None = None,
) -> bool:
    """Return whether the selected assets have a positive combined balance.

    A cold cache is warmed from the repository when one is supplied. Without a
    repository, a cold cache fails closed.
    """

    balances = await cache.get_balances(customer_id)
    if not balances and repository is not None:
        rows = await repository.get_customer_balances(customer_id)
        if rows:
            await cache.set_balances(
                customer_id,
                {row.asset_type: Decimal(str(row.amount)) for row in rows},
            )
            balances = await cache.get_balances(customer_id)
    return sum(_decimal(balances.get(enum_value(asset))) for asset in asset_types) > 0


async def require_balance(
    customer_id: CustomerId,
    asset_types: Sequence[AssetName],
    *,
    cache: BillingCache,
    repository: BillingRepository | None = None,
) -> None:
    """Raise ``GatekeeperDeniedError`` when the selected assets are exhausted."""

    if not await has_balance(
        customer_id,
        asset_types,
        cache=cache,
        repository=repository,
    ):
        raise GatekeeperDeniedError(customer_id)


def _decimal(value: str | None) -> Decimal:
    try:
        return Decimal(value or "0")
    except (ArithmeticError, ValueError):
        return Decimal("0")
