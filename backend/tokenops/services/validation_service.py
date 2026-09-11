from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository

class ValidationService:
    def __init__(self, org_repo: OrganizationWalletRepository, user_repo: UserWalletRepository):
        self.org_repo = org_repo
        self.user_repo = user_repo

    def validate_org_wallet_exists(self, organization_name: str) -> bool:
        return self.org_repo.get_wallet(organization_name) is not None

    def validate_user_wallet_exists(self, user_id: int, organization_name: str) -> bool:
        return (
            self.user_repo.get_user_wallet(user_id, organization_name) is not None or
            self.user_repo.get_membership(user_id, organization_name) is not None
        )

    def validate_sufficient_org_reserve(self, organization_name: str, amount: int) -> bool:
        wallet = self.org_repo.get_wallet(organization_name)
        if not wallet:
            return False
            
        # Formula: reserve = purchased - allocated_to_users
        total_allocated = self.user_repo.get_total_allocated(organization_name)
        actual_reserve = max(0, wallet.purchased_tokens - total_allocated)
        
        # Auto-heal integrity if reserved_tokens is out of sync
        if wallet.reserved_tokens != actual_reserve:
            wallet.reserved_tokens = actual_reserve
            self.org_repo.session.add(wallet)
            self.org_repo.session.flush()

        # Available to allocate is (purchased - allocated) = reserve
        return actual_reserve >= amount

    def validate_sufficient_user_balance(self, user_id: int, organization_name: str, amount: int) -> bool:
        wallet = self.user_repo.get_user_wallet(user_id, organization_name)
        if not wallet:
            return False
            
        # Formula: remaining = allocated - consumed
        actual_remaining = wallet.allocated_tokens - wallet.consumed_tokens
        
        # Auto-heal integrity if remaining_tokens is out of sync
        if wallet.remaining_tokens != actual_remaining:
            wallet.remaining_tokens = max(0, actual_remaining)
            self.user_repo.session.add(wallet)
            self.user_repo.session.flush()

        return actual_remaining >= amount
