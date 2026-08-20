"""FlexiBilling — provider-agnostic usage metering and balance billing.

The package keeps the billing engine independent from a web framework, ORM,
cache, and payment provider. Implement the protocols in :mod:`flexibilling.ports`
or use the included in-memory, Redis, and SQLAlchemy adapters.
"""

from .__about__ import __version__
from .cache import InMemoryBillingCache, NullBillingCache
from .checks import has_balance, require_balance
from .context import BillingContext, UsageMetrics, get_billing_context
from .decorators import BillingDecorators, billing
from .engine import Gatekeeper, RatingEngine, WaterfallEngine, WaterfallResult
from .exceptions import (
    BillingConfigurationError,
    BillingContextError,
    BillingError,
    GatekeeperDeniedError,
    InsufficientFundsError,
    NoBillableUsageError,
    RuleNotFoundError,
)
from .models import (
    AssetType,
    BalanceTransaction,
    BalanceTransactionCreate,
    BillingProduct,
    BillingProductStrategy,
    BillingRule,
    BillingStats,
    BillingStatus,
    CustomerBalance,
    MetricType,
    TransactionType,
    UsageRecord,
    UsageRecordCreate,
    UsageService,
    UsageSummary,
)
from .service import BillingService
from .snapshot import UsageMetric, UsageSnapshot, get_usage_snapshot
from .worker import BillingWorker, WorkerCycleResult

__all__ = [
    "__version__",
    "AssetType",
    "BalanceTransaction",
    "BalanceTransactionCreate",
    "BillingConfigurationError",
    "BillingContext",
    "BillingContextError",
    "BillingDecorators",
    "BillingError",
    "BillingProduct",
    "BillingProductStrategy",
    "BillingRule",
    "BillingService",
    "BillingStats",
    "BillingStatus",
    "BillingWorker",
    "CustomerBalance",
    "Gatekeeper",
    "GatekeeperDeniedError",
    "InMemoryBillingCache",
    "InsufficientFundsError",
    "MetricType",
    "NoBillableUsageError",
    "NullBillingCache",
    "RatingEngine",
    "RuleNotFoundError",
    "TransactionType",
    "UsageMetric",
    "UsageMetrics",
    "UsageRecord",
    "UsageRecordCreate",
    "UsageService",
    "UsageSummary",
    "UsageSnapshot",
    "WaterfallEngine",
    "WaterfallResult",
    "WorkerCycleResult",
    "billing",
    "get_billing_context",
    "get_usage_snapshot",
    "has_balance",
    "require_balance",
]
