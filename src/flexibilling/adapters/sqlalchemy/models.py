"""Neutral SQLAlchemy tables for the reference adapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the optional reference schema."""


class TimestampedMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CustomerBalanceModel(TimestampedMixin, Base):
    __tablename__ = "customer_balances"

    customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))

    __table_args__ = (
        UniqueConstraint("customer_id", "asset_type", name="uq_flexibilling_customer_asset"),
        Index("ix_flexibilling_customer_balances_customer_asset", "customer_id", "asset_type"),
    )


class BalanceTransactionModel(TimestampedMixin, Base):
    __tablename__ = "balance_transactions"

    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_usage_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_flexibilling_balance_tx_customer_created", "customer_id", "created_at"),
        Index("ix_flexibilling_balance_tx_source_usage", "source_usage_id"),
    )


class BillingRuleModel(TimestampedMixin, Base):
    __tablename__ = "billing_rules"

    service: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    target_asset: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    conversion_rate: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("1")
    )
    filter_condition: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    refund_service_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_flexibilling_billing_rules_service_priority", "service", "priority"),
    )


class BillingProductModel(TimestampedMixin, Base):
    __tablename__ = "billing_products"

    external_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="top_up")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("external_product_id", "asset_type", name="uq_flexibilling_product_asset"),
        Index("ix_flexibilling_products_external_product", "external_product_id"),
    )


class UsageRecordModel(TimestampedMixin, Base):
    __tablename__ = "usage_records"

    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    variant: Mapped[str] = mapped_column(String(255), nullable=False, default="default")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    billing_error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_flexibilling_usage_customer_created", "customer_id", "created_at"),)
