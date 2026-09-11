from fastapi import Depends, HTTPException, status, Header
from auth import get_current_user
from models import User, UserOrganizationRole, OrganizationRole
from database import get_db
from sqlalchemy.orm import Session
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from tokenops.services.org_admin.org_governance_service import OrgGovernanceService
from tokenops.services.org_admin.org_analytics_service import OrgAnalyticsService
from tokenops.services.wallet_service import WalletService
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.repositories.ledger import LedgerRepository
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.repositories.idempotency import IdempotencyRepository
from tokenops.services.pricing_service import PricingService
from tokenops.repositories.pricing import PricingRepository
from typing import Optional

async def get_active_organization(
    x_organization: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> str:
    # If the app relies on a header, use it. Otherwise fallback to current_user.organization_name
    org = x_organization or getattr(current_user, "organization_name", None)
    if not org:
        # Fallback to UserOrganizationRole
        uor = db.query(UserOrganizationRole).filter(UserOrganizationRole.user_id == current_user.id).first()
        if uor and uor.organization_name:
            org = uor.organization_name

    if not org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active organization not specified in context."
        )
    return org

async def verify_org_admin(
    active_organization: str = Depends(get_active_organization),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency that enforces Organization Admin RBAC.
    """
    # 1. Fetch the user's role mapping in the active organization
    from sqlalchemy import func
    mapping = db.query(UserOrganizationRole).join(OrganizationRole).filter(
        UserOrganizationRole.user_id == current_user.id,
        func.lower(UserOrganizationRole.organization_name) == active_organization.lower(),
        OrganizationRole.name.in_(["ORG_ADMIN", "Admin", "admin"])
    ).first()
    
    is_legacy_admin = bool(
        getattr(current_user, "organization_name", None) and 
        current_user.organization_name.lower() == active_organization.lower() and 
        getattr(current_user, "is_org_admin", False)
    )
    
    is_admin = bool(mapping or is_legacy_admin or getattr(current_user, "is_super_admin", False))
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="INSUFFICIENT_PRIVILEGES"
        )
        
    # We could attach active_organization to the current_user object dynamically 
    # to be used by the route handlers without depending on get_active_organization again.
    setattr(current_user, "active_organization", active_organization)
    
    return current_user

def get_org_audit_service(db: Session = Depends(get_db)) -> OrgAuditService:
    return OrgAuditService(session=db)

def get_org_wallet_service(
    db: Session = Depends(get_db),
    audit_service: OrgAuditService = Depends(get_org_audit_service)
) -> OrgWalletService:
    org_repo = OrganizationWalletRepository(db)
    user_repo = UserWalletRepository(db)
    validation = ValidationService(org_repo, user_repo)
    ledger_repo = LedgerRepository(db)
    ledger = LedgerService(ledger_repo)
    idempotency_repo = IdempotencyRepository(db)
    idempotency = IdempotencyService(idempotency_repo)
    pricing_repo = PricingRepository(db)
    pricing_service = PricingService(pricing_repo)
    
    wallet_service = WalletService(db, org_repo, user_repo, validation, ledger, idempotency)
    return OrgWalletService(db, wallet_service, audit_service, org_repo, user_repo, pricing_service)

def get_org_governance_service(
    db: Session = Depends(get_db),
    audit_service: OrgAuditService = Depends(get_org_audit_service)
) -> OrgGovernanceService:
    return OrgGovernanceService(db, audit_service)

def get_org_analytics_service(
    db: Session = Depends(get_db)
) -> OrgAnalyticsService:
    return OrgAnalyticsService(db)
