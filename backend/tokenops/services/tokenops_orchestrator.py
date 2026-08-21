import logging
import uuid
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from tokenops.services.validation_service import ValidationService
from tokenops.services.pricing_service import PricingService
from tokenops.services.wallet_service import WalletService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.usage_summary_service import UsageSummaryService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization
from models import AIUsageLog
from tokenops.models.ledger import TransactionType
from tokenops.domain import TokenTransaction
from tokenops.utils.retry import retry_on_lock

logger = logging.getLogger(__name__)

class TokenOpsOrchestrator:
    def __init__(
        self,
        session: Session,
        validation: ValidationService,
        pricing: PricingService,
        wallet: WalletService,
        ledger: LedgerService,
        usage_summary: UsageSummaryService,
        idempotency: IdempotencyService
    ):
        self.session = session
        self.validation = validation
        self.pricing = pricing
        self.wallet = wallet
        self.ledger = ledger
        self.usage_summary = usage_summary
        self.idempotency = idempotency

    @classmethod
    def create(cls, session: Session) -> "TokenOpsOrchestrator":
        from tokenops.repositories.organization_wallet import OrganizationWalletRepository
        from tokenops.repositories.user_wallet import UserWalletRepository
        from tokenops.repositories.pricing import PricingRepository
        from tokenops.repositories.ledger import LedgerRepository
        from tokenops.repositories.usage_summary import UsageSummaryRepository
        from tokenops.repositories.idempotency import IdempotencyRepository

        org_repo = OrganizationWalletRepository(session)
        user_repo = UserWalletRepository(session)
        pricing_repo = PricingRepository(session)
        ledger_repo = LedgerRepository(session)
        usage_repo = UsageSummaryRepository(session)
        idempotency_repo = IdempotencyRepository(session)

        validation = ValidationService(org_repo, user_repo)
        pricing = PricingService(pricing_repo)
        ledger = LedgerService(ledger_repo)
        idempotency = IdempotencyService(idempotency_repo)
        wallet = WalletService(session, org_repo, user_repo, validation, ledger, idempotency)
        usage_summary = UsageSummaryService(usage_repo)

        return cls(
            session=session,
            validation=validation,
            pricing=pricing,
            wallet=wallet,
            ledger=ledger,
            usage_summary=usage_summary,
            idempotency=idempotency
        )

    @retry_on_lock(max_retries=3)
    def pre_execute(self, user_id: int, organization_name: Optional[str]) -> None:
        """
        Pre-Execution Hook.
        1. Validates RBAC (user mapped to org).
        2. Validates block status.
        3. Validates PREPAID balance if not PAYG.
        """
        if not organization_name:
            raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")
            
        with self.session.begin():
            # Check if organization exists and user is mapped
            membership = self.session.query(UserOrganization).filter_by(
                user_id=user_id,
                organization_name=organization_name,
                is_active=True
            ).first()
            
            if not membership:
                raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")
                
            wallet = self.session.query(OrganizationWallet).filter_by(
                organization_name=organization_name
            ).first()
            
            if not wallet:
                raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")
                
            if wallet.is_blocked:
                raise HTTPException(status_code=403, detail="ORGANIZATION_BLOCKED")
                
            # Check balance if not PAYG
            if not wallet.payg_enabled and wallet.remaining_tokens <= 0:
                raise HTTPException(status_code=402, detail="TOKEN_EXHAUSTED")

    @retry_on_lock(max_retries=3)
    def post_execute(
        self,
        user_id: int,
        organization_name: Optional[str],
        model_name: str,
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        request_id: Optional[str] = None
    ) -> None:
        """
        Post-Execution Hook.
        1. If tokens are None (unknown), skip deduction and log UNKNOWN audit event.
        2. Compute cost.
        3. Deduct from wallet.
        4. Write to ledger.
        5. Update usage summary.
        6. Write AIUsageLog.
        """
        if not organization_name:
            return
            
        request_id = request_id or str(uuid.uuid4())
            
        # Fallback handling: If usage metrics are unavailable
        if prompt_tokens is None or completion_tokens is None:
            with self.session.begin():
                if not self.idempotency.create_processing_record(request_id):
                    return
                    
                log_entry = AIUsageLog(
                    user_id=user_id,
                    project_token=organization_name,
                    model=model_name,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cost=0.0,
                    usage_status="UNKNOWN"
                )
                self.session.add(log_entry)
                self.idempotency.mark_completed(request_id)
                logger.warning(f"Unknown token usage for request {request_id}, logged as UNKNOWN for manual reconciliation.")
            return
            
        # Normal deduction
        with self.session.begin():
            if not self.idempotency.create_processing_record(request_id):
                return
                
            wallet = self.session.query(OrganizationWallet).filter_by(
                organization_name=organization_name
            ).first()
            
            if not wallet:
                return

            total_tokens = prompt_tokens + completion_tokens
            
            # 1. Deduct from wallet
            wallet.consumed_tokens += total_tokens
            wallet.remaining_tokens = wallet.purchased_tokens - wallet.consumed_tokens - wallet.reserved_tokens
            
            # 2. Write Ledger
            price = self.pricing.get_price(model_name)
            cost = float(price * total_tokens)
            
            tx = TokenTransaction(
                organization_name=organization_name,
                transaction_type=TransactionType.CONSUMPTION.value,
                token_delta=-total_tokens,
                reference_id=request_id,
                user_id=user_id,
                remarks=f"Model: {model_name}"
            )
            self.ledger.write_entry(tx, balance_after=wallet.remaining_tokens)
            
            # 3. Update Usage Summary
            self.usage_summary.increment_rollup(
                organization_name=organization_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost=cost
            )
            
            # 4. Write AIUsageLog
            log_entry = AIUsageLog(
                user_id=user_id,
                project_token=organization_name,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost,
                usage_status="COMPLETED"
            )
            self.session.add(log_entry)
            
            self.idempotency.mark_completed(request_id)
