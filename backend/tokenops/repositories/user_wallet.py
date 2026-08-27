from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.models import UserTokenWallet, UserOrganization

class UserWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_membership(self, user_id: int, organization_name: str) -> UserOrganization | None:
        return self.session.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            func.lower(UserOrganization.organization_name) == organization_name.lower()
        ).first()

    def get_user_wallet(self, user_id: int, organization_name: str) -> UserTokenWallet | None:
        return self.session.query(UserTokenWallet).filter(
            UserTokenWallet.user_id == user_id,
            func.lower(UserTokenWallet.organization_name) == organization_name.lower()
        ).first()

    def update_wallet(self, user_id: int, organization_name: str, allocated_delta: int = 0, consumed_delta: int = 0, remaining_delta: int = 0) -> None:
        wallet = self.get_user_wallet(user_id, organization_name)
        if not wallet:
            wallet = UserTokenWallet(
                user_id=user_id,
                organization_name=organization_name,
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
        total = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter(
            func.lower(UserTokenWallet.organization_name) == organization_name.lower()
        ).scalar()
        return total or 0
