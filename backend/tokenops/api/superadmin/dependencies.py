from fastapi import Depends, HTTPException, status
from auth import get_current_user
from models import User
from database import get_db
from sqlalchemy.orm import Session
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.repositories.usage_summary import UsageSummaryRepository
from tokenops.repositories.pricing import PricingRepository
from tokenops.services.admin.admin_wallet_service import AdminWalletService
from tokenops.services.admin.admin_governance_service import AdminGovernanceService
from tokenops.services.admin.admin_pricing_service import AdminPricingService
from tokenops.services.admin.admin_analytics_service import AdminAnalyticsService
from tokenops.services.wallet_service import WalletService
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.repositories.ledger import LedgerRepository
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.repositories.idempotency import IdempotencyRepository
from tokenops.services.pricing_service import PricingService
from tokenops.services.payg_invoice_service import PAYGInvoiceService

async def verify_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that enforces Super Admin RBAC.
    """
    if not bool(getattr(current_user, "is_super_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="INSUFFICIENT_PRIVILEGES"
        )
    return current_user

def get_admin_audit_service(db: Session = Depends(get_db)) -> AdminAuditService:
    return AdminAuditService(session=db)

def get_admin_wallet_service(
    db: Session = Depends(get_db),
    audit_service: AdminAuditService = Depends(get_admin_audit_service)
) -> AdminWalletService:
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
    return AdminWalletService(db, wallet_service, audit_service, org_repo, pricing_service)

def get_admin_governance_service(
    db: Session = Depends(get_db),
    audit_service: AdminAuditService = Depends(get_admin_audit_service)
) -> AdminGovernanceService:
    org_repo = OrganizationWalletRepository(db)
    user_repo = UserWalletRepository(db)
    validation = ValidationService(org_repo, user_repo)
    ledger_repo = LedgerRepository(db)
    ledger = LedgerService(ledger_repo)
    idempotency_repo = IdempotencyRepository(db)
    idempotency = IdempotencyService(idempotency_repo)
    wallet_service = WalletService(db, org_repo, user_repo, validation, ledger, idempotency)
    return AdminGovernanceService(db, audit_service, org_repo, user_repo, wallet_service)

def get_admin_pricing_service(
    db: Session = Depends(get_db),
    audit_service: AdminAuditService = Depends(get_admin_audit_service)
) -> AdminPricingService:
    pricing_repo = PricingRepository(db)
    return AdminPricingService(db, audit_service, pricing_repo)

def get_admin_analytics_service(
    db: Session = Depends(get_db)
) -> AdminAnalyticsService:
    return AdminAnalyticsService(db)

def get_payg_invoice_service(
    db: Session = Depends(get_db)
) -> PAYGInvoiceService:
    from tokenops.services.payg_invoice_service import PAYGInvoiceService
    pricing_repo = PricingRepository(db)
    pricing_service = PricingService(pricing_repo)
    return PAYGInvoiceService(db, pricing_service)
