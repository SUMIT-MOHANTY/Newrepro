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

        Ledger invariant:
            balance_after = org.remaining_tokens (before) + amount
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                wallet = self.org_repo.get_or_create(organization_name)
                return WalletState(0, 0, wallet.remaining_tokens, wallet.reserved_tokens)

            wallet = self.org_repo.get_or_create(organization_name)
            # Capture remaining BEFORE mutation for correct ledger balance_after.
            # P0-7 fix: was incorrectly using reserved_tokens + amount.
            balance_before = wallet.remaining_tokens

            self.org_repo.update_balance(organization_name, purchased_delta=amount, remaining_delta=amount)
            self.org_repo.update_reserve(organization_name, reserved_delta=amount)

            tx = TokenTransaction(
                organization_name=organization_name,
                transaction_type=TransactionType.PURCHASE.value,
                token_delta=amount,
                reference_id=request_id,
                purpose="Token Pack Purchase",
                remarks=remarks
            )
            self.ledger.write_entry(tx, balance_after=balance_before + amount)

            self.idempotency.mark_completed(request_id)

            wallet = self.org_repo.get_wallet(organization_name)
            return WalletState(0, 0, wallet.remaining_tokens, wallet.reserved_tokens)

    @retry_on_lock(max_retries=3)
    def allocate_tokens(self, user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm B: Allocate Tokens
        Moves tokens from Organization Reserve to User Wallet.

        Ledger invariant:
            ALLOCATION credits the USER wallet.
            balance_after = user.remaining_tokens (before) + amount
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

            # Capture user wallet balance BEFORE mutation for ledger.
            # P0-7 fix: was incorrectly using org reserved_tokens.
            user_wallet_before = self.user_repo.get_user_wallet(user_id, organization_name)
            user_balance_before = user_wallet_before.remaining_tokens if user_wallet_before else 0

            # 1. Update Org Wallet (reduce reserve; remaining is unchanged — tokens still in system)
            self.org_repo.update_reserve(organization_name, reserved_delta=-amount)

            # 2. Credit User Wallet
            self.user_repo.update_wallet(user_id, organization_name, allocated_delta=amount, remaining_delta=amount)

            # Ledger records the credit to the USER wallet.
            tx = TokenTransaction(
                organization_name=organization_name,
                user_id=user_id,
                transaction_type=TransactionType.ALLOCATION.value,
                token_delta=amount,
                reference_id=request_id,
                purpose="Admin Quota Allocation"
            )
            self.ledger.write_entry(tx, balance_after=user_balance_before + amount)

            self.idempotency.mark_completed(request_id)

            user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
            return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)

    @retry_on_lock(max_retries=3)
    def reallocate_tokens(self, from_user_id: int, to_user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm C: Reallocate Tokens
        Moves tokens between two users in the same organization.

        Ledger invariants:
            Out leg (source): balance_after = from_user.remaining (before) - amount
            In leg (target):  balance_after = to_user.remaining (before) + amount
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if from_user_id == to_user_id:
            raise ValueError("Source and destination users must be different")

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

            # Capture BOTH user wallet balances BEFORE mutation for correct ledger entries.
            # P0-7 fix: was incorrectly using org reserved_tokens for both legs.
            from_wallet = self.user_repo.get_user_wallet(from_user_id, organization_name)
            to_wallet_before = self.user_repo.get_user_wallet(to_user_id, organization_name)
            from_balance_before = from_wallet.remaining_tokens if from_wallet else 0
            to_balance_before = to_wallet_before.remaining_tokens if to_wallet_before else 0

            # Deduct from source
            self.user_repo.update_wallet(from_user_id, organization_name, allocated_delta=-amount, remaining_delta=-amount)

            # Add to target
            self.user_repo.update_wallet(to_user_id, organization_name, allocated_delta=amount, remaining_delta=amount)

            # Debit leg: source user wallet
            tx_out = TokenTransaction(
                organization_name=organization_name,
                user_id=from_user_id,
                transaction_type=TransactionType.REALLOCATION.value,
                token_delta=-amount,
                reference_id=f"{request_id}_out" if request_id else str(uuid.uuid4()),
                purpose="User Wallet Reallocation"
            )
            self.ledger.write_entry(tx_out, balance_after=from_balance_before - amount)

            # Credit leg: target user wallet
            tx_in = TokenTransaction(
                organization_name=organization_name,
                user_id=to_user_id,
                transaction_type=TransactionType.REALLOCATION.value,
                token_delta=amount,
                reference_id=f"{request_id}_in" if request_id else str(uuid.uuid4()),
                purpose="User Wallet Reallocation"
            )
            self.ledger.write_entry(tx_in, balance_after=to_balance_before + amount)

            self.idempotency.mark_completed(request_id)

            to_wallet = self.user_repo.get_user_wallet(to_user_id, organization_name)
            return WalletState(to_wallet.allocated_tokens, to_wallet.consumed_tokens, to_wallet.remaining_tokens, 0)

    @retry_on_lock(max_retries=3)
    def revoke_tokens(self, user_id: int, organization_name: str, amount: int, request_id: str | None = None) -> WalletState:
        """
        Algorithm D: Revoke Tokens
        Moves unused tokens from User Wallet back to Organization Reserve.

        Ledger invariant:
            REVOCATION debits the USER wallet.
            balance_after = user.remaining_tokens (before) - amount
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

            # Capture user wallet balance BEFORE mutation for ledger.
            # P0-7 fix: was incorrectly using org reserved_tokens + amount.
            user_wallet_before = self.user_repo.get_user_wallet(user_id, organization_name)
            user_balance_before = user_wallet_before.remaining_tokens

            # Deduct from user
            self.user_repo.update_wallet(user_id, organization_name, allocated_delta=-amount, remaining_delta=-amount)

            # Return to org reserve (remaining is unchanged — tokens stay in the system)
            self.org_repo.update_reserve(organization_name, reserved_delta=amount)

            # Ledger records the debit from the USER wallet.
            tx = TokenTransaction(
                organization_name=organization_name,
                user_id=user_id,
                transaction_type=TransactionType.REVOCATION.value,
                token_delta=-amount,
                reference_id=request_id,
                purpose="Quota Revocation"
            )
            self.ledger.write_entry(tx, balance_after=user_balance_before - amount)

            self.idempotency.mark_completed(request_id)

            user_wallet = self.user_repo.get_user_wallet(user_id, organization_name)
            return WalletState(user_wallet.allocated_tokens, user_wallet.consumed_tokens, user_wallet.remaining_tokens, 0)
