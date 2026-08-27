"""
TokenOps — AI Model Pricing model.

Table:
    model_pricing — Editable per-model token price, managed by Super Admin.

Design rules:
    • Prices are stored as SQLAlchemy Numeric(20, 10) which maps to REAL in
      SQLite (64-bit IEEE 754 float, ~15 significant decimal digits).
    • Effective-from enables historical price records — the active price for a
      model is the row with is_active=True and the latest effective_from.
    • The hardcoded rate of $0.000007/token in llm_gateway.py is replaced by
      a lookup against this table after Phase 2 is deployed.
    • A functional index on (model_name, is_active) supports O(1) price lookup.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base

# Default price — identical to the currently hardcoded value in llm_gateway.py
# so that the system is neutral at first deployment.
DEFAULT_PRICE_PER_TOKEN = Decimal("0.0000070000")


class ModelPricing(Base):
    """
    Editable AI model pricing table.

    One active row per model_name at any point in time.
    Historical rows are preserved (is_active=False) for billing audit.

    Lookup:
        Active price for a model:
            SELECT * FROM model_pricing
            WHERE model_name = :model AND is_active = 1
            ORDER BY effective_from DESC
            LIMIT 1

        Complexity: O(1) via (model_name, is_active) composite index.

    Dictionary cache strategy:
        The service layer maintains an in-process dict:
            _pricing_cache: dict[str, Decimal]  # model_name → price_per_token
        The cache is invalidated whenever a row is written to this table.
    """

    __tablename__ = "model_pricing"
    __table_args__ = (
        # Supports O(1) active price lookup by model name.
        Index("ix_model_pricing_active_lookup", "model_name", "is_active"),
        # Enforce at most one active price per model.
        UniqueConstraint(
            "model_name", "is_active",
            name="uq_model_pricing_active_model",
        ),
    )

    id              = Column(Integer, primary_key=True, index=True)
    model_name      = Column(String, nullable=False, index=True,
                             comment="AI model identifier, e.g. 'BournAI', 'gpt-4o'")

    # Numeric(precision=20, scale=10): supports prices as small as 0.0000000001
    # without floating-point drift.  SQLAlchemy maps this to REAL in SQLite.
    price_per_token = Column(
        Numeric(precision=20, scale=10),
        nullable=False,
        default=DEFAULT_PRICE_PER_TOKEN,
        comment="USD cost per single token (input or output)",
    )

    effective_from  = Column(DateTime, nullable=False, default=datetime.utcnow,
                             comment="Timestamp from which this price is valid")
    is_active       = Column(Boolean, nullable=False, default=True, index=True,
                             comment="Only one active row per model_name at a time")
    created_by      = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Super Admin user who created this pricing row",
    )
    created_at      = Column(DateTime, nullable=False, default=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<ModelPricing model={self.model_name!r} "
            f"price={self.price_per_token} active={self.is_active}>"
        )
