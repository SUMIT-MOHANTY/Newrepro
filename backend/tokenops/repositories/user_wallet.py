from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.models import UserTokenWallet

class UserWalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_user_wallet(self, user_id: int, organization_name: str) -> UserTokenWallet | None:
        return self.session.query(UserTokenWallet).filter(
            UserTokenWallet.user_id == user_id,
            UserTokenWallet.organization_name == organization_name
        ).first()

    def update_wallet(self, user_id: int, organization_name: str, allocated_delta: int = 0, consumed_delta: int = 0, remaining_delta: int = 0) -> None:
        self.session.query(UserTokenWallet).filter(
            UserTokenWallet.user_id == user_id,
            UserTokenWallet.organization_name == organization_name
        ).update({
            UserTokenWallet.allocated_tokens: UserTokenWallet.allocated_tokens + allocated_delta,
            UserTokenWallet.consumed_tokens: UserTokenWallet.consumed_tokens + consumed_delta,
            UserTokenWallet.remaining_tokens: UserTokenWallet.remaining_tokens + remaining_delta
        })

    def get_total_allocated(self, organization_name: str) -> int:
        total = self.session.query(func.sum(UserTokenWallet.allocated_tokens)).filter(
            UserTokenWallet.organization_name == organization_name
        ).scalar()
        return total or 0
