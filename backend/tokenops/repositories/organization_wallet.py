from sqlalchemy.orm import Session
from tokenops.models import OrganizationWallet

class OrganizationWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, organization_name: str) -> OrganizationWallet | None:
        # 1. Try matching by resolved UUID if possible
        org_id = None
        canonical_name = organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            canonical_name = org.name
            wallet = self.session.query(OrganizationWallet).filter(
                OrganizationWallet.id == org_id
            ).first()
            if wallet:
                # Auto-heal: set organization_id if missing or mismatching
                if not wallet.organization_id or wallet.organization_id != org_id:
                    wallet.organization_id = org_id
                return wallet
        except Exception:
            pass

        # 2. Fallback to case-insensitive name lookup for compatibility
        from sqlalchemy import func
        wallet = self.session.query(OrganizationWallet).filter(
            func.lower(OrganizationWallet.organization_name) == canonical_name.lower()
        ).first()
        if wallet:
            # Auto-heal: set organization_id / id if missing
            if org_id and (not wallet.organization_id or wallet.organization_id != org_id):
                wallet.organization_id = org_id
                if not wallet.id:
                    wallet.id = org_id
                self.session.add(wallet)
                self.session.flush()
            return wallet

        # --- LAZY CREATION/AUTO-HEAL ---
        # If the organization actually exists in the core DB, auto-create a default wallet with 0 tokens
        if org_id:
            try:
                wallet = OrganizationWallet(
                    id=org_id,
                    organization_name=canonical_name,
                    organization_id=org_id,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False
                )
                self.session.add(wallet)
                self.session.flush()
                return wallet
            except Exception:
                pass

        return None

    def get_by_organization(self, organization_name: str) -> OrganizationWallet | None:
        """Alias for get_wallet for service compatibility."""
        return self.get_wallet(organization_name)

    def update_balance(self, organization_name: str, purchased_delta: int = 0, remaining_delta: int = 0) -> None:
        """Atomic UPDATE to modify wallet balances without SELECT FOR UPDATE."""
        wallet = self.get_wallet(organization_name)
        if wallet:
            self.session.query(OrganizationWallet).filter(
                OrganizationWallet.id == wallet.id
            ).update({
                OrganizationWallet.purchased_tokens: OrganizationWallet.purchased_tokens + purchased_delta,
                OrganizationWallet.remaining_tokens: OrganizationWallet.remaining_tokens + remaining_delta
            })

    def update_reserve(self, organization_name: str, reserved_delta: int) -> None:
        """Atomic UPDATE for reserved tokens."""
        wallet = self.get_wallet(organization_name)
        if wallet:
            self.session.query(OrganizationWallet).filter(
                OrganizationWallet.id == wallet.id
            ).update({
                OrganizationWallet.reserved_tokens: OrganizationWallet.reserved_tokens + reserved_delta
            })

    def get_or_create(self, organization_name: str) -> OrganizationWallet:
        """Get existing wallet or lazily create a zero-balance wallet for the organization."""
        wallet = self.get_wallet(organization_name)
        if not wallet:
            org_id = None
            try:
                from tokenops.services.tenant_resolver_service import TenantResolverService
                resolver = TenantResolverService(self.session)
                org_id, org = resolver.resolve(organization_name)
                organization_name = org.name  # Use canonical name
            except Exception:
                pass

            wallet = OrganizationWallet(
                id=org_id,  # Use the authoritative organization UUID if resolved
                organization_name=organization_name,
                organization_id=org_id,
                purchased_tokens=0,
                remaining_tokens=0,
                reserved_tokens=0,
                payg_enabled=False,
                is_blocked=False,
            )
            self.session.add(wallet)
            self.session.flush()
        return wallet
