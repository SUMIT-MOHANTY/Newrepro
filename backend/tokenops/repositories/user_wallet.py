from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.models import UserTokenWallet, UserOrganization

class UserWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def _resolve_tenant(self, organization_name: str) -> tuple[str | None, str]:
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            return org_id, org.name
        except Exception:
            return None, organization_name

    def get_membership(self, user_id: int, organization_name: str) -> UserOrganization | None:
        org_id, canonical_name = self._resolve_tenant(organization_name)
        if org_id:
            membership = self.session.query(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == org_id
            ).first()
            if membership:
                # Auto-heal: ensure organization_id is set
                if not membership.organization_id:
                    membership.organization_id = org_id
                return membership

        # Fallback to name check
        membership = self.session.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            func.lower(UserOrganization.organization_name) == canonical_name.lower()
        ).first()
        if membership and org_id:
            # Auto-heal
            membership.organization_id = org_id
            return membership

        # --- LAZY CREATION/AUTO-HEAL ---
        # If user is in core DB and their org name matches (case insensitive), auto-create membership
        try:
            from models import User
            core_user = self.session.query(User).filter(User.id == user_id).first()
            if core_user and core_user.organization_name and core_user.organization_name.lower() == canonical_name.lower():
                membership = UserOrganization(
                    user_id=user_id,
                    organization_id=org_id or "00000000-0000-0000-0000-000000000000",
                    organization_name=core_user.organization_name,
                    is_active=True
                )
                self.session.add(membership)
                self.session.flush()
                return membership
        except Exception:
            pass

        return None

    def get_user_wallet(self, user_id: int, organization_name: str) -> UserTokenWallet | None:
        org_id, canonical_name = self._resolve_tenant(organization_name)
        if org_id:
            wallet = self.session.query(UserTokenWallet).filter(
                UserTokenWallet.user_id == user_id,
                UserTokenWallet.organization_id == org_id
            ).first()
            if wallet:
                # Auto-heal: ensure organization_id is set
                if not wallet.organization_id:
                    wallet.organization_id = org_id
                return wallet

        # Fallback to name check
        wallet = self.session.query(UserTokenWallet).filter(
            UserTokenWallet.user_id == user_id,
            func.lower(UserTokenWallet.organization_name) == canonical_name.lower()
        ).first()
        if wallet and org_id:
            # Auto-heal
            wallet.organization_id = org_id
            return wallet

        # --- LAZY CREATION/AUTO-HEAL ---
        # If user has a membership (either existing or lazy created), auto-create wallet with 0 tokens
        try:
            membership = self.get_membership(user_id, organization_name)
            if membership:
                wallet = UserTokenWallet(
                    user_id=user_id,
                    organization_id=org_id or "00000000-0000-0000-0000-000000000000",
                    organization_name=membership.organization_name,
                    allocated_tokens=0,
                    remaining_tokens=0,
                    consumed_tokens=0,
                    is_blocked=False
                )
                self.session.add(wallet)
                self.session.flush()
                return wallet
        except Exception:
            pass

        return None

    def update_wallet(self, user_id: int, organization_name: str, allocated_delta: int = 0, consumed_delta: int = 0, remaining_delta: int = 0) -> None:
        org_id, canonical_name = self._resolve_tenant(organization_name)
        wallet = self.get_user_wallet(user_id, organization_name)
        if not wallet:
            wallet = UserTokenWallet(
                user_id=user_id,
                organization_name=canonical_name,
                organization_id=org_id,
                allocated_tokens=max(0, allocated_delta),
                consumed_tokens=max(0, consumed_delta),
                remaining_tokens=max(0, remaining_delta),
                is_blocked=False
            )
            self.session.add(wallet)
            self.session.flush()
        else:
            self.session.query(UserTokenWallet).filter(
                UserTokenWallet.id == wallet.id
            ).update({
                UserTokenWallet.allocated_tokens: UserTokenWallet.allocated_tokens + allocated_delta,
                UserTokenWallet.consumed_tokens: UserTokenWallet.consumed_tokens + consumed_delta,
                UserTokenWallet.remaining_tokens: UserTokenWallet.remaining_tokens + remaining_delta
            })

    def get_total_allocated(self, organization_name: str) -> int:
        org_id, canonical_name = self._resolve_tenant(organization_name)
        if org_id:
            total = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter(
                UserTokenWallet.organization_id == org_id
            ).scalar()
            if total is not None:
                return total

        total = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter(
            func.lower(UserTokenWallet.organization_name) == canonical_name.lower()
        ).scalar()
        return total or 0
