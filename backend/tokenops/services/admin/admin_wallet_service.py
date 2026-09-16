from typing import List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.services.wallet_service import WalletService
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.services.pricing_service import PricingService
from tokenops.models.token_wallet import OrganizationWallet, UserTokenWallet
from tokenops.schemas.superadmin import OrganizationWalletView, PaginatedOrganizationResponse

from tokenops.models.organization import Organization
from tokenops.utils.retry import retry_on_lock
from config import settings

class AdminWalletService:
    def __init__(
        self,
        session: Session,
        wallet_service: WalletService,
        audit_service: AdminAuditService,
        org_repo: OrganizationWalletRepository,
        pricing_service: PricingService
    ):
        self.session = session
        self.wallet_service = wallet_service
        self.audit_service = audit_service
        self.org_repo = org_repo
        self.pricing_service = pricing_service

    def get_organizations(self, page: int = 1, size: int = 50, search: str = None) -> PaginatedOrganizationResponse:
        """
        Get paginated list of all organizations in the platform with their token wallet status.
        """
        org_query = self.session.query(Organization)
        
        if search:
            org_query = org_query.filter(Organization.name.ilike(f"%{search}%"))
            
        total = org_query.count()
        offset = (page - 1) * size
        orgs = org_query.order_by(Organization.name).offset(offset).limit(size).all()
        
        reference_price = float(self.pricing_service.get_price(settings.ai_model))
        
        items = []
        for org in orgs:
            w = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.organization_name == org.name) |
                (OrganizationWallet.id == org.id)
            ).first()
            if w:
                consumed = self.session.query(func.sum(UserTokenWallet.consumed_tokens)).filter(
                    func.lower(UserTokenWallet.organization_name) == org.name.lower()
                ).scalar() or 0
                items.append(OrganizationWalletView(
                    organization_name=org.name,
                    purchased_tokens=w.purchased_tokens or 0,
                    consumed_tokens=consumed,
                    reserved_tokens=w.reserved_tokens or 0,
                    remaining_tokens=w.remaining_tokens or 0,
                    payg_enabled=bool(w.payg_enabled),
                    is_blocked=bool(w.is_blocked),
                    reference_price=reference_price,
                    payg_grace_period_months=getattr(w, "payg_grace_period_months", 3),
                    payg_current_spend_usd=float(w.payg_current_spend_usd or 0.0),
                    payg_reserved_spend_usd=float(w.payg_reserved_spend_usd or 0.0),
                    payg_soft_limit_usd=float(w.payg_soft_limit_usd) if w.payg_soft_limit_usd is not None else None,
                    payg_hard_limit_usd=float(w.payg_hard_limit_usd) if w.payg_hard_limit_usd is not None else None,
                    payg_billing_email=w.payg_billing_email
                ))
            else:
                items.append(OrganizationWalletView(
                    organization_name=org.name,
                    purchased_tokens=0,
                    consumed_tokens=0,
                    reserved_tokens=0,
                    remaining_tokens=0,
                    payg_enabled=False,
                    is_blocked=False,
                    reference_price=reference_price,
                    payg_grace_period_months=3,
                    payg_current_spend_usd=0.0,
                    payg_reserved_spend_usd=0.0,
                    payg_soft_limit_usd=None,
                    payg_hard_limit_usd=None,
                    payg_billing_email=None
                ))
        
        return PaginatedOrganizationResponse(
            items=items,
            total=total,
            page=page,
            size=size
        )

    def get_organization(self, organization_name: str) -> OrganizationWalletView:
        """
        Get a specific organization wallet.
        """
        w = self.org_repo.get_by_organization(organization_name)
        reference_price = float(self.pricing_service.get_price(settings.ai_model))
        
        if not w:
            return OrganizationWalletView(
                organization_name=organization_name,
                purchased_tokens=0,
                consumed_tokens=0,
                reserved_tokens=0,
                remaining_tokens=0,
                payg_enabled=False,
                is_blocked=False,
                reference_price=reference_price,
                payg_grace_period_months=3,
                payg_current_spend_usd=0.0,
                payg_reserved_spend_usd=0.0,
                payg_soft_limit_usd=None,
                payg_hard_limit_usd=None,
                payg_billing_email=None
            )
            
        consumed = self.session.query(func.sum(UserTokenWallet.consumed_tokens)).filter(
            func.lower(UserTokenWallet.organization_name) == organization_name.lower()
        ).scalar() or 0
        return OrganizationWalletView(
            organization_name=w.organization_name,
            purchased_tokens=w.purchased_tokens or 0,
            consumed_tokens=consumed,
            reserved_tokens=w.reserved_tokens or 0,
            remaining_tokens=w.remaining_tokens or 0,
            payg_enabled=bool(w.payg_enabled),
            is_blocked=bool(w.is_blocked),
            reference_price=reference_price,
            payg_grace_period_months=getattr(w, "payg_grace_period_months", 3),
            payg_current_spend_usd=float(w.payg_current_spend_usd or 0.0),
            payg_reserved_spend_usd=float(w.payg_reserved_spend_usd or 0.0),
            payg_soft_limit_usd=float(w.payg_soft_limit_usd) if w.payg_soft_limit_usd is not None else None,
            payg_hard_limit_usd=float(w.payg_hard_limit_usd) if w.payg_hard_limit_usd is not None else None,
            payg_billing_email=w.payg_billing_email
        )

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

    @retry_on_lock(max_retries=5)
    def purchase_tokens(self, admin_user_id: int, organization_name: str, token_amount: int, remarks: str = None) -> OrganizationWalletView:
        """
        Purchase prepaid tokens for an organization.
        Atomically executes financial mutation, ledger entry, and audit log.
        """
        with self._tx():
            self.wallet_service.purchase_tokens(
                organization_name=organization_name,
                amount=token_amount,
                remarks=remarks
            )
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="PURCHASE_TOKENS",
                target_entity=organization_name,
                details={"token_amount": token_amount, "remarks": remarks}
            )
            
        return self.get_organization(organization_name)

    def set_grace_period(self, admin_user_id: int, organization_name: str, grace_period_months: int) -> OrganizationWalletView:
        if grace_period_months < 0:
            raise ValueError("Grace period must be a non-negative integer")
            
        w = self.org_repo.get_or_create(organization_name)
        w.payg_grace_period_months = grace_period_months
        self.session.commit()
        
        try:
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="SET_PAYG_GRACE_PERIOD",
                target_entity=organization_name,
                details={"grace_period_months": grace_period_months}
            )
            self.session.commit()
        except Exception:
            pass
            
        return self.get_organization(organization_name)

    def bulk_set_grace_period(self, admin_user_id: int, grace_period_months: int) -> None:
        if grace_period_months < 0:
            raise ValueError("Grace period must be a non-negative integer")
            
        # Update all wallets
        self.session.query(OrganizationWallet).update({
            OrganizationWallet.payg_grace_period_months: grace_period_months
        })
        self.session.commit()
        
        try:
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="BULK_SET_PAYG_GRACE_PERIOD",
                target_entity="ALL_ORGANIZATIONS",
                details={"grace_period_months": grace_period_months}
            )
            self.session.commit()
        except Exception:
            pass
