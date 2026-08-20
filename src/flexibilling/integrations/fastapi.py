"""Optional FastAPI/Starlette integration helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..checks import has_balance
from ..context import BillingContext, reset_billing_context, set_billing_context
from ..models import AssetName, CustomerId
from ..ports import BillingCache, BillingRepository

try:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
except ImportError:

    class BillingMiddleware:
        """Placeholder that reports the missing optional dependency on use."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _require_fastapi()

else:

    class BillingMiddleware(BaseHTTPMiddleware):  # type: ignore[reportRedeclaration]
        """Initialize a billing context from ``request.state.customer_id``."""

        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            customer_id = getattr(request.state, "customer_id", None)
            if customer_id is None:
                return await call_next(request)
            ctx = BillingContext(
                customer_id=customer_id,
                reference_id=getattr(request.state, "billing_reference_id", None),
            )
            token = set_billing_context(ctx)
            try:
                return await call_next(request)
            finally:
                reset_billing_context(token)


def json_response_factory(status_code: int, content: dict[str, Any]) -> Any:
    """Create a Starlette JSON response without importing it in core modules."""

    _require_fastapi()
    from starlette.responses import JSONResponse

    return JSONResponse(status_code=status_code, content=content)


async def require_balance_http(
    customer_id: CustomerId,
    asset_types: Sequence[AssetName],
    *,
    cache: BillingCache,
    repository: BillingRepository | None = None,
    detail: str = "Insufficient balance",
) -> None:
    """FastAPI-friendly 402 wrapper around the backend-neutral balance check."""

    _require_fastapi()
    if not await has_balance(customer_id, asset_types, cache=cache, repository=repository):
        from fastapi import HTTPException

        raise HTTPException(status_code=402, detail=detail)


def _require_fastapi() -> None:
    try:
        import fastapi  # noqa: F401
        import starlette  # noqa: F401
    except ImportError as error:  # pragma: no cover - only without the optional extra
        raise ImportError(
            'FastAPI integration requires `uv add "flexibilling[fastapi]"`'
        ) from error
