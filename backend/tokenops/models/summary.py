"""
TokenOps — Organization Usage Summary (Prefix-Sum Rollup Table).

Table:
    organization_usage_summary — Incrementally updated dashboard aggregates.

Design rules:
    • This table exists ONLY for read performance.  It is NOT the source of
      truth — the token_transaction_ledger and ai_usage_logs are authoritative.
    • One row per organization (UNIQUE on organization_name).
    • Every AI request that writes to ai_usage_logs also issues:
          UPDATE organization_usage_summary
          SET    total_prompt_tokens     = total_prompt_tokens     + :prompt,
                 total_completion_tokens = total_completion_tokens + :completion,
                 total_tokens            = total_tokens            + :total,
                 total_cost              = total_cost              + :cost,
                 request_count           = request_count           + 1,
                 last_updated            = :now
          WHERE  organization_name = :org
      This is the Incremental Aggregation algorithm.
    • Dashboard reads are O(1):
          SELECT * FROM organization_usage_summary WHERE organization_name = :org
    • A missing row is lazily created on first AI call for the org (upsert
      pattern in the service layer).
    • SQLite WAL mode serialises concurrent UPDATE statements to the same row,
      preventing double-counts without SELECT FOR UPDATE.

    Prefix-sum property:
        total_tokens = SUM(prompt + completion) for all ai_usage_logs rows
                       belonging to this org.  The rollup table stores the
                       running prefix sum so that dashboard reads avoid the
                       O(N) scan of ai_usage_logs.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from database import Base


class OrganizationUsageSummary(Base):
    """
    Prefix-sum rollup table for per-organization AI token usage.

    Updated atomically by the service layer on every successful LLM call.
    Read by dashboard endpoints for O(1) cost and token totals.

    The Numeric(20, 8) type for total_cost provides sub-cent precision across
    very large token volumes without floating-point accumulation error.

    last_updated is the timestamp of the most recent LLM call that touched
    this row — not a DB onupdate trigger, because the service layer controls
    the UPDATE statement directly for atomicity.
    """

    __tablename__ = "organization_usage_summary"
    __table_args__ = (
        UniqueConstraint(
            "organization_name",
            name="uq_org_usage_summary_org",
        ),
        # Already covered by UNIQUE but an explicit index makes intent clear.
        Index("ix_org_usage_summary_org", "organization_name"),
        Index("ix_org_usage_summary_updated", "last_updated"),
    )

    id                      = Column(Integer, primary_key=True, index=True)
    organization_name       = Column(String, nullable=False, unique=True, index=True,
                                     comment="Tenant identifier")

    # --- Incremental counters (prefix sums) ---
    total_prompt_tokens     = Column(BigInteger, nullable=False, default=0,
                                     comment="Running sum of all prompt_tokens across ai_usage_logs")
    total_completion_tokens = Column(BigInteger, nullable=False, default=0,
                                     comment="Running sum of all completion_tokens across ai_usage_logs")
    total_tokens            = Column(BigInteger, nullable=False, default=0,
                                     comment="= total_prompt_tokens + total_completion_tokens")
    total_cost              = Column(
        Numeric(precision=20, scale=8),
        nullable=False,
        default=Decimal("0.0"),
        comment="Running sum of cost across ai_usage_logs (USD)",
    )
    request_count           = Column(BigInteger, nullable=False, default=0,
                                     comment="Total number of LLM API calls for this org")
    last_updated            = Column(DateTime, nullable=False, default=datetime.utcnow,
                                     comment="Timestamp of the last AI call that updated this row")

    def __repr__(self) -> str:
        return (
            f"<OrganizationUsageSummary "
            f"org={self.organization_name!r} "
            f"tokens={self.total_tokens} "
            f"cost={self.total_cost} "
            f"requests={self.request_count}>"
        )


class UserUsageSummary(Base):
    """
    Prefix-sum rollup table for per-user AI token usage inside an organization.

    Updated atomically by the service layer on every successful LLM call.
    Read by dashboard endpoints for O(1) top user analytics without scanning AIUsageLog.
    """

    __tablename__ = "user_usage_summary"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_name",
            name="uq_user_usage_summary",
        ),
        Index("ix_user_usage_summary_user", "user_id"),
        Index("ix_user_usage_summary_org", "organization_name"),
    )

    id                      = Column(Integer, primary_key=True, index=True)
    user_id                 = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_name       = Column(String, nullable=False, index=True)

    total_prompt_tokens     = Column(BigInteger, nullable=False, default=0)
    total_completion_tokens = Column(BigInteger, nullable=False, default=0)
    total_tokens            = Column(BigInteger, nullable=False, default=0)
    total_cost              = Column(
        Numeric(precision=20, scale=8),
        nullable=False,
        default=Decimal("0.0"),
    )
    request_count           = Column(BigInteger, nullable=False, default=0)
    last_updated            = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<UserUsageSummary "
            f"user_id={self.user_id} "
            f"org={self.organization_name!r} "
            f"tokens={self.total_tokens}>"
        )
