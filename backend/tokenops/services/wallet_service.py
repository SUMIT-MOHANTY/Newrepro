from sqlalchemy.orm import Session
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.domain import TokenTransaction, WalletState
from tokenops.models.ledger import TransactionType
from tokenops.utils.retry import retry_on_lock
import uuid

class WalletService:
    def __init__(
        self,
        session: Session,
        org_repo: OrganizationWalletRepository,
        user_repo: UserWalletRepository,
        validation: ValidationService,
        ledger: LedgerService,
        idempotency: IdempotencyService
    ):
        self.session = session
        self.org_repo = org_repo
        self.user_repo = user_repo
        self.validation = validation
        self.ledger = ledger
        self.idempotency = idempotency

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

    @retry_on_lock(max_retries=3)
    def purchase_tokens(self, organization_name: str, amount: int, request_id: str | None = None, remarks: str | None = None) -> WalletState:
        """
        Algorithm A: Purchase Tokens
        Increments org wallet purchased and remaining tokens.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                wallet = self.org_repo.get_or_create(organization_name)
                return WalletState(0, 0, wallet.remaining_tokens, wallet.reserved_tokens)

            wallet = self.org_repo.get_or_create(organization_name)
            new_balance = wallet.reserved_tokens + amount

            self.org_repo.update_balance(organization_name, purchased_delta=amount, remaining_delta=amount)
            self.org_repo.update_reserve(organization_name, reserved_delta=amount)
            
            tx = TokenTransaction(
                organization_name=organization_name,
                transaction_type=TransactionType.PURCHASE.value,
                token_delta=amount,
                reference_id=request_id,
                remarks=remarks
            )
            self.ledger.write_entry(tx, balance_after=new_balance)
            
            self.idempotency.mark_completed(request_id)

            # Re-fetch to get updated state before transaction commits
            wallet = self.org_repo.get_wallet(organization_name)
            return WalletState(0, 0, wallet.remaining_tokens, wallet.reserved_tokens)

    @retry_on_lock(max_retries=3)
    def allocate_tokens(self, user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm B: Allocate Tokens
        Moves tokens from Organization Reserve to User Wallet.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
                if not user_wallet:
                    raise ValueError("User wallet not found")
                return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)

            if not self.validation.validate_sufficient_org_reserve(organization_name, amount):
                raise ValueError("Insufficient available tokens in organization wallet to allocate")
            if not self.validation.validate_user_wallet_exists(user_id, organization_name):
                 raise ValueError("User wallet does not exist in this organization")

            org_wallet = self.org_repo.get_wallet(organization_name)
            org_new_balance = org_wallet.reserved_tokens - amount
            
            # 1. Update Org Wallet (reduce reserve, remaining is unchanged because tokens are not consumed yet)
            self.org_repo.update_reserve(organization_name, reserved_delta=-amount)

            # 2. Update User Wallet
            self.user_repo.update_wallet(user_id, organization_name, allocated_delta=amount, remaining_delta=amount)

            tx = TokenTransaction(
                organization_name=organization_name,
                user_id=user_id,
                transaction_type=TransactionType.ALLOCATION.value,
                token_delta=amount, # Ledger tracks the credit to the user, or should it be org level?
                reference_id=request_id
            )
            self.ledger.write_entry(tx, balance_after=org_new_balance)
            
            self.idempotency.mark_completed(request_id)

            user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
            return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)

    @retry_on_lock(max_retries=3)
    def reallocate_tokens(self, from_user_id: int, to_user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm C: Reallocate Tokens
        Moves tokens between two users in the same organization.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                to_wallet = self.user_repo.get_user_wallet(to_user_id, organization_name)
                if not to_wallet:
                    raise ValueError("Target user wallet not found")
                return WalletState(to_wallet.allocated_tokens, to_wallet.consumed_tokens, to_wallet.remaining_tokens, 0)

            if not self.validation.validate_sufficient_user_balance(from_user_id, organization_name, amount):
                raise ValueError("Source user has insufficient remaining balance")
            if not self.validation.validate_user_wallet_exists(to_user_id, organization_name):
                 raise ValueError("Target user wallet does not exist")

            org_wallet = self.org_repo.get_wallet(organization_name)
            org_balance = org_wallet.reserved_tokens

            # Deduct from source
            self.user_repo.update_wallet(from_user_id, organization_name, allocated_delta=-amount, remaining_delta=-amount)
            
            # Add to target
            self.user_repo.update_wallet(to_user_id, organization_name, allocated_delta=amount, remaining_delta=amount)

            # Ledger entries for both legs of the transaction
            # Debit source
            tx_out = TokenTransaction(
                organization_name=organization_name,
                user_id=from_user_id,
                transaction_type=TransactionType.REALLOCATION.value,
                token_delta=-amount,
                reference_id=f"{request_id}_out" if request_id else str(uuid.uuid4())
            )
            self.ledger.write_entry(tx_out, balance_after=org_balance)

            # Credit target
            tx_in = TokenTransaction(
                organization_name=organization_name,
                user_id=to_user_id,
                transaction_type=TransactionType.REALLOCATION.value,
                token_delta=amount,
                reference_id=f"{request_id}_in" if request_id else str(uuid.uuid4())
            )
            self.ledger.write_entry(tx_in, balance_after=org_balance)
            
            self.idempotency.mark_completed(request_id)

            to_wallet = self.user_repo.get_user_wallet(to_user_id, organization_name)
            return WalletState(to_wallet.allocated_tokens, to_wallet.consumed_tokens, to_wallet.remaining_tokens, 0)

    @retry_on_lock(max_retries=3)
    def revoke_tokens(self, user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm D: Revoke Tokens
        Moves unused tokens from User Wallet back to Organization Reserve/Balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
                if not user_wallet:
                     raise ValueError("User wallet not found")
                return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)

            if not self.validation.validate_sufficient_user_balance(user_id, organization_name, amount):
                raise ValueError("User has insufficient remaining balance to revoke")

            org_wallet = self.org_repo.get_wallet(organization_name)
            org_new_balance = org_wallet.reserved_tokens + amount

            # Deduct from user
            self.user_repo.update_wallet(user_id, organization_name, allocated_delta=-amount, remaining_delta=-amount)

            # Return to org (increase reserve, remaining is unchanged)
            self.org_repo.update_reserve(organization_name, reserved_delta=amount)

            tx = TokenTransaction(
                organization_name=organization_name,
                user_id=user_id,
                transaction_type=TransactionType.REVOCATION.value,
                token_delta=-amount, # from the user's perspective it's a debit
                reference_id=request_id
            )
            self.ledger.write_entry(tx, balance_after=org_new_balance)
            
            self.idempotency.mark_completed(request_id)

            user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
            return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)
