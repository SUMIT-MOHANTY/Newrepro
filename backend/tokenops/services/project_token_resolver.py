import uuid
import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

def resolve_or_ensure_project_token(
    session: Session,
    user_id: Optional[int] = None,
    organization_name: Optional[str] = None,
    candidate_project_token: Optional[str] = None,
    candidate_project_name: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Guarantees that a valid, non-org-level project_token and project_name are returned.
    
    Prevents any AI consumption log or financial ledger record from ever being created
    at the organization level, with a null/empty project_token, or with a project_token
    equal to the organization name or ID.
    
    Resolution order:
      1. Validate candidate_project_token (ensure it is NOT the org name, org UUID, or empty).
         If valid, resolve project_name from DB if missing.
      2. If candidate is invalid or missing:
         a. If user_id provided: check user.last_project_token.
         b. Check user's most recent ShareProject or GovernanceResponse.
         c. Check organization's most recent ShareProject or GovernanceResponse.
         d. If no project exists for this organization: create an official ShareProject workspace.
      3. Update user.last_project_token if user_id is provided.
    """
    from models import User, GovernanceResponse, ShareProject
    from tokenops.models.token_wallet import OrganizationWallet

    canonical_org_name = (organization_name or "").strip()
    
    # Helper to check if a string matches any organization name or wallet ID
    def _is_org_identifier(val: Optional[str]) -> bool:
        if not val or not val.strip():
            return True
        v = val.strip().lower()
        if canonical_org_name and v == canonical_org_name.lower():
            return True
        
        # Check against OrganizationWallet table
        match = session.query(OrganizationWallet.id).filter(
            (func.lower(OrganizationWallet.organization_name) == v) |
            (OrganizationWallet.id == val.strip())
        ).first()
        return match is not None

    resolved_token = None
    resolved_name = candidate_project_name

    # Step 1: Check candidate token
    if candidate_project_token and not _is_org_identifier(candidate_project_token):
        clean_cand = candidate_project_token.strip()
        # Look up existing project name if missing
        gov = session.query(GovernanceResponse).filter(
            GovernanceResponse.project_token == clean_cand
        ).first()
        if gov:
            resolved_token = clean_cand
            resolved_name = resolved_name or gov.project_name
        else:
            sp = session.query(ShareProject).filter(
                ShareProject.project_token == clean_cand
            ).first()
            if sp:
                resolved_token = clean_cand
                resolved_name = resolved_name or sp.project_name
            else:
                # Valid token string that isn't in DB yet: auto-register so it has an auditable record
                resolved_token = clean_cand
                resolved_name = resolved_name or "Project Workspace"
                try:
                    new_sp = ShareProject(
                        project_token=resolved_token,
                        owner_id=user_id or 1,
                        project_name=resolved_name,
                        description="Auto-registered project workspace for AI tracking"
                    )
                    session.add(new_sp)
                    session.flush()
                except Exception as ex:
                    logger.debug(f"ShareProject auto-registration skipped: {ex}")

    # Step 2: Fallback resolution if candidate was missing or rejected
    user = None
    if user_id:
        try:
            user = session.query(User).filter(User.id == user_id).first()
        except Exception:
            user = None

    if not resolved_token and user:
        # 2a. Check user's last_project_token
        if user.last_project_token and not _is_org_identifier(user.last_project_token):
            lpt = user.last_project_token.strip()
            gov = session.query(GovernanceResponse).filter(
                GovernanceResponse.project_token == lpt
            ).first()
            if gov:
                resolved_token = lpt
                resolved_name = gov.project_name
            else:
                sp = session.query(ShareProject).filter(
                    ShareProject.project_token == lpt
                ).first()
                if sp:
                    resolved_token = lpt
                    resolved_name = sp.project_name

        # 2b. Check user's most recent projects
        if not resolved_token:
            sp = session.query(ShareProject).filter(
                ShareProject.owner_id == user.id,
                ShareProject.project_token != None
            ).order_by(ShareProject.created_at.desc()).first()
            if sp and not _is_org_identifier(sp.project_token):
                resolved_token = sp.project_token
                resolved_name = sp.project_name

        if not resolved_token:
            gov = session.query(GovernanceResponse).filter(
                GovernanceResponse.owner_id == user.id,
                GovernanceResponse.project_token != None
            ).order_by(GovernanceResponse.submission_date.desc()).first()
            if gov and not _is_org_identifier(gov.project_token):
                resolved_token = gov.project_token
                resolved_name = gov.project_name

        # Ensure canonical org name from user if missing
        if not canonical_org_name and user.organization_name:
            canonical_org_name = user.organization_name

    # 2c. Check organization's projects
    if not resolved_token and canonical_org_name:
        org_users = session.query(User.id).filter(
            func.lower(User.organization_name) == canonical_org_name.lower()
        ).all()
        org_user_ids = [u[0] for u in org_users]
        if org_user_ids:
            sp = session.query(ShareProject).filter(
                ShareProject.owner_id.in_(org_user_ids),
                ShareProject.project_token != None
            ).order_by(ShareProject.created_at.desc()).first()
            if sp and not _is_org_identifier(sp.project_token):
                resolved_token = sp.project_token
                resolved_name = sp.project_name

            if not resolved_token:
                gov = session.query(GovernanceResponse).filter(
                    GovernanceResponse.owner_id.in_(org_user_ids),
                    GovernanceResponse.project_token != None
                ).order_by(GovernanceResponse.submission_date.desc()).first()
                if gov and not _is_org_identifier(gov.project_token):
                    resolved_token = gov.project_token
                    resolved_name = gov.project_name

    # 2d. If no project exists for this organization: create an official ShareProject workspace
    if not resolved_token:
        org_display = canonical_org_name or "General"
        default_name = f"{org_display} Workspace"
        default_token = str(uuid.uuid4())
        owner_id_to_use = user_id or 1
        if user:
            owner_id_to_use = user.id
        else:
            first_user = session.query(User.id).first()
            if first_user:
                owner_id_to_use = first_user[0]

        new_sp = ShareProject(
            project_token=default_token,
            owner_id=owner_id_to_use,
            project_name=default_name,
            description=f"Default project workspace for {org_display}"
        )
        session.add(new_sp)
        session.flush()
        resolved_token = default_token
        resolved_name = default_name
        logger.info(f"Created default project workspace '{default_name}' (token: {default_token})")

    # Step 3: Update user's last_project_token if applicable
    if user and resolved_token and user.last_project_token != resolved_token:
        user.last_project_token = resolved_token
        session.flush()

    return str(resolved_token), str(resolved_name or "Workspace Project")
