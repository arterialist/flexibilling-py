"""Minimal FastAPI integration example.

Run with:

    uv run --extra fastapi uvicorn examples.fastapi_min.app:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from flexibilling import get_billing_context
from flexibilling.integrations.fastapi import BillingMiddleware

app = FastAPI(title="FlexiBilling example")
app.add_middleware(BillingMiddleware)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Return a response while exposing the request billing context hook."""

    context = get_billing_context()
    return {"status": "ok", "billing_context": "available" if context else "empty"}
