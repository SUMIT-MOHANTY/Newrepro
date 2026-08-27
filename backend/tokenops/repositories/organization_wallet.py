from sqlalchemy.orm import Session
from tokenops.models import OrganizationWallet

class OrganizationWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, organization_name: str) -> OrganizationWallet | None:
        return self.session.query(OrganizationWallet).filter(
            OrganizationWallet.organization_name == organization_name
        ).first()

    def get_by_organization(self, organization_name: str) -> OrganizationWallet | None:
        """Alias for get_wallet for service compatibility."""
        return self.get_wallet(organization_name)

    def update_balance(self, organization_name: str, purchased_delta: int = 0, remaining_delta: int = 0) -> None:
        """Atomic UPDATE to modify wallet balances without SELECT FOR UPDATE."""
        self.session.query(OrganizationWallet).filter(
            OrganizationWallet.organization_name == organization_name
        ).update({
            OrganizationWallet.purchased_tokens: OrganizationWallet.purchased_tokens + purchased_delta,
            OrganizationWallet.remaining_tokens: OrganizationWallet.remaining_tokens + remaining_delta
        })

    def update_reserve(self, organization_name: str, reserved_delta: int) -> None:
        """Atomic UPDATE for reserved tokens."""
        self.session.query(OrganizationWallet).filter(
            OrganizationWallet.organization_name == organization_name
        ).update({
            OrganizationWallet.reserved_tokens: OrganizationWallet.reserved_tokens + reserved_delta
        })

    def get_or_create(self, organization_name: str) -> OrganizationWallet:
        """Get existing wallet or lazily create a zero-balance wallet for the organization."""
        wallet = self.get_wallet(organization_name)
        if not wallet:
            wallet = OrganizationWallet(
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
