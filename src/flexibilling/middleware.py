"""Compatibility import for the optional FastAPI middleware."""

from .integrations.fastapi import BillingMiddleware

__all__ = ["BillingMiddleware"]
