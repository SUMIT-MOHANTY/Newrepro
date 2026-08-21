from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository

class ValidationService:
    def __init__(self, org_repo: OrganizationWalletRepository, user_repo: UserWalletRepository):
        self.org_repo = org_repo
        self.user_repo = user_repo

    def validate_org_wallet_exists(self, organization_name: str) -> bool:
        return self.org_repo.get_wallet(organization_name) is not None

    def validate_user_wallet_exists(self, user_id: int, organization_name: str) -> bool:
        return self.user_repo.get_user_wallet(user_id, organization_name) is not None

    def validate_sufficient_org_reserve(self, organization_name: str, amount: int) -> bool:
        wallet = self.org_repo.get_wallet(organization_name)
        if not wallet:
            return False
            
        # Formula: reserve = purchased - allocated_to_users
        total_allocated = self.user_repo.get_total_allocated(organization_name)
        actual_reserve = wallet.purchased_tokens - total_allocated
        
        # Verify integrity
        if wallet.reserved_tokens != actual_reserve:
            raise ValueError(f"Organization reserve integrity error: expected {actual_reserve}, got {wallet.reserved_tokens}")

        # Available to allocate is (purchased - allocated) = reserve
        return actual_reserve >= amount

    def validate_sufficient_user_balance(self, user_id: int, organization_name: str, amount: int) -> bool:
        wallet = self.user_repo.get_user_wallet(user_id, organization_name)
        if not wallet:
            return False
            
        # Formula: remaining = allocated - consumed
        actual_remaining = wallet.allocated_tokens - wallet.consumed_tokens
        
        # Verify integrity
        if wallet.remaining_tokens != actual_remaining:
             raise ValueError(f"User remaining integrity error: expected {actual_remaining}, got {wallet.remaining_tokens}")

        return actual_remaining >= amount
