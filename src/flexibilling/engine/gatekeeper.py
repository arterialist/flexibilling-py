"""Fast, cache-only balance permission checks."""

from __future__ import annotations

from ..exceptions import GatekeeperDeniedError
from ..models import CustomerId
from ..ports import BillingCache


class Gatekeeper:
    """Fail-closed permission check backed by a materialized balance snapshot."""

    def __init__(self, cache: BillingCache) -> None:
        self._cache = cache

    async def check(self, customer_id: CustomerId) -> bool:
        can_transact = await self._cache.can_transact(customer_id)
        balances = await self._cache.get_balances(customer_id)
        if not balances or not can_transact:
            raise GatekeeperDeniedError(customer_id)
        return True

    async def check_silent(self, customer_id: CustomerId) -> bool:
        try:
            return await self.check(customer_id)
        except GatekeeperDeniedError:
            return False
