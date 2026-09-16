import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class UserQuotaRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class UserTokenQuotaRequest(Base):
    """
    Stores self-service token quota top-up requests from organization members to Org Admins.
    A user can only submit a request when their remaining allocated tokens are exhausted (<= 0).
    """
    __tablename__ = "user_token_quota_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User requesting additional token quota"
    )
    organization_name = Column(
        String,
        nullable=False,
        index=True,
        comment="Organization to which the user belongs"
    )
    organization_id = Column(
        String(36),
        nullable=True,
        index=True,
        comment="Canonical UUID tenant ID"
    )
    requested_tokens = Column(
        BigInteger,
        nullable=False,
        comment="Number of tokens requested by the user"
    )
    reason = Column(
        Text,
        nullable=True,
        comment="User's justification / project context for the top-up"
    )
    status = Column(
        String,
        nullable=False,
        default=UserQuotaRequestStatus.PENDING.value,
        index=True,
        comment="PENDING | APPROVED | REJECTED"
    )
    admin_notes = Column(
        Text,
        nullable=True,
        comment="Org Admin notes / rationale for approval or rejection"
    )
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Org Admin user who reviewed this request"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )
    reviewed_at = Column(
        DateTime,
        nullable=True
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="select")
    reviewer = relationship("User", foreign_keys=[reviewed_by], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<UserTokenQuotaRequest id={self.id} user_id={self.user_id} "
            f"org={self.organization_name!r} tokens={self.requested_tokens} "
            f"status={self.status!r}>"
        )
