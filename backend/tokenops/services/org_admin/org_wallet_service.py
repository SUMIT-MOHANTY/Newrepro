from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.services.wallet_service import WalletService
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.services.pricing_service import PricingService
from config import settings
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
        user_repo: UserWalletRepository,
        pricing_service: PricingService
    ):
        self.session = session
        self.wallet_service = wallet_service
        self.audit_service = audit_service
        self.org_repo = org_repo
        self.user_repo = user_repo
        self.pricing_service = pricing_service

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

    def get_users(self, organization_name: str, page: int = 1, size: int = 50, search: str = None) -> PaginatedUserWalletResponse:
        from tokenops.models.token_wallet import UserOrganization
        import models

        # 1. Query all users belonging to this organization from users table and UserOrganization
        org_users = self.session.query(models.User).filter(
            func.lower(models.User.organization_name) == organization_name.lower()
        ).all()

        memberships = self.session.query(UserOrganization).filter(
            func.lower(UserOrganization.organization_name) == organization_name.lower()
        ).all()
        
        member_dict = {m.user_id: m for m in memberships}

        # Build combined map of users
        all_user_map = {}
        for u in org_users:
            all_user_map[u.id] = {
                "user": u,
                "role": member_dict[u.id].role if u.id in member_dict else ("ORG_ADMIN" if u.is_org_admin else "member"),
                "is_active": member_dict[u.id].is_active if u.id in member_dict else True
            }

        for m in memberships:
            if m.user_id not in all_user_map:
                u = self.session.query(models.User).filter(models.User.id == m.user_id).first()
                if u:
                    all_user_map[u.id] = {
                        "user": u,
                        "role": m.role,
                        "is_active": m.is_active
                    }

        user_ids = list(all_user_map.keys())
        wallets_by_user = {}
        if user_ids:
            wallets = self.session.query(UserTokenWallet).filter(
                func.lower(UserTokenWallet.organization_name) == organization_name.lower(),
                UserTokenWallet.user_id.in_(user_ids)
            ).all()
            wallets_by_user = {w.user_id: w for w in wallets}

        reference_price = float(self.pricing_service.get_price(settings.ai_model))

        items = []
        for uid, info in all_user_map.items():
            u = info["user"]
            name_parts = [getattr(u, "first_name", None) or "", getattr(u, "last_name", None) or ""]
            full_name = " ".join([p for p in name_parts if p]).strip() or getattr(u, "username", None) or (u.email.split("@")[0] if getattr(u, "email", None) else f"User {uid}")

            if search:
                s = search.lower()
                if s not in (u.email or "").lower() and s not in full_name.lower():
                    continue

            w = wallets_by_user.get(uid)
            items.append(
                UserWalletView(
                    user_id=uid,
                    email=u.email,
                    name=full_name,
                    role=info["role"],
                    allocated_tokens=w.allocated_tokens if w else 0,
                    consumed_tokens=w.consumed_tokens if w else 0,
                    remaining_tokens=w.remaining_tokens if w else 0,
                    is_blocked=w.is_blocked if w else (not info["is_active"]),
                    reference_price=reference_price
                )
            )

        # Sort by user_id
        items.sort(key=lambda x: x.user_id)
        total = len(items)
        offset = (page - 1) * size
        paged_items = items[offset:offset + size]

        return PaginatedUserWalletResponse(
            items=paged_items,
            total=total,
            page=page,
            size=size
        )

    def get_user(self, organization_name: str, user_id: int) -> UserWalletView:
        w = self.session.query(UserTokenWallet).filter_by(organization_name=organization_name, user_id=user_id).first()
        if not w:
            return None
            
        reference_price = float(self.pricing_service.get_price(settings.ai_model))
            
        return UserWalletView(
            user_id=w.user_id,
            allocated_tokens=w.allocated_tokens,
            consumed_tokens=w.consumed_tokens,
            remaining_tokens=w.remaining_tokens,
            is_blocked=w.is_blocked,
            reference_price=reference_price
        )

    def get_reserve(self, organization_name: str) -> ReserveWalletView:
        wallet = self.org_repo.get_by_organization(organization_name)
        if not wallet:
            return None
            
        # Calculate allocated tokens by summing up all UserTokenWallet allocated_tokens for this org
        allocated = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter_by(
            organization_name=organization_name
        ).scalar() or 0

        # Calculate consumed tokens from UserTokenWallet allocations or OrganizationUsageSummary
        consumed = self.session.query(func.sum(UserTokenWallet.consumed_tokens)).filter_by(
            organization_name=organization_name
        ).scalar() or 0
        if consumed == 0:
            from tokenops.models.summary import OrganizationUsageSummary
            usage = self.session.query(OrganizationUsageSummary).filter_by(
                organization_name=organization_name
            ).first()
            if usage:
                consumed = usage.total_tokens or 0

        reference_price = float(self.pricing_service.get_price(settings.ai_model))

        return ReserveWalletView(
            organization_name=organization_name,
            purchased_tokens=wallet.purchased_tokens,
            reserved_tokens=wallet.reserved_tokens,
            allocated_tokens=allocated,
            consumed_tokens=consumed,
            remaining_tokens=wallet.remaining_tokens,
            reference_price=reference_price
        )

    def allocate_tokens(self, admin_user_id: int, organization_name: str, request_id: str, user_id: int, token_amount: int, remarks: str = None):
        state = self.wallet_service.allocate_tokens(
            user_id=user_id,
            organization_name=organization_name,
            amount=token_amount,
            request_id=request_id
        )
        
        with self._tx():
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
        
        with self._tx():
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
        
        with self._tx():
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="REVOKE_TOKENS",
                target_entity=str(user_id),
                request_id=request_id,
                details={"token_amount": token_amount}
            )
        return state
