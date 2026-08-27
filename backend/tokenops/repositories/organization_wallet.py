from sqlalchemy.orm import Session
from tokenops.models import OrganizationWallet

class OrganizationWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, organization_name: str) -> OrganizationWallet | None:
        from sqlalchemy import func
        # 1. Try case-insensitive matching on the string name
        wallet = self.session.query(OrganizationWallet).filter(
            func.lower(OrganizationWallet.organization_name) == organization_name.lower()
        ).first()
        if wallet:
            return wallet

        # 2. Try matching by resolved UUID if possible
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, _ = resolver.resolve(organization_name)
            return self.session.query(OrganizationWallet).filter(
                OrganizationWallet.id == org_id
            ).first()
        except Exception:
            return None

    def get_by_organization(self, organization_name: str) -> OrganizationWallet | None:
        """Alias for get_wallet for service compatibility."""
        return self.get_wallet(organization_name)

    def update_balance(self, organization_name: str, purchased_delta: int = 0, remaining_delta: int = 0) -> None:
        """Atomic UPDATE to modify wallet balances without SELECT FOR UPDATE."""
        from sqlalchemy import func
        self.session.query(OrganizationWallet).filter(
            func.lower(OrganizationWallet.organization_name) == organization_name.lower()
        ).update({
            OrganizationWallet.purchased_tokens: OrganizationWallet.purchased_tokens + purchased_delta,
            OrganizationWallet.remaining_tokens: OrganizationWallet.remaining_tokens + remaining_delta
        })

    def update_reserve(self, organization_name: str, reserved_delta: int) -> None:
        """Atomic UPDATE for reserved tokens."""
        from sqlalchemy import func
        self.session.query(OrganizationWallet).filter(
            func.lower(OrganizationWallet.organization_name) == organization_name.lower()
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
                purchased_tokens=0,
                remaining_tokens=0,
                reserved_tokens=0,
                payg_enabled=False,
                is_blocked=False,
            )
            self.session.add(wallet)
            self.session.flush()
        return wallet
