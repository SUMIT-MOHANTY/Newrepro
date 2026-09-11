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
        from tokenops.models.token_wallet import UserOrganization, UserTokenWallet
        import models

        # 1. Resolve canonical tenant and org_id
        org_id = None
        canonical_name = organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            canonical_name = org.name
        except Exception:
            pass

        # 2. Query users belonging to this organization across all membership models:
        # A. Core User records with matching organization_name
        org_users = self.session.query(models.User).filter(
            (func.lower(models.User.organization_name) == canonical_name.lower()) |
            (func.lower(models.User.organization_name) == organization_name.lower())
        ).all()

        # B. UserOrganizationRole records (primary DSuite RBAC mapping)
        role_mappings = self.session.query(models.UserOrganizationRole).filter(
            (func.lower(models.UserOrganizationRole.organization_name) == canonical_name.lower()) |
            (func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower())
        ).all()

        # C. UserOrganization memberships in tokenops
        memberships_query = self.session.query(UserOrganization).filter(
            (func.lower(UserOrganization.organization_name) == canonical_name.lower()) |
            (func.lower(UserOrganization.organization_name) == organization_name.lower())
        )
        if org_id:
            memberships_query = self.session.query(UserOrganization).filter(
                (func.lower(UserOrganization.organization_name) == canonical_name.lower()) |
                (func.lower(UserOrganization.organization_name) == organization_name.lower()) |
                (UserOrganization.organization_id == org_id)
            )
        memberships = memberships_query.all()
        member_dict = {m.user_id: m for m in memberships}

        # D. UserTokenWallet records
        wallets_query = self.session.query(UserTokenWallet).filter(
            (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
            (func.lower(UserTokenWallet.organization_name) == organization_name.lower())
        )
        if org_id:
            wallets_query = self.session.query(UserTokenWallet).filter(
                (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
                (func.lower(UserTokenWallet.organization_name) == organization_name.lower()) |
                (UserTokenWallet.organization_id == org_id)
            )
        existing_wallets = wallets_query.all()
        wallets_by_user = {w.user_id: w for w in existing_wallets}

        # Collect all unique user IDs
        all_user_ids = set()
        all_user_ids.update([u.id for u in org_users])
        all_user_ids.update([m.user_id for m in role_mappings])
        all_user_ids.update([m.user_id for m in memberships])
        all_user_ids.update([w.user_id for w in existing_wallets])

        # Load User objects for all discovered user IDs
        all_users = self.session.query(models.User).filter(models.User.id.in_(all_user_ids)).all() if all_user_ids else []
        user_dict = {u.id: u for u in all_users}

        # Load role names for role_mappings
        role_ids = [m.role_id for m in role_mappings if m.role_id]
        role_names_by_id = {}
        if role_ids:
            roles = self.session.query(models.OrganizationRole).filter(models.OrganizationRole.id.in_(role_ids)).all()
            role_names_by_id = {r.id: r.name for r in roles}

        user_role_map = {}
        for m in role_mappings:
            if m.role_id in role_names_by_id:
                user_role_map[m.user_id] = role_names_by_id[m.role_id]

        # Build combined user map
        all_user_map = {}
        for uid in all_user_ids:
            u = user_dict.get(uid)
            if not u:
                continue

            role = "MEMBER"
            if getattr(u, "is_super_admin", False):
                role = "SUPER_ADMIN"
            elif getattr(u, "is_org_admin", False):
                role = "ORG_ADMIN"
            elif uid in user_role_map and user_role_map[uid]:
                role = user_role_map[uid].upper()
            elif uid in member_dict and member_dict[uid].role:
                role = member_dict[uid].role.upper()

            is_active = True
            if uid in member_dict:
                is_active = member_dict[uid].is_active

            all_user_map[uid] = {
                "user": u,
                "role": role,
                "is_active": is_active
            }

        # Ensure all users have a UserTokenWallet and UserOrganization membership
        flushed = False
        for uid in all_user_ids:
            if uid not in wallets_by_user:
                new_w = UserTokenWallet(
                    user_id=uid,
                    organization_name=canonical_name,
                    organization_id=org_id or "00000000-0000-0000-0000-000000000000",
                    allocated_tokens=0,
                    consumed_tokens=0,
                    remaining_tokens=0,
                    is_blocked=False
                )
                self.session.add(new_w)
                wallets_by_user[uid] = new_w
                flushed = True

            if uid not in member_dict and uid in all_user_map:
                new_m = UserOrganization(
                    user_id=uid,
                    organization_name=canonical_name,
                    organization_id=org_id or "00000000-0000-0000-0000-000000000000",
                    role=all_user_map[uid]["role"].lower(),
                    is_active=all_user_map[uid]["is_active"]
                )
                self.session.add(new_m)
                member_dict[uid] = new_m
                flushed = True

        if flushed:
            self.session.flush()

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
        org_id = None
        canonical_name = organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            canonical_name = org.name
        except Exception:
            pass

        query = self.session.query(UserTokenWallet).filter(UserTokenWallet.user_id == user_id)
        if org_id:
            w = query.filter(
                (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
                (func.lower(UserTokenWallet.organization_name) == organization_name.lower()) |
                (UserTokenWallet.organization_id == org_id)
            ).first()
        else:
            w = query.filter(
                (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
                (func.lower(UserTokenWallet.organization_name) == organization_name.lower())
            ).first()

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
        org_id = None
        canonical_name = organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            canonical_name = org.name
        except Exception:
            pass

        wallet = self.org_repo.get_by_organization(organization_name)
        if not wallet and canonical_name:
            wallet = self.org_repo.get_by_organization(canonical_name)
        if not wallet:
            wallet = self.org_repo.get_or_create(canonical_name or organization_name)
            
        # Reconcile approved tokens from approved TokenQuotaRequest & TokenTransactionLedger
        from tokenops.models.quota_request import TokenQuotaRequest, QuotaRequestStatus, QuotaRequestType
        approved_tokens_query = self.session.query(func.sum(TokenQuotaRequest.requested_tokens)).filter(
            (func.lower(TokenQuotaRequest.organization_name) == canonical_name.lower()) |
            (func.lower(TokenQuotaRequest.organization_name) == organization_name.lower()) |
            (TokenQuotaRequest.organization_id == org_id),
            TokenQuotaRequest.status.in_([QuotaRequestStatus.APPROVED, QuotaRequestStatus.APPROVED.value]),
            TokenQuotaRequest.request_type.in_([QuotaRequestType.TOKEN_INCREASE, QuotaRequestType.TOKEN_INCREASE.value])
        ).scalar() or 0

        from tokenops.models.ledger import TokenTransactionLedger, TransactionType
        ledger_tokens_query = self.session.query(func.sum(TokenTransactionLedger.token_delta)).filter(
            (func.lower(TokenTransactionLedger.organization_name) == canonical_name.lower()) |
            (func.lower(TokenTransactionLedger.organization_name) == organization_name.lower()) |
            (TokenTransactionLedger.organization_id == org_id),
            TokenTransactionLedger.transaction_type.in_([TransactionType.PURCHASE.value, "PURCHASE"])
        ).scalar() or 0

        total_approved = max(approved_tokens_query, ledger_tokens_query)

        # Calculate allocated tokens by summing up all UserTokenWallet allocated_tokens for this org
        allocated = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter(
            (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
            (func.lower(UserTokenWallet.organization_name) == organization_name.lower()) |
            (UserTokenWallet.organization_id == org_id)
        ).scalar() or 0

        # Calculate consumed tokens from UserTokenWallet allocations or OrganizationUsageSummary
        consumed = self.session.query(func.sum(UserTokenWallet.consumed_tokens)).filter(
            (func.lower(UserTokenWallet.organization_name) == canonical_name.lower()) |
            (func.lower(UserTokenWallet.organization_name) == organization_name.lower()) |
            (UserTokenWallet.organization_id == org_id)
        ).scalar() or 0
        if consumed == 0:
            from tokenops.models.summary import OrganizationUsageSummary
            usage = self.session.query(OrganizationUsageSummary).filter(
                (func.lower(OrganizationUsageSummary.organization_name) == canonical_name.lower()) |
                (func.lower(OrganizationUsageSummary.organization_name) == organization_name.lower()) |
                (OrganizationUsageSummary.organization_id == org_id)
            ).first()
            if usage:
                consumed = usage.total_tokens or 0

        # Auto-heal: If approved tokens exist and exceed wallet.purchased_tokens, update wallet
        modified = False
        if total_approved > (wallet.purchased_tokens or 0):
            wallet.purchased_tokens = total_approved
            modified = True

        expected_reserve = max(0, (wallet.purchased_tokens or 0) - allocated)
        expected_remaining = max(0, (wallet.purchased_tokens or 0) - consumed)

        if wallet.reserved_tokens != expected_reserve:
            wallet.reserved_tokens = expected_reserve
            modified = True
        if wallet.remaining_tokens != expected_remaining:
            wallet.remaining_tokens = expected_remaining
            modified = True

        if modified:
            self.session.add(wallet)
            self.session.flush()

        reference_price = float(self.pricing_service.get_price(settings.ai_model))

        return ReserveWalletView(
            organization_name=canonical_name,
            purchased_tokens=wallet.purchased_tokens,
            reserved_tokens=wallet.reserved_tokens,
            allocated_tokens=allocated,
            consumed_tokens=consumed,
            remaining_tokens=wallet.remaining_tokens,
            reference_price=reference_price,
            payg_enabled=bool(wallet.payg_enabled),
            payg_soft_limit_usd=float(wallet.payg_soft_limit_usd) if wallet.payg_soft_limit_usd is not None else None,
            payg_hard_limit_usd=float(wallet.payg_hard_limit_usd) if wallet.payg_hard_limit_usd is not None else None,
            payg_current_spend_usd=float(wallet.payg_current_spend_usd or 0.0)
        )

    def allocate_tokens(self, admin_user_id: int, organization_name: str, request_id: str, user_id: int, token_amount: int, remarks: str = None):
        with self._tx():
            state = self.wallet_service.allocate_tokens(
                user_id=user_id,
                organization_name=organization_name,
                amount=token_amount,
                request_id=request_id
            )
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
        with self._tx():
            state = self.wallet_service.reallocate_tokens(
                from_user_id=source_user_id,
                to_user_id=destination_user_id,
                organization_name=organization_name,
                amount=token_amount,
                request_id=request_id
            )
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
        with self._tx():
            state = self.wallet_service.revoke_tokens(
                user_id=user_id,
                organization_name=organization_name,
                amount=token_amount,
                request_id=request_id
            )
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="REVOKE_TOKENS",
                target_entity=str(user_id),
                request_id=request_id,
                details={"token_amount": token_amount}
            )
            return state
