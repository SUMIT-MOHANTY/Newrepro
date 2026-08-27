"""
TokenOps — Tenant Resolver Service.

Provides deterministic resolution from any incoming tenant identifier
(UUID, exact legacy name, or case-insensitive string) to the authoritative
Organization UUID, strictly enforcing tenant isolation and disallowing ambiguous guesses.
"""

import logging
from typing import Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from tokenops.models.organization import Organization, LegacyOrganizationIdentifier

logger = logging.getLogger(__name__)


class TenantResolverService:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, identifier: Optional[str], enforce_active: bool = True) -> Tuple[str, Organization]:
        """
        Deterministically resolve an input identifier to (organization_id_uuid, Organization).

        Resolution Order:
            1. If identifier is None/empty -> 400/403
            2. Direct UUID lookup on Organization.id
            3. Exact case-sensitive match on LegacyOrganizationIdentifier.legacy_name
            4. Normalized case-insensitive lookup on LegacyOrganizationIdentifier:
               - Exactly 1 match -> Resolved
               - >1 match -> 409 AMBIGUOUS_TENANT_IDENTITY (Never guess!)
               - 0 matches -> 404 ORGANIZATION_NOT_FOUND
            5. Enforce Organization.is_active == True if required.
        """
        if not identifier or not identifier.strip():
            raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")

        cleaned = identifier.strip()

        # 1. Direct UUID Lookup
        org = self.session.query(Organization).filter(Organization.id == cleaned).first()
        if org:
            if enforce_active and not org.is_active:
                raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
            return org.id, org

        # 2. Exact Case-Sensitive Match on Legacy Identifier
        exact_alias = self.session.query(LegacyOrganizationIdentifier).filter(
            LegacyOrganizationIdentifier.legacy_name == cleaned,
            LegacyOrganizationIdentifier.is_active == True
        ).first()

        if exact_alias:
            org = self.session.query(Organization).filter(Organization.id == exact_alias.organization_id).first()
            if not org:
                raise HTTPException(status_code=404, detail="ORGANIZATION_NOT_FOUND")
            if enforce_active and not org.is_active:
                raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
            return org.id, org

        # 2.5. Governance Project Token Lookup (Resolve project_token UUID to Organization)
        try:
            from models import GovernanceResponse
            gov = self.session.query(GovernanceResponse).filter(
                GovernanceResponse.project_token == cleaned
            ).first()
            if gov and gov.organization_name:
                org = self.session.query(Organization).filter(
                    func.lower(Organization.name) == gov.organization_name.lower()
                ).first()
                if org:
                    if enforce_active and not org.is_active:
                        raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
                    return org.id, org
        except Exception as e:
            logger.warning(f"Failed resolving tenant via GovernanceResponse project_token: {e}")

        # 3. Normalized Case-Insensitive Discovery
        normalized_aliases = self.session.query(LegacyOrganizationIdentifier).filter(
            func.lower(LegacyOrganizationIdentifier.legacy_name) == func.lower(cleaned),
            LegacyOrganizationIdentifier.is_active == True
        ).all()

        if len(normalized_aliases) > 1:
            logger.warning(
                f"Ambiguous tenant resolution for '{cleaned}'. Found {len(normalized_aliases)} matching tenants."
            )
            raise HTTPException(
                status_code=409,
                detail="AMBIGUOUS_TENANT_IDENTITY: Multiple tenants match this normalized name. Provide explicit UUID."
            )
        elif len(normalized_aliases) == 1:
            alias = normalized_aliases[0]
            org = self.session.query(Organization).filter(Organization.id == alias.organization_id).first()
            if not org:
                raise HTTPException(status_code=404, detail="ORGANIZATION_NOT_FOUND")
            if enforce_active and not org.is_active:
                raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
            return org.id, org

        # 4. No Match Found
        raise HTTPException(status_code=404, detail=f"ORGANIZATION_NOT_FOUND: No tenant matches '{cleaned}'")
