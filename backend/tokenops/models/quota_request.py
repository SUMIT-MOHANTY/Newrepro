import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class QuotaRequestType(str, enum.Enum):
    TOKEN_INCREASE = "TOKEN_INCREASE"
    PAYG_ENABLEMENT = "PAYG_ENABLEMENT"
    LIMIT_INCREASE = "LIMIT_INCREASE"


class QuotaRequestStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TokenQuotaRequest(Base):
    """
    Stores requests from Organization Admins to Super Admins for:
    1. Token Quota Increase (adding tokens to the organization's reserve)
    2. PAYG Enablement (enabling post-paid unlimited billing for the organization)
    3. PAYG Limit Increase (raising soft/hard spending caps)
    """
    __tablename__ = "token_quota_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, nullable=False, index=True)
    organization_id = Column(String(36), index=True, nullable=True)
    request_type = Column(
        SAEnum(QuotaRequestType),
        nullable=False,
        default=QuotaRequestType.TOKEN_INCREASE,
        index=True
    )
    requested_tokens = Column(BigInteger, nullable=False, default=0)
    requested_limit_usd = Column(Numeric(precision=10, scale=2), nullable=True, comment="Requested dollar limit for LIMIT_INCREASE")
    requested_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(
        SAEnum(QuotaRequestStatus),
        nullable=False,
        default=QuotaRequestStatus.REQUESTED,
        index=True,
    )
    remarks = Column(Text, nullable=True, comment="Org Admin justification")
    admin_notes = Column(Text, nullable=True, comment="Super Admin approval/rejection remarks")
    approved_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    # Relationships
    requester = relationship("User", foreign_keys=[requested_by], lazy="select")
    approver = relationship("User", foreign_keys=[approved_by], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<TokenQuotaRequest id={self.id} org={self.organization_name!r} "
            f"type={self.request_type.value} status={self.status.value} "
            f"tokens={self.requested_tokens}>"
        )
