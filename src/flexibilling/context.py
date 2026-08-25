"""Context-variable based request and usage-session state."""

from __future__ import annotations

import contextvars
from contextvars import Token
from dataclasses import dataclass, field
from typing import Any

from .models import CustomerId, EventMetadata, ServiceName


@dataclass(slots=True)
class UsageMetrics:
    """Metrics accumulated during one billing session."""

    quantity: float = 0.0
    duration_seconds: float = 0.0
    units: int = 0
    input_units: int = 0
    output_units: int = 0
    cached_units: int = 0
    events: int = 0

    def is_empty(self) -> bool:
        return not any(
            (
                self.quantity,
                self.duration_seconds,
                self.units,
                self.input_units,
                self.output_units,
                self.cached_units,
                self.events,
            )
        )


@dataclass(slots=True)
class BillingContext:
    """Request-scoped customer, service, metrics, and event metadata."""

    customer_id: CustomerId
    service: ServiceName | None = None
    metrics: UsageMetrics = field(default_factory=UsageMetrics)
    metadata: EventMetadata = field(default_factory=dict)
    reference_id: CustomerId | None = None
    variant: str | None = None

    def report(
        self,
        *,
        quantity: float = 0.0,
        duration_seconds: float = 0.0,
        units: int = 0,
        input_units: int = 0,
        output_units: int = 0,
        cached_units: int = 0,
        events: int = 0,
    ) -> None:
        """Accumulate one usage report into the active context."""

        self.metrics.quantity += quantity
        self.metrics.duration_seconds += duration_seconds
        self.metrics.units += units
        self.metrics.input_units += input_units
        self.metrics.output_units += output_units
        self.metrics.cached_units += cached_units
        self.metrics.events += events

    def set_metadata(self, key: str, value: Any) -> None:
        """Set one metadata value used by rule filters or rating."""

        self.metadata[key] = value


_billing_context_var: contextvars.ContextVar[BillingContext | None] = contextvars.ContextVar(
    "flexibilling_context", default=None
)


def get_billing_context() -> BillingContext | None:
    return _billing_context_var.get()


def set_billing_context(ctx: BillingContext) -> Token[BillingContext | None]:
    return _billing_context_var.set(ctx)


def reset_billing_context(token: Token[BillingContext | None]) -> None:
    _billing_context_var.reset(token)
