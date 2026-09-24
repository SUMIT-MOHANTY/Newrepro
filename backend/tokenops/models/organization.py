"""
TokenOps — Tenant Master & Legacy Identifier Models.

Tables:
    organizations — Canonical tenant master table keyed by immutable UUID.
    legacy_organization_identifiers — Deterministic lookup table mapping legacy string identifiers to UUIDs.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Organization(Base):
    """
    Canonical Tenant Master.
    
    The organization_id (UUID) is the single immutable authoritative identity.
    Display name is human-readable and mutable.
    """
    __tablename__ = "organizations"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Authoritative immutable UUID",
    )
    name = Column(
        String,
        nullable=False,
        index=True,
        comment="Canonical display name",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    legacy_identifiers = relationship(
        "LegacyOrganizationIdentifier",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id!r} name={self.name!r} active={self.is_active}>"


class LegacyOrganizationIdentifier(Base):
    """
    Deterministic compatibility mapping for legacy organization strings.

    Resolves historical organization_name strings (e.g. from JWT, API payload, SSO)
    to the authoritative organization_id UUID.
    """
    __tablename__ = "legacy_organization_identifiers"
    __table_args__ = (
        UniqueConstraint("legacy_name", name="uq_legacy_org_identifier_name"),
        Index("ix_legacy_org_identifier_name", "legacy_name"),
        Index("ix_legacy_org_identifier_org_id", "organization_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    legacy_name = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
        comment="Exact case-sensitive legacy name",
    )
    alias_type = Column(
        String,
        nullable=False,
        default="LEGACY_NAME",
        comment="LEGACY_NAME, SSO_DOMAIN, or CUSTOM_ALIAS",
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="legacy_identifiers")

    def __repr__(self) -> str:
        return (
            f"<LegacyOrganizationIdentifier legacy_name={self.legacy_name!r} "
            f"org_id={self.organization_id!r} active={self.is_active}>"
        )
