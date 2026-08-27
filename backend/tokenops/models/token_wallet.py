"""
TokenOps — Wallet models.

Tables:
    organization_wallet   — One prepaid token wallet per organization.
    user_organization     — Adjacency-list mapping: user ↔ organization (M:N).
    user_token_wallet     — Per-user token allocation within an organization.

Design rules:
    • organization_name is the tenant key (string FK, matches existing pattern).
    • All primary keys are integers for SQLite compatibility except where UUID
      is explicitly required (organization_wallet.id uses UUID stored as CHAR(36)).
    • Composite UNIQUE constraints enforce one-wallet-per-org and one-wallet-per-
      user-per-org at the database level, not just the application level.
    • BigInteger maps to INTEGER in SQLite (dynamic typing handles 64-bit values).
    • No SELECT FOR UPDATE — SQLite WAL mode serialises writes natively.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
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


# ---------------------------------------------------------------------------
# 1. OrganizationWallet
# ---------------------------------------------------------------------------

class OrganizationWallet(Base):
    """
    Prepaid token wallet owned by an organization.

    One row per organization (enforced by UNIQUE on organization_name).

    Token accounting identity:
        remaining_tokens = purchased_tokens - consumed_tokens - reserved_tokens

    The wallet layer intentionally does NOT duplicate AIUsageLog data.
    Consumed totals are sourced from the token_transaction_ledger DEBIT entries
    so the wallet balance is always reconcilable against the immutable ledger.

    Data structure: Hash lookup — O(1) read via organization_name unique index.
    """

    __tablename__ = "organization_wallet"
    __table_args__ = (
        UniqueConstraint("organization_name", name="uq_org_wallet_org_name"),
        # Partial index: quickly find all blocked wallets for admin sweep.
        Index("ix_org_wallet_blocked", "is_blocked"),
    )

    # UUID primary key stored as CHAR(36); SQLite has no native UUID type.
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )
    organization_name = Column(
        String, index=True, nullable=False, comment="Tenant identifier"
    )
    organization_id   = Column(
        String(36), index=True, nullable=True, comment="Authoritative UUID tenant key"
    )

    # --- Token counters (all in raw token units, not USD) ---
    purchased_tokens = Column(BigInteger, nullable=False, default=0,
                              comment="Cumulative tokens purchased/allocated by Super Admin")
    remaining_tokens = Column(BigInteger, nullable=False, default=0,
                              comment="Tokens still available for consumption")
    reserved_tokens  = Column(BigInteger, nullable=False, default=0,
                              comment="Tokens reserved for in-flight requests (soft lock)")

    # --- Feature flags & PAYG Option C Limits ---
    payg_enabled           = Column(Boolean, nullable=False, default=False,
                                    comment="True = org may consume beyond wallet balance at PAYG rate")
    payg_soft_limit_usd    = Column(Numeric(precision=10, scale=2), nullable=True, default=None,
                                    comment="Configurable soft spending warning limit in USD")
    payg_hard_limit_usd    = Column(Numeric(precision=10, scale=2), nullable=True, default=None,
                                    comment="Configurable hard spending cap in USD (blocks consumption once reached)")
    payg_current_spend_usd = Column(Numeric(precision=20, scale=8), nullable=False, default=Decimal("0.0"),
                                    comment="Accumulated PAYG dollar spend in the current billing cycle")
    payg_billing_email     = Column(String, nullable=True,
                                    comment="Dedicated billing contact email for PAYG invoices and alerts")
    is_blocked             = Column(Boolean, nullable=False, default=False,
                                    comment="True = all LLM calls rejected; admin override required")

    # --- Audit timestamps ---
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<OrganizationWallet org={self.organization_name!r} "
            f"remaining={self.remaining_tokens} blocked={self.is_blocked}>"
        )


# ---------------------------------------------------------------------------
# 2. UserOrganization  (Adjacency List)
# ---------------------------------------------------------------------------

class UserOrganization(Base):
    """
    Adjacency-list mapping a User to one or more Organizations.

    Replaces the scalar User.organization_name FK pattern for multi-org users.
    The existing User.organization_name column is preserved for backward
    compatibility — this table is additive, not a replacement.

    Lookup complexity: O(1) via composite index (user_id, organization_name).
    A user's full org list is O(k) where k = number of orgs the user belongs to.

    Roles are stored as plain strings (matching OrganizationRole.name) rather
    than a FK to avoid a hard coupling to the RBAC role table.
    """

    __tablename__ = "user_organization"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_name",
            name="uq_user_org_membership",
        ),
        # Composite index — the primary lookup for "which orgs does user X belong to?"
        Index("ix_user_org_user_org", "user_id", "organization_name"),
        # Secondary index — "which users belong to org Y?" (admin list view)
        Index("ix_user_org_org_active", "organization_name", "is_active"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_name = Column(String, nullable=False, index=True)
    organization_id   = Column(String(36), index=True, nullable=True)
    role              = Column(String, nullable=False, default="member",
                               comment="Role name within this organization")
    is_active         = Column(Boolean, nullable=False, default=True)
    joined_at         = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship back to the built-in User model (read-only, no back_populates
    # because we must not modify the User model in Phase 2).
    user = relationship("User", foreign_keys=[user_id], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<UserOrganization user_id={self.user_id} "
            f"org={self.organization_name!r} role={self.role!r} "
            f"active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# 3. UserTokenWallet
# ---------------------------------------------------------------------------

class UserTokenWallet(Base):
    """
    Per-user token allocation inside a specific organization.

    Tokens belong to the organization, not the user.  The user wallet tracks
    how many of the org's tokens have been *allocated* to this user and how
    many the user has *consumed*.

    Token accounting identity:
        remaining_tokens = allocated_tokens - consumed_tokens

    A user may have a wallet in multiple organizations (one row per org).

    Lookup complexity: O(1) via UNIQUE (user_id, organization_name) composite index.
    """

    __tablename__ = "user_token_wallet"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_name",
            name="uq_user_token_wallet",
        ),
        Index("ix_user_token_wallet_org", "organization_name"),
        Index("ix_user_token_wallet_blocked", "is_blocked"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_name = Column(String, nullable=False, index=True)
    organization_id   = Column(String(36), index=True, nullable=True)

    # Token counters — maintained by the wallet service; ledger is source of truth.
    allocated_tokens  = Column(BigInteger, nullable=False, default=0,
                                comment="Tokens granted by Org Admin to this user")
    consumed_tokens   = Column(BigInteger, nullable=False, default=0,
                                comment="Tokens consumed via AI calls")
    remaining_tokens  = Column(BigInteger, nullable=False, default=0,
                                comment="allocated_tokens - consumed_tokens")

    is_blocked        = Column(Boolean, nullable=False, default=False,
                                comment="True = this user's LLM calls are blocked within this org")
    created_at        = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at        = Column(DateTime, nullable=False, default=datetime.utcnow,
                               onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<UserTokenWallet user_id={self.user_id} "
            f"org={self.organization_name!r} "
            f"remaining={self.remaining_tokens}>"
        )
