from sqlalchemy.orm import Session
from tokenops.models import OrganizationWallet

class OrganizationWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, organization_name: str) -> OrganizationWallet | None:
        import uuid
        from sqlalchemy import func
        org_id = None
        canonical_name = organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            canonical_name = org.name
        except Exception:
            pass

        # 1. Match by resolved org_id or canonical / incoming organization_name
        query = self.session.query(OrganizationWallet)
        if org_id:
            wallet = query.filter(
                (OrganizationWallet.id == org_id) |
                (OrganizationWallet.organization_id == org_id) |
                (func.lower(OrganizationWallet.organization_name) == canonical_name.lower()) |
                (func.lower(OrganizationWallet.organization_name) == organization_name.lower())
            ).first()
        else:
            wallet = query.filter(
                (func.lower(OrganizationWallet.organization_name) == canonical_name.lower()) |
                (func.lower(OrganizationWallet.organization_name) == organization_name.lower())
            ).first()

        if wallet:
            # Auto-heal: set organization_id and canonical name if missing or mismatching
            modified = False
            if org_id and (not wallet.organization_id or wallet.organization_id != org_id):
                wallet.organization_id = org_id
                modified = True
            if canonical_name and wallet.organization_name != canonical_name:
                wallet.organization_name = canonical_name
                modified = True
            if modified:
                self.session.add(wallet)
                self.session.flush()
            return wallet

        # --- LAZY CREATION/AUTO-HEAL ---
        # If the organization actually exists in the core DB, auto-create a default wallet with 0 tokens
        if org_id:
            try:
                wallet = OrganizationWallet(
                    id=org_id or str(uuid.uuid4()),
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
        """Update wallet balances and flush to ensure session synchronization."""
        wallet = self.get_wallet(organization_name)
        if wallet:
            wallet.purchased_tokens = (wallet.purchased_tokens or 0) + purchased_delta
            wallet.remaining_tokens = (wallet.remaining_tokens or 0) + remaining_delta
            self.session.add(wallet)
            self.session.flush()

    def update_reserve(self, organization_name: str, reserved_delta: int) -> None:
        """Update reserved tokens and flush to ensure session synchronization."""
        wallet = self.get_wallet(organization_name)
        if wallet:
            wallet.reserved_tokens = (wallet.reserved_tokens or 0) + reserved_delta
            self.session.add(wallet)
            self.session.flush()

    def get_or_create(self, organization_name: str) -> OrganizationWallet:
        """Get existing wallet or lazily create a zero-balance wallet for the organization."""
        wallet = self.get_wallet(organization_name)
        if not wallet:
            import uuid
            org_id = None
            canonical_name = organization_name
            try:
                from tokenops.services.tenant_resolver_service import TenantResolverService
                resolver = TenantResolverService(self.session)
                org_id, org = resolver.resolve(organization_name)
                canonical_name = org.name  # Use canonical name
            except Exception:
                pass

            wallet = OrganizationWallet(
                id=org_id or str(uuid.uuid4()),
                organization_name=canonical_name,
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
