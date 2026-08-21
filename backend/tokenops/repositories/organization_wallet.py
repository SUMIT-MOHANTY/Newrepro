from sqlalchemy.orm import Session
from tokenops.models import OrganizationWallet

class OrganizationWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, organization_name: str) -> OrganizationWallet | None:
        return self.session.query(OrganizationWallet).filter(
            OrganizationWallet.organization_name == organization_name
        ).first()

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
