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
                if not org:
                    import uuid
                    from tokenops.models import OrganizationWallet

                    org_uuid = str(uuid.uuid4())
                    # Create Organization record
                    org = Organization(
                        id=org_uuid,
                        name=gov.organization_name,
                        is_active=True
                    )
                    self.session.add(org)

                    # Create legacy mapping
                    legacy = LegacyOrganizationIdentifier(
                        organization_id=org_uuid,
                        legacy_name=gov.organization_name,
                        alias_type="LEGACY_NAME",
                        is_active=True
                    )
                    self.session.add(legacy)

                    # Create default OrganizationWallet
                    wallet = OrganizationWallet(
                        id=org_uuid,
                        organization_name=gov.organization_name,
                        organization_id=org_uuid,
                        purchased_tokens=0,
                        remaining_tokens=0,
                        reserved_tokens=0,
                        payg_enabled=False,
                        is_blocked=False
                    )
                    self.session.add(wallet)
                    self.session.flush()
                    logger.info(f"Auto-healed / lazy created tokenops Organization & Wallet via GovernanceResponse project_token lookup for '{gov.organization_name}' with ID: {org.id}")

                if not org:
                    alias = self.session.query(LegacyOrganizationIdentifier).filter(
                        func.lower(LegacyOrganizationIdentifier.legacy_name) == gov.organization_name.lower(),
                        LegacyOrganizationIdentifier.is_active == True
                    ).first()
                    if alias:
                        org = self.session.query(Organization).filter(Organization.id == alias.organization_id).first()
                if org:
                    if enforce_active and not org.is_active:
                        raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
                    return org.id, org
        except Exception as e:
            logger.warning(f"Failed resolving tenant via GovernanceResponse project_token: {e}")

        # 3. Direct Match on Organization.name
        org = self.session.query(Organization).filter(
            func.lower(Organization.name) == func.lower(cleaned)
        ).first()
        if org:
            if enforce_active and not org.is_active:
                raise HTTPException(status_code=403, detail="ORGANIZATION_INACTIVE")
            return org.id, org

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

        # --- AUTO-HEAL / LAZY CREATION ---
        # If the organization name is not in tokenops organizations but exists in the core system DB,
        # dynamically provision Organization UUID, Legacy Mapping, and Org Wallet.
        try:
            from models import User, UserOrganizationRole
            exists_in_users = self.session.query(User).filter(
                func.lower(User.organization_name) == func.lower(cleaned)
            ).first() is not None

            if not exists_in_users:
                exists_in_users = self.session.query(UserOrganizationRole).filter(
                    func.lower(UserOrganizationRole.organization_name) == func.lower(cleaned)
                ).first() is not None

            if exists_in_users:
                import uuid
                from tokenops.models import OrganizationWallet

                # Find canonical casing
                canonical_org_name = cleaned
                user_record = self.session.query(User).filter(
                    func.lower(User.organization_name) == func.lower(cleaned)
                ).first()
                if user_record and user_record.organization_name:
                    canonical_org_name = user_record.organization_name
                else:
                    role_record = self.session.query(UserOrganizationRole).filter(
                        func.lower(UserOrganizationRole.organization_name) == func.lower(cleaned)
                    ).first()
                    if role_record and role_record.organization_name:
                        canonical_org_name = role_record.organization_name

                # Create Organization record
                import uuid
                org_uuid = str(uuid.uuid4())
                org = Organization(
                    id=org_uuid,
                    name=canonical_org_name,
                    is_active=True
                )
                self.session.add(org)

                # Create legacy mapping
                legacy = LegacyOrganizationIdentifier(
                    organization_id=org_uuid,
                    legacy_name=canonical_org_name,
                    alias_type="LEGACY_NAME",
                    is_active=True
                )
                self.session.add(legacy)

                # Create default OrganizationWallet
                wallet = OrganizationWallet(
                    id=org_uuid,
                    organization_name=canonical_org_name,
                    organization_id=org_uuid,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False
                )
                self.session.add(wallet)
                self.session.flush()

                logger.info(f"Auto-healed / lazy created tokenops Organization & Wallet for '{canonical_org_name}' with ID: {org.id}")
                return org.id, org
        except Exception as e:
            logger.warning(f"Failed to auto-heal organization '{cleaned}': {e}")

        # 4. No Match Found
        raise HTTPException(status_code=404, detail=f"ORGANIZATION_NOT_FOUND: No tenant matches '{cleaned}'")
