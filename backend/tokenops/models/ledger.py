"""
TokenOps — Immutable Token Transaction Ledger.

Table:
    token_transaction_ledger — Append-only financial audit trail.

Design rules:
    • This is the MOST IMPORTANT table in TokenOps.
    • NEVER issue UPDATE or DELETE statements against this table.
    • Every token movement in the system (purchase, allocation, consumption,
      revocation) MUST produce exactly one INSERT into this table.
    • balance_after stores the org wallet balance immediately after this
      transaction — enabling O(n) ledger replay and O(1) point-in-time
      balance reconstruction without scanning ai_usage_logs.
    • token_delta is signed:
          Positive (+) → tokens added  (PURCHASE, ALLOCATION)
          Negative (-) → tokens removed (AI_CONSUMPTION, REVOCATION)
    • reference_id links the ledger row to the triggering entity:
          AI_CONSUMPTION → ai_usage_logs.id (as string)
          ALLOCATION     → user_token_wallet.id (as string)
          PURCHASE       → external invoice / Super Admin action ID
    • Composite index (organization_name, created_at) enables efficient
      time-range queries for billing and reconciliation reports.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class TransactionType(str, enum.Enum):
    """
    All legal token movement types in the TokenOps ledger.

    PURCHASE          — Super Admin credits tokens to an org wallet.
    ALLOCATION        — Org Admin allocates tokens from org wallet to a user wallet.
    REALLOCATION      — Org Admin moves tokens between two user wallets.
    AI_CONSUMPTION    — Tokens deducted for an LLM API call (prepaid path).
    PAYG_USAGE        — Tokens deducted for an LLM API call (PAYG path, no prepaid balance).
    REVOCATION        — Super Admin or Org Admin reclaims unspent allocated tokens.
    MANUAL_ADJUSTMENT — Super Admin correction entry with mandatory remarks.
    """
    PURCHASE          = "PURCHASE"
    ALLOCATION        = "ALLOCATION"
    REALLOCATION      = "REALLOCATION"
    AI_CONSUMPTION    = "AI_CONSUMPTION"
    PAYG_USAGE        = "PAYG_USAGE"
    REVOCATION        = "REVOCATION"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


# Pre-computed set for O(1) membership test in the service layer.
DEBIT_TYPES  = frozenset({
    TransactionType.AI_CONSUMPTION,
    TransactionType.PAYG_USAGE,
    TransactionType.REVOCATION,
})
CREDIT_TYPES = frozenset({
    TransactionType.PURCHASE,
    TransactionType.ALLOCATION,
    TransactionType.MANUAL_ADJUSTMENT,
})


# ---------------------------------------------------------------------------
# 7. TokenTransactionLedger
# ---------------------------------------------------------------------------

class TokenTransactionLedger(Base):
    """
    Immutable append-only financial ledger for all token movements.

    Every row represents a single atomic token event.  The balance_after column
    denormalises the wallet balance at the moment of the transaction so that:

        1. Any point-in-time balance can be read from a single row.
        2. The current balance equals the balance_after of the latest row for
           the organization.
        3. Full ledger replay can reconstruct every wallet state.

    Append-only guarantee:
        The service layer MUST NOT issue UPDATE or DELETE on this table.
        Database-level enforcement is via a trigger in the migration script.

    Running balance algorithm (service layer responsibility):
        new_balance = current_wallet.remaining_tokens + token_delta
        INSERT INTO token_transaction_ledger (balance_after=new_balance, ...)
        UPDATE organization_wallet SET remaining_tokens = new_balance

    Composite indexes:
        (organization_name, created_at) — time-range billing reports      O(log N)
        (organization_name, transaction_type) — type-filtered audit report O(log N)
        (user_id, created_at)           — per-user consumption history     O(log N)
        (reference_id)                  — correlate ledger ↔ ai_usage_logs O(log N)
    """

    __tablename__ = "token_transaction_ledger"
    __table_args__ = (
        # Composite indexes for efficient time-range and filtered queries.
        Index("ix_ttl_org_created",   "organization_name", "created_at"),
        Index("ix_ttl_org_type",      "organization_name", "transaction_type"),
        Index("ix_ttl_user_created",  "user_id",           "created_at"),
        Index("ix_ttl_reference",     "reference_id"),
        # Enforce token_delta sign convention:
        #   DEBIT types  → token_delta must be <= 0
        #   CREDIT types → token_delta must be >= 0
        # SQLite supports CHECK constraints.
        CheckConstraint(
            "token_delta != 0",
            name="ck_ttl_token_delta_nonzero",
        ),
    )

    id                = Column(Integer, primary_key=True, index=True,
                               autoincrement=True)
    organization_name = Column(String, nullable=False, index=True,
                               comment="Tenant — matches organization_wallet.organization_name")
    organization_id   = Column(String(36), index=True, nullable=True)
    user_id           = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="User who triggered or received the token movement (nullable for org-level events)",
    )
    transaction_type  = Column(
        String, nullable=False, index=True,
        comment="One of TransactionType enum values",
    )
    token_delta       = Column(
        BigInteger, nullable=False,
        comment="Signed token change: positive = credit, negative = debit",
    )
    balance_after     = Column(
        BigInteger, nullable=False,
        comment="OrganizationWallet.remaining_tokens immediately after this transaction",
    )
    reference_id      = Column(
        String, nullable=True, index=True,
        comment="ID of the triggering entity, e.g. ai_usage_logs.id or user_token_wallet.id",
    )
    purpose           = Column(String, nullable=True, index=True,
                               comment="Circumstance or feature that triggered this transaction (e.g. Requirement Screening, BRD Analysis, Admin Quota Allocation)")
    project_token     = Column(String, nullable=True, index=True,
                               comment="Project token if this transaction occurred within a specific project context")
    project_name      = Column(String, nullable=True, index=True,
                               comment="Human-readable project name associated with project_token")
    remarks           = Column(Text, nullable=True,
                               comment="Human-readable note; mandatory for MANUAL_ADJUSTMENT")
    created_by        = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User or system actor who initiated this ledger entry",
    )
    created_at        = Column(DateTime, nullable=False, default=datetime.utcnow,
                               index=True)

    # Relationships (read-only; no back_populates to avoid modifying User model)
    user    = relationship("User", foreign_keys=[user_id],    lazy="select")
    creator = relationship("User", foreign_keys=[created_by], lazy="select")

    @property
    def transaction_type_enum(self) -> TransactionType:
        """Return the typed enum value for the transaction_type column."""
        return TransactionType(self.transaction_type)

    @property
    def is_debit(self) -> bool:
        return self.token_delta < 0

    @property
    def is_credit(self) -> bool:
        return self.token_delta > 0

    def __repr__(self) -> str:
        return (
            f"<TokenTransactionLedger id={self.id} "
            f"org={self.organization_name!r} "
            f"type={self.transaction_type!r} "
            f"delta={self.token_delta:+d} "
            f"balance_after={self.balance_after}>"
        )
