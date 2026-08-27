import logging
import uuid
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from tokenops.services.validation_service import ValidationService
from tokenops.services.pricing_service import PricingService
from tokenops.services.wallet_service import WalletService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.usage_summary_service import UsageSummaryService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.services.tenant_resolver_service import TenantResolverService
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization, UserTokenWallet
from models import AIUsageLog
from tokenops.models.ledger import TransactionType, TokenTransactionLedger
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
        idempotency: IdempotencyService,
        tenant_resolver: TenantResolverService
    ):
        self.session = session
        self.validation = validation
        self.pricing = pricing
        self.wallet = wallet
        self.ledger = ledger
        self.usage_summary = usage_summary
        self.idempotency = idempotency
        self.tenant_resolver = tenant_resolver

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

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
        tenant_resolver = TenantResolverService(session)

        return cls(
            session=session,
            validation=validation,
            pricing=pricing,
            wallet=wallet,
            ledger=ledger,
            usage_summary=usage_summary,
            idempotency=idempotency,
            tenant_resolver=tenant_resolver
        )

    @retry_on_lock(max_retries=3)
    def pre_execute(
        self,
        user_id: int,
        organization_name: Optional[str],
        model_name: Optional[str] = None,
        estimated_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
    ) -> float:
        """
        Pre-Execution Hook.

        For PREPAID organizations:
            - UserTokenWallet is the ONLY authoritative spendable balance.
            - There is NO fallback to OrganizationWallet.remaining_tokens.
            - If the user has no allocated wallet: TOKEN_EXHAUSTED (402).
            - If the user wallet is blocked: USER_BLOCKED (403).
            - If the user has remaining_tokens <= 0: TOKEN_EXHAUSTED (402).

        For PAYG organizations:
            - Enforces hard limit: current_spend + reserved_spend + estimated_cost <= hard_limit.
            - Atomically reserves in-flight spend on OrganizationWallet.payg_reserved_spend_usd.
            - Logs soft limit warning if projected spend reaches soft limit.
            - Returns the reserved_cost amount (float).
        """
        if not organization_name:
            raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")

        with self._tx():
            # 1. Resolve tenant deterministically
            org_id, org = self.tenant_resolver.resolve(organization_name)

            # 2. Verify user membership
            membership = self.session.query(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == org_id,
                UserOrganization.is_active == True
            ).first()
            if not membership:
                membership = self.session.query(UserOrganization).filter(
                    UserOrganization.user_id == user_id,
                    func.lower(UserOrganization.organization_name) == org.name.lower(),
                    UserOrganization.is_active == True
                ).first()
                if membership:
                    # Auto-heal
                    membership.organization_id = org_id

            if not membership:
                raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")

            # 3. Resolve org wallet — needed for block status and PAYG flag
            org_wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == org.name.lower())
            ).first()
            if org_wallet and (not org_wallet.organization_id or org_wallet.organization_id != org_id):
                org_wallet.organization_id = org_id

            if not org_wallet:
                raise HTTPException(status_code=403, detail="ORGANIZATION_ACCESS_DENIED")

            if org_wallet.is_blocked:
                raise HTTPException(status_code=403, detail="ORGANIZATION_BLOCKED")

            # 4. PAYG: check overdue invoices against grace period and user caps
            if org_wallet.payg_enabled:
                from tokenops.models.payg import PAYGInvoice, InvoiceStatus
                from datetime import datetime
                
                # Fetch all OVERDUE invoices for this organization
                overdue_invoices = self.session.query(PAYGInvoice).filter(
                    (PAYGInvoice.organization_id == org_id) |
                    (func.lower(PAYGInvoice.organization_name) == org.name.lower()),
                    PAYGInvoice.invoice_status == InvoiceStatus.OVERDUE.value
                ).all()

                grace_period = getattr(org_wallet, "payg_grace_period_months", 3)

                for invoice in overdue_invoices:
                    try:
                        by, bm = map(int, invoice.billing_month.split("-"))
                        today = datetime.utcnow()
                        cy, cm = today.year, today.month
                        diff_months = (cy - by) * 12 + (cm - bm)
                    except Exception:
                        diff_months = 0
                    
                    if diff_months >= grace_period:
                        raise HTTPException(
                            status_code=402,
                            detail=f"PAYG access suspended: invoice for {invoice.billing_month} has been overdue for {diff_months} months. Grace period threshold is {grace_period} months."
                        )
                
                # Hybrid PAYG Check: enforce user-level block or budget cap limits if wallet exists
                user_wallet = self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.user_id == user_id,
                    UserTokenWallet.organization_id == org_id
                ).first()
                if not user_wallet:
                    user_wallet = self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.user_id == user_id,
                        func.lower(UserTokenWallet.organization_name) == org.name.lower()
                    ).first()
                    if user_wallet and org_id:
                        user_wallet.organization_id = org_id
                
                if user_wallet:
                    if user_wallet.is_blocked:
                        raise HTTPException(status_code=403, detail="USER_BLOCKED")
                    
                    # If allocated_tokens > 0, treat it as a budget cap
                    if user_wallet.allocated_tokens > 0 and user_wallet.remaining_tokens <= 0:
                        raise HTTPException(status_code=402, detail="TOKEN_EXHAUSTED")
                        
                est_cost = 0.0
                if estimated_cost is not None and float(estimated_cost) > 0:
                    est_cost = float(estimated_cost)
                elif estimated_tokens is not None and int(estimated_tokens) > 0:
                    price = float(self.pricing.get_price(model_name or "default"))
                    est_cost = float(int(estimated_tokens) * price)

                current_spend = float(org_wallet.payg_current_spend_usd or 0.0)
                reserved_spend = float(org_wallet.payg_reserved_spend_usd or 0.0)
                projected_spend = current_spend + reserved_spend + est_cost

                # Check hard spending cap if configured (blocks consumption if limit is reached or projected spend exceeds limit)
                if org_wallet.payg_hard_limit_usd is not None and float(org_wallet.payg_hard_limit_usd) > 0:
                    hard_limit = float(org_wallet.payg_hard_limit_usd)
                    if current_spend + reserved_spend >= hard_limit or projected_spend > hard_limit:
                        raise HTTPException(status_code=402, detail="PAYG_HARD_LIMIT_REACHED")

                # Check soft spending warning threshold if configured (warn only, does not block)
                if org_wallet.payg_soft_limit_usd is not None and float(org_wallet.payg_soft_limit_usd) > 0:
                    if projected_spend >= float(org_wallet.payg_soft_limit_usd):
                        logger.warning(
                            f"PAYG soft limit warning for org '{org.name}': projected spend ${projected_spend:.2f} "
                            f"reached soft limit ${float(org_wallet.payg_soft_limit_usd):.2f}"
                        )

                # Atomically record in-flight reservation
                if est_cost > 0:
                    if org_wallet.payg_hard_limit_usd is not None and float(org_wallet.payg_hard_limit_usd) > 0:
                        rows_updated = self.session.query(OrganizationWallet).filter(
                            OrganizationWallet.id == org_wallet.id,
                            (OrganizationWallet.payg_current_spend_usd + OrganizationWallet.payg_reserved_spend_usd + est_cost) <= org_wallet.payg_hard_limit_usd
                        ).update({
                            OrganizationWallet.payg_reserved_spend_usd: OrganizationWallet.payg_reserved_spend_usd + est_cost
                        }, synchronize_session=False)

                        if rows_updated == 0:
                            raise HTTPException(status_code=402, detail="PAYG_HARD_LIMIT_REACHED")
                    else:
                        self.session.query(OrganizationWallet).filter(
                            OrganizationWallet.id == org_wallet.id
                        ).update({
                            OrganizationWallet.payg_reserved_spend_usd: OrganizationWallet.payg_reserved_spend_usd + est_cost
                        }, synchronize_session=False)

                    self.session.flush()

                return est_cost

            # 5. PREPAID: UserTokenWallet is mandatory.
            # There is NO fallback to OrganizationWallet.remaining_tokens.
            # A user with no allocation must be blocked, not silently routed to the org pool.
            user_wallet = self.session.query(UserTokenWallet).filter(
                UserTokenWallet.user_id == user_id,
                UserTokenWallet.organization_id == org_id
            ).first()
            if not user_wallet:
                user_wallet = self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.user_id == user_id,
                    func.lower(UserTokenWallet.organization_name) == org.name.lower()
                ).first()
                if user_wallet:
                    # Auto-heal
                    user_wallet.organization_id = org_id

            if not user_wallet:
                raise HTTPException(status_code=402, detail="TOKEN_EXHAUSTED")

            if user_wallet.is_blocked:
                raise HTTPException(status_code=403, detail="USER_BLOCKED")

            if user_wallet.remaining_tokens <= 0:
                raise HTTPException(status_code=402, detail="TOKEN_EXHAUSTED")

            return 0.0

    @retry_on_lock(max_retries=3)
    def post_execute(
        self,
        user_id: int,
        organization_name: Optional[str],
        model_name: str,
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        request_id: Optional[str] = None,
        reserved_cost: Optional[float] = None,
    ) -> None:
        """
        Post-Execution Hook.

        For PREPAID organizations:
            - Deducts actual tokens from UserTokenWallet ONLY.
            - OrganizationWallet.remaining_tokens is NOT modified — tokens were already
              moved to the user during allocation; deducting from org would double count.
            - Actual provider-reported tokens are always recorded (no min() clamp).
            - Wallet may go negative — the NEXT pre_execute call will block the user.

        For PAYG organizations:
            - No prepaid wallet is touched.
            - Releases in-flight reservation and settles actual dollar spend.
            - PAYG_USAGE ledger entry records cost/usage attribution.

        Handling missing/unknown tokens:
            - If prompt_tokens or completion_tokens is None, records status UNKNOWN in ai_usage_logs
              and skips wallet deduction (leaves for manual reconciliation).
        """
        if not organization_name:
            return

        # ── Unknown tokens branch ─────────────────────────────────────────────
        if prompt_tokens is None or completion_tokens is None:
            with self._tx():
                if not self.idempotency.create_processing_record(request_id):
                    return

                try:
                    org_id, org = self.tenant_resolver.resolve(organization_name)
                    canonical_name = org.name
                except Exception:
                    org_id = None
                    canonical_name = organization_name

                log_entry = AIUsageLog(
                    user_id=user_id,
                    project_token=canonical_name,
                    organization_name=canonical_name,
                    organization_id=org_id,
                    model=model_name,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cost=0.0,
                    usage_status="UNKNOWN"
                )
                self.session.add(log_entry)
                self.idempotency.mark_completed(request_id)
                logger.warning(
                    f"Unknown token usage for request {request_id}, "
                    "logged as UNKNOWN for manual reconciliation."
                )

            # Release in-flight reservation if any
            if reserved_cost and float(reserved_cost) > 0:
                self.release_reservation(organization_name, reserved_cost)
            return

        # ── Normal deduction path ─────────────────────────────────────────────
        with self._tx():
            if not self.idempotency.create_processing_record(request_id):
                return

            try:
                org_id, org = self.tenant_resolver.resolve(organization_name)
                canonical_name = org.name
            except Exception:
                org_id = None
                canonical_name = organization_name

            org_wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == canonical_name.lower())
            ).first()

            if not org_wallet:
                logger.error(f"post_execute: org wallet not found for {canonical_name}, skipping.")
                return

            total_tokens = prompt_tokens + completion_tokens
            price = self.pricing.get_price(model_name)
            cost = float(price * total_tokens)

            if org_wallet.payg_enabled:
                # ── PAYG PATH ─────────────────────────────────────────────────
                # Release in-flight reservation and settle actual dollar spend
                if reserved_cost is not None and float(reserved_cost) > 0:
                    current_res = float(org_wallet.payg_reserved_spend_usd or 0.0)
                    org_wallet.payg_reserved_spend_usd = max(0.0, current_res - float(reserved_cost))

                org_wallet.payg_current_spend_usd = float(org_wallet.payg_current_spend_usd or 0.0) + cost

                # Meaningful accumulated PAYG token debt semantics for balance_after
                prev_payg = self.session.query(func.sum(TokenTransactionLedger.token_delta)).filter(
                    func.lower(TokenTransactionLedger.organization_name) == canonical_name.lower(),
                    TokenTransactionLedger.transaction_type == TransactionType.PAYG_USAGE.value
                ).scalar() or 0
                accumulated_payg_balance = prev_payg - total_tokens

                tx = TokenTransaction(
                    organization_name=canonical_name,
                    transaction_type=TransactionType.PAYG_USAGE.value,
                    token_delta=-total_tokens,
                    reference_id=request_id,
                    user_id=user_id,
                    remarks=f"Model: {model_name} (PAYG, Cost: ${cost:.6f})"
                )
                self.ledger.write_entry(tx, balance_after=accumulated_payg_balance)

                # Hybrid PAYG: if UserTokenWallet exists, decrement balance cap
                user_wallet = self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.user_id == user_id,
                    UserTokenWallet.organization_id == org_id
                ).first()
                if not user_wallet:
                    user_wallet = self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.user_id == user_id,
                        func.lower(UserTokenWallet.organization_name) == canonical_name.lower()
                    ).first()
                
                if user_wallet:
                    self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.id == user_wallet.id
                    ).update({
                        UserTokenWallet.consumed_tokens: UserTokenWallet.consumed_tokens + total_tokens,
                        UserTokenWallet.remaining_tokens: UserTokenWallet.remaining_tokens - total_tokens
                    })

                # Hybrid PAYG: if UserTokenWallet exists, decrement balance cap
                user_wallet = self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.user_id == user_id,
                    UserTokenWallet.organization_id == org_id
                ).first()
                if not user_wallet:
                    user_wallet = self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.user_id == user_id,
                        func.lower(UserTokenWallet.organization_name) == canonical_name.lower()
                    ).first()
                
                if user_wallet:
                    self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.id == user_wallet.id
                    ).update({
                        UserTokenWallet.consumed_tokens: UserTokenWallet.consumed_tokens + total_tokens,
                        UserTokenWallet.remaining_tokens: UserTokenWallet.remaining_tokens - total_tokens
                    })

            else:
                # ── PREPAID PATH ──────────────────────────────────────────────
                # Deduct ONLY from the UserTokenWallet.
                # OrganizationWallet.remaining_tokens is intentionally NOT touched here.
                # The tokens were already moved out of org reserve during allocation.
                user_wallet = self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.user_id == user_id,
                    UserTokenWallet.organization_id == org_id
                ).first()

                if not user_wallet:
                    user_wallet = self.session.query(UserTokenWallet).filter(
                        UserTokenWallet.user_id == user_id,
                        func.lower(UserTokenWallet.organization_name) == canonical_name.lower()
                    ).first()
                    if user_wallet:
                        user_wallet.organization_id = org_id

                if not user_wallet:
                    logger.error(
                        f"post_execute: UserTokenWallet not found for user {user_id} "
                        f"in org {canonical_name}. Logging UNKNOWN."
                    )
                    log_entry = AIUsageLog(
                        user_id=user_id,
                        project_token=canonical_name,
                        organization_name=canonical_name,
                        organization_id=org_id,
                        model=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost=cost,
                        usage_status="UNKNOWN"
                    )
                    self.session.add(log_entry)
                    self.idempotency.mark_completed(request_id)
                    return

                # Capture balance BEFORE for a correct, auditable ledger entry.
                balance_before = user_wallet.remaining_tokens

                # Deduct actual tokens — NO min() clamp.
                # The actual provider-reported consumption must always be preserved.
                # If remaining goes negative, the next pre_execute will block this user.
                self.session.query(UserTokenWallet).filter(
                    UserTokenWallet.id == user_wallet.id
                ).update({
                    UserTokenWallet.consumed_tokens: UserTokenWallet.consumed_tokens + total_tokens,
                    UserTokenWallet.remaining_tokens: UserTokenWallet.remaining_tokens - total_tokens
                })

                # AI_CONSUMPTION ledger entry — balance_after is the USER wallet balance.
                tx = TokenTransaction(
                    organization_name=canonical_name,
                    transaction_type=TransactionType.AI_CONSUMPTION.value,
                    token_delta=-total_tokens,
                    reference_id=request_id,
                    user_id=user_id,
                    remarks=f"Model: {model_name}"
                )
                self.ledger.write_entry(tx, balance_after=balance_before - total_tokens)

            # ── Common: Usage summaries + AIUsageLog (both PREPAID and PAYG) ──
            self.usage_summary.increment_rollup(
                organization_name=canonical_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost=cost
            )

            self.usage_summary.increment_user_rollup(
                user_id=user_id,
                organization_name=canonical_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost=cost
            )

            log_entry = AIUsageLog(
                user_id=user_id,
                project_token=canonical_name,
                organization_name=canonical_name,
                organization_id=org_id,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost,
                usage_status="COMPLETED"
            )
            self.session.add(log_entry)

            self.idempotency.mark_completed(request_id)

    @retry_on_lock(max_retries=3)
    def release_reservation(
        self,
        organization_name: str,
        reserved_cost: Optional[float] = None
    ) -> None:
        """
        Releases in-flight PAYG reserved spend when an execution fails or is cancelled
        without incrementing payg_current_spend_usd.
        """
        if reserved_cost is None or float(reserved_cost) <= 0:
            return
        with self._tx():
            try:
                org_id, org = self.tenant_resolver.resolve(organization_name)
                canonical_name = org.name
            except Exception:
                org_id = None
                canonical_name = organization_name

            org_wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == canonical_name.lower())
            ).first()
            if org_wallet:
                current_res = float(org_wallet.payg_reserved_spend_usd or 0.0)
                org_wallet.payg_reserved_spend_usd = max(0.0, current_res - float(reserved_cost))
