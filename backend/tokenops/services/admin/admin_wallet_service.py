from typing import List, Tuple
from sqlalchemy.orm import Session
from tokenops.services.wallet_service import WalletService
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.models.token_wallet import OrganizationWallet
from tokenops.schemas.superadmin import OrganizationWalletView, PaginatedOrganizationResponse

class AdminWalletService:
    def __init__(
        self,
        session: Session,
        wallet_service: WalletService,
        audit_service: AdminAuditService,
        org_repo: OrganizationWalletRepository
    ):
        self.session = session
        self.wallet_service = wallet_service
        self.audit_service = audit_service
        self.org_repo = org_repo

    def get_organizations(self, page: int = 1, size: int = 50, search: str = None) -> PaginatedOrganizationResponse:
        """
        Get paginated list of organizations.
        """
        query = self.session.query(OrganizationWallet)
        
        if search:
            query = query.filter(OrganizationWallet.organization_name.ilike(f"%{search}%"))
            
        total = query.count()
        
        offset = (page - 1) * size
        wallets = query.order_by(OrganizationWallet.organization_name).offset(offset).limit(size).all()
        
        items = [
            OrganizationWalletView(
                organization_name=w.organization_name,
                purchased_tokens=w.purchased_tokens,
                consumed_tokens=w.consumed_tokens,
                reserved_tokens=w.reserved_tokens,
                remaining_tokens=w.remaining_tokens,
                payg_enabled=w.payg_enabled,
                is_blocked=w.is_blocked
            ) for w in wallets
        ]
        
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
        if not w:
            return None
            
        return OrganizationWalletView(
            organization_name=w.organization_name,
            purchased_tokens=w.purchased_tokens,
            consumed_tokens=w.consumed_tokens,
            reserved_tokens=w.reserved_tokens,
            remaining_tokens=w.remaining_tokens,
            payg_enabled=w.payg_enabled,
            is_blocked=w.is_blocked
        )

    def purchase_tokens(self, admin_user_id: int, organization_name: str, token_amount: int, remarks: str = None) -> OrganizationWalletView:
        """
        Purchase prepaid tokens for an organization.
        """
        # We reuse the existing WalletService to perform the transaction.
        # But we create an audit log.
        # Note: wallet_service.purchase_tokens should commit internally, or we wrap it in a transaction if needed.
        # Looking at WalletService, it uses @retry_on_lock and creates a transaction.
        self.wallet_service.purchase_tokens(
            organization_name=organization_name,
            token_amount=token_amount,
            user_id=admin_user_id,
            remarks=remarks
        )
        
        # Then we create an audit entry
        with self.session.begin():
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="PURCHASE_TOKENS",
                target_entity=organization_name,
                details={"token_amount": token_amount, "remarks": remarks}
            )
            
        return self.get_organization(organization_name)
