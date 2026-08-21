from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.services.wallet_service import WalletService
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.models.token_wallet import UserTokenWallet, OrganizationWallet
from tokenops.schemas.orgadmin import (
    UserWalletView, PaginatedUserWalletResponse, ReserveWalletView
)

class OrgWalletService:
    def __init__(
        self,
        session: Session,
        wallet_service: WalletService,
        audit_service: OrgAuditService,
        org_repo: OrganizationWalletRepository,
        user_repo: UserWalletRepository
    ):
        self.session = session
        self.wallet_service = wallet_service
        self.audit_service = audit_service
        self.org_repo = org_repo
        self.user_repo = user_repo

    def get_users(self, organization_name: str, page: int = 1, size: int = 50, search: str = None) -> PaginatedUserWalletResponse:
        query = self.session.query(UserTokenWallet).filter(UserTokenWallet.organization_name == organization_name)
        
        # We can join with User if we wanted to search by email, but keeping it simple for now based on wallet fields
        # If we need to search, typically we'd join with User model and filter by User.email.
        
        total = query.count()
        offset = (page - 1) * size
        user_wallets = query.order_by(UserTokenWallet.user_id).offset(offset).limit(size).all()
        
        items = [
            UserWalletView(
                user_id=w.user_id,
                allocated_tokens=w.allocated_tokens,
                consumed_tokens=w.consumed_tokens,
                remaining_tokens=w.remaining_tokens,
                is_blocked=w.is_blocked
            ) for w in user_wallets
        ]
        
        return PaginatedUserWalletResponse(
            items=items,
            total=total,
            page=page,
            size=size
        )

    def get_user(self, organization_name: str, user_id: int) -> UserWalletView:
        w = self.session.query(UserTokenWallet).filter_by(organization_name=organization_name, user_id=user_id).first()
        if not w:
            return None
            
        return UserWalletView(
            user_id=w.user_id,
            allocated_tokens=w.allocated_tokens,
            consumed_tokens=w.consumed_tokens,
            remaining_tokens=w.remaining_tokens,
            is_blocked=w.is_blocked
        )

    def get_reserve(self, organization_name: str) -> ReserveWalletView:
        wallet = self.org_repo.get_by_organization(organization_name)
        if not wallet:
            return None
            
        # Calculate allocated tokens by summing up all UserTokenWallet allocated_tokens for this org
        allocated = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter_by(
            organization_name=organization_name
        ).scalar() or 0
        
        return ReserveWalletView(
            organization_name=organization_name,
            purchased_tokens=wallet.purchased_tokens,
            reserved_tokens=wallet.reserved_tokens,
            allocated_tokens=allocated,
            consumed_tokens=wallet.consumed_tokens,
            remaining_tokens=wallet.remaining_tokens
        )

    def allocate_tokens(self, admin_user_id: int, organization_name: str, request_id: str, user_id: int, token_amount: int, remarks: str = None):
        state = self.wallet_service.allocate_tokens(
            user_id=user_id,
            organization_name=organization_name,
            amount=token_amount,
            request_id=request_id
        )
        
        with self.session.begin():
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="ALLOCATE_TOKENS",
                target_entity=str(user_id),
                request_id=request_id,
                details={"token_amount": token_amount, "remarks": remarks}
            )
        return state

    def reallocate_tokens(self, admin_user_id: int, organization_name: str, request_id: str, source_user_id: int, destination_user_id: int, token_amount: int):
        state = self.wallet_service.reallocate_tokens(
            from_user_id=source_user_id,
            to_user_id=destination_user_id,
            organization_name=organization_name,
            amount=token_amount,
            request_id=request_id
        )
        
        with self.session.begin():
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="REALLOCATE_TOKENS",
                target_entity=f"{source_user_id}->{destination_user_id}",
                request_id=request_id,
                details={"token_amount": token_amount}
            )
        return state

    def revoke_tokens(self, admin_user_id: int, organization_name: str, request_id: str, user_id: int, token_amount: int):
        state = self.wallet_service.revoke_tokens(
            user_id=user_id,
            organization_name=organization_name,
            amount=token_amount,
            request_id=request_id
        )
        
        with self.session.begin():
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="REVOKE_TOKENS",
                target_entity=str(user_id),
                request_id=request_id,
                details={"token_amount": token_amount}
            )
        return state
