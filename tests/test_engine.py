from decimal import Decimal

import pytest

from flexibilling import (
    AssetType,
    InsufficientFundsError,
    MetricType,
    NoBillableUsageError,
    RuleNotFoundError,
)
from flexibilling.engine.rating import RatingEngine, _resolve_dotted_key
from flexibilling.engine.waterfall import WaterfallEngine
from tests.conftest import make_balances, make_record, make_rule


def test_rating_supports_fixed_quantity_duration_and_units() -> None:
    record = make_record(
        quantity=3,
        event_metadata={"duration_seconds": 180},
        input_units=500,
        output_units=200,
    )
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.fixed, conversion_rate=Decimal("5")), record
    ) == Decimal("5")
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.quantity, conversion_rate=Decimal("2")), record
    ) == Decimal("6")
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.duration), record
    ) == Decimal("180")
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.units, conversion_rate=Decimal("0.001")), record
    ) == Decimal("0.7")


def test_duration_uses_record_field_when_metadata_is_absent() -> None:
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.duration), make_record(duration_seconds=12)
    ) == Decimal("12")
    assert RatingEngine.calculate_cost(
        make_rule(metric_type=MetricType.duration, conversion_rate=Decimal("0.5")),
        make_record(duration_seconds=60),
    ) == Decimal("30.0")


def test_filter_supports_dotted_keys() -> None:
    rule = make_rule(filter_condition={"result.status": "qualified"})
    assert RatingEngine.matches_filter(rule, {"result": {"status": "qualified"}})
    assert not RatingEngine.matches_filter(rule, {"result": {"status": "new"}})
    assert _resolve_dotted_key({"a": {"b": 1}}, "a.b") == 1
    assert _resolve_dotted_key({"a": "text"}, "a.b") is None


def test_waterfall_uses_priority_and_falls_back_between_assets() -> None:
    rules = [
        make_rule(priority=10, target_asset=AssetType.units),
        make_rule(priority=20, target_asset=AssetType.prepaid_units, rule_id=2),
    ]
    result = WaterfallEngine().evaluate(
        rules,
        make_record(units=60),
        make_balances(units=0, prepaid_units=200),
    )
    assert result.rule.id == 2
    assert result.amount == Decimal("60")


def test_waterfall_distinguishes_zero_usage_from_insufficient_funds() -> None:
    with pytest.raises(RuleNotFoundError):
        WaterfallEngine().evaluate([], make_record(), {})
    with pytest.raises(NoBillableUsageError):
        WaterfallEngine().evaluate([make_rule()], make_record(), make_balances(units=100))
    with pytest.raises(InsufficientFundsError):
        WaterfallEngine().evaluate(
            [make_rule()],
            make_record(units=100),
            make_balances(units=50),
        )


def test_waterfall_filter_mismatch_is_not_a_funds_failure() -> None:
    with pytest.raises(NoBillableUsageError):
        WaterfallEngine().evaluate(
            [make_rule(metric_type=MetricType.fixed, filter_condition={"channel": "api"})],
            make_record(event_metadata={"channel": "batch"}),
            make_balances(units=100),
        )
