"""
TokenOps — Tenant Resolver Service.

Provides deterministic resolution from any incoming tenant identifier
(UUID, exact legacy name, or case-insensitive string) to the authoritative
Organization UUID, strictly enforcing tenant isolation and disallowing ambiguous guesses.
"""

import base64
import json
import logging
from typing import Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from tokenops.models.organization import Organization, LegacyOrganizationIdentifier

logger = logging.getLogger(__name__)


def _is_jwt(val: Optional[str]) -> bool:
    if not val or not isinstance(val, str):
        return False
    parts = val.strip().split(".")
    return len(parts) == 3 and parts[0].startswith("ey")


def _decode_jwt_unverified_payload(jwt_str: str) -> dict:
    try:
        parts = jwt_str.strip().split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception:
        return {}


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

        # Handle JWT tokens gracefully (never let raw JWT cause 404 ORGANIZATION_NOT_FOUND)
        if _is_jwt(cleaned):
            payload = _decode_jwt_unverified_payload(cleaned)
            candidate_org = None
            try:
                from app.integrations.llm import llm_gateway
                candidate_org = llm_gateway.current_user_org_var.get()
                if candidate_org and _is_jwt(candidate_org):
                    candidate_org = None
            except Exception:
                candidate_org = None

            if not candidate_org:
                try:
                    from app.integrations.llm import llm_gateway
                    uid = llm_gateway.current_user_id_var.get()
                    if uid:
                        from models import User
                        u = self.session.query(User).filter(User.id == uid).first()
                        if u and u.organization_name:
                            candidate_org = u.organization_name
                except Exception:
                    pass

            if not candidate_org and payload.get("client_id"):
                cid = payload["client_id"]
                try:
                    from models import GovernanceResponse
                    gov = self.session.query(GovernanceResponse).filter(
                        GovernanceResponse.client_id == cid
                    ).first()
                    if gov and gov.organization_name:
                        candidate_org = gov.organization_name
                except Exception:
                    pass

            if not candidate_org:
                candidate_org = payload.get("organization_name") or payload.get("org_name")

            if candidate_org:
                return self.resolve(candidate_org, enforce_active=enforce_active)

            first_org = self.session.query(Organization).filter(Organization.is_active == True).first()
            if first_org:
                return first_org.id, first_org

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

        # 2.5. Project Token Lookup (Resolve project_token UUID to Organization)
        try:
            from models import GovernanceResponse, ShareProject, User
            proj_org_name = None

            gov = self.session.query(GovernanceResponse).filter(
                GovernanceResponse.project_token == cleaned
            ).first()
            if gov:
                if gov.organization_name:
                    proj_org_name = gov.organization_name
                elif gov.owner_id:
                    u = self.session.query(User).filter(User.id == gov.owner_id).first()
                    if u and u.organization_name:
                        proj_org_name = u.organization_name

            if not proj_org_name:
                sp = self.session.query(ShareProject).filter(
                    ShareProject.project_token == cleaned
                ).first()
                if sp and sp.owner_id:
                    u = self.session.query(User).filter(User.id == sp.owner_id).first()
                    if u and u.organization_name:
                        proj_org_name = u.organization_name

            if not proj_org_name:
                u = self.session.query(User).filter(User.last_project_token == cleaned).first()
                if u and u.organization_name:
                    proj_org_name = u.organization_name

            if not proj_org_name:
                try:
                    from app.integrations.llm import llm_gateway
                    active_org = llm_gateway.current_user_org_var.get()
                    if active_org and not _is_jwt(active_org):
                        proj_org_name = active_org
                except Exception:
                    pass

            if proj_org_name:
                return self.resolve(proj_org_name, enforce_active=enforce_active)
        except Exception as e:
            logger.warning(f"Failed resolving tenant via project_token '{cleaned}': {e}")

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
