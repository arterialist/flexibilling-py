"""Priority-ordered rule evaluation and asset selection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..exceptions import InsufficientFundsError, NoBillableUsageError, RuleNotFoundError
from ..metrics import BILLING_RULE_EVALUATIONS
from ..models import AssetName, BillingRule, UsageRecord, enum_value
from .rating import RatingEngine


@dataclass(frozen=True, slots=True)
class WaterfallResult:
    asset_type: AssetName
    amount: Decimal
    rule: BillingRule | Any
    refund_service_type: str | None = None


class WaterfallEngine:
    """Evaluate active rules in ascending priority until one can be funded."""

    def __init__(self, rating_engine: RatingEngine | None = None) -> None:
        self._rating = rating_engine or RatingEngine()

    def evaluate(
        self,
        rules: list[BillingRule] | tuple[BillingRule, ...],
        record: UsageRecord | Any,
        balances: dict[AssetName, Decimal],
    ) -> WaterfallResult:
        service = enum_value(record.service)
        if not rules:
            BILLING_RULE_EVALUATIONS.labels(service, "rule_not_found", "none").inc()
            raise RuleNotFoundError(record.service)

        saw_positive_cost = False
        for rule in sorted(rules, key=lambda item: item.priority):
            asset = rule.target_asset
            asset_label = enum_value(asset)
            if not self._rating.matches_filter(rule, getattr(record, "event_metadata", None)):
                BILLING_RULE_EVALUATIONS.labels(service, "filter_mismatch", asset_label).inc()
                continue

            cost = self._rating.calculate_cost(rule, record)
            if cost <= 0:
                BILLING_RULE_EVALUATIONS.labels(service, "zero_cost", asset_label).inc()
                continue
            saw_positive_cost = True

            available = _balance_for_asset(balances, asset)
            if available >= cost:
                BILLING_RULE_EVALUATIONS.labels(service, "matched", asset_label).inc()
                return WaterfallResult(
                    asset_type=asset,
                    amount=cost,
                    rule=rule,
                    refund_service_type=(
                        enum_value(rule.refund_service_type)
                        if rule.refund_service_type is not None
                        else None
                    ),
                )

            BILLING_RULE_EVALUATIONS.labels(service, "insufficient_balance", asset_label).inc()

        if not saw_positive_cost:
            BILLING_RULE_EVALUATIONS.labels(service, "no_billable_usage", "none").inc()
            raise NoBillableUsageError(record.customer_id, record.service)

        BILLING_RULE_EVALUATIONS.labels(service, "insufficient_funds", "none").inc()
        raise InsufficientFundsError(record.customer_id, record.service)


def _balance_for_asset(balances: dict[AssetName, Decimal], asset: AssetName) -> Decimal:
    if asset in balances:
        return Decimal(str(balances[asset]))
    asset_label = enum_value(asset)
    for key, amount in balances.items():
        if enum_value(key) == asset_label:
            return Decimal(str(amount))
    return Decimal("0")
