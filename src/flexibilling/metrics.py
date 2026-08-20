"""Optional Prometheus metrics for billing operations.

The core package works without ``prometheus-client``. When the optional
dependency is installed, these metrics are registered using a neutral
``flexibilling`` prefix rather than an application-specific name.
"""

from __future__ import annotations

from typing import Any


class _NoopChild:
    def inc(self, amount: float = 1.0) -> None:
        return None

    def observe(self, amount: float) -> None:
        return None

    def set(self, amount: float) -> None:
        return None


class _NoopMetric:
    def labels(self, *args: Any, **kwargs: Any) -> _NoopChild:
        return _NoopChild()

    def inc(self, amount: float = 1.0) -> None:
        return None

    def observe(self, amount: float) -> None:
        return None

    def set(self, amount: float) -> None:
        return None


def _counter(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Any:
    try:
        from prometheus_client import Counter

        return Counter(name, documentation, labelnames=labelnames)
    except ImportError:
        return _NoopMetric()


def _histogram(
    name: str,
    documentation: str,
    labelnames: tuple[str, ...] = (),
    buckets: tuple[float, ...] | None = None,
) -> Any:
    try:
        from prometheus_client import Histogram

        kwargs: dict[str, Any] = {"labelnames": labelnames}
        if buckets is not None:
            kwargs["buckets"] = buckets
        return Histogram(name, documentation, **kwargs)
    except ImportError:
        return _NoopMetric()


def _gauge(name: str, documentation: str) -> Any:
    try:
        from prometheus_client import Gauge

        return Gauge(name, documentation)
    except ImportError:
        return _NoopMetric()


BILLING_USAGE_RECORDS = _counter(
    "flexibilling_usage_records_total",
    "Usage records processed by the billing worker, by service and outcome.",
    ("billing_service", "outcome"),
)
BILLING_USAGE_DURATION = _histogram(
    "flexibilling_usage_processing_duration_seconds",
    "Billing worker processing time for one usage record.",
    ("billing_service", "outcome"),
    (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
BILLING_RULE_EVALUATIONS = _counter(
    "flexibilling_rule_evaluations_total",
    "Billing waterfall rule evaluations by service, result, and target asset.",
    ("billing_service", "outcome", "asset"),
)
BILLING_BALANCE_OPERATIONS = _counter(
    "flexibilling_balance_operations_total",
    "Balance funding, charging, and refund operations by outcome.",
    ("operation", "asset", "outcome"),
)
BILLING_BALANCE_OPERATION_DURATION = _histogram(
    "flexibilling_balance_operation_duration_seconds",
    "Duration of balance funding, charging, and refund operations.",
    ("operation", "asset"),
    (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
BILLING_WORKER_CYCLES = _counter(
    "flexibilling_worker_cycles_total",
    "Billing worker poll cycles by outcome.",
    ("outcome",),
)
BILLING_WORKER_CYCLE_DURATION = _histogram(
    "flexibilling_worker_cycle_duration_seconds",
    "Duration of one billing worker poll cycle.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
BILLING_WORKER_RECORDS = _counter(
    "flexibilling_worker_records_total",
    "Billing worker records handled by service and outcome.",
    ("billing_service", "outcome"),
)
BILLING_WORKER_LAST_SUCCESS = _gauge(
    "flexibilling_worker_last_success_unixtime",
    "Unix timestamp of the last completed billing worker poll cycle.",
)
BILLING_WORKER_BATCH_SIZE = _gauge(
    "flexibilling_worker_last_batch_size",
    "Number of usage records fetched by the last billing worker cycle.",
)


def observe_balance_operation(
    *, operation: str, asset: str, outcome: str, duration_seconds: float
) -> None:
    """Record an operation without allowing observability to affect billing."""

    try:
        BILLING_BALANCE_OPERATIONS.labels(operation, asset, outcome).inc()
        BILLING_BALANCE_OPERATION_DURATION.labels(operation, asset).observe(duration_seconds)
    except Exception:
        return None
