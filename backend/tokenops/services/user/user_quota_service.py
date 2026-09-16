import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import User
from tokenops.models.user_quota_request import UserTokenQuotaRequest, UserQuotaRequestStatus
from tokenops.models.token_wallet import UserTokenWallet, OrganizationWallet
from tokenops.services.tenant_resolver_service import TenantResolverService
from tokenops.services.org_admin.org_wallet_service import OrgWalletService

logger = logging.getLogger(__name__)


class UserQuotaService:
    def __init__(self, session: Session):
        self.session = session
        self.tenant_resolver = TenantResolverService(session)

    def create_request(
        self,
        user_id: int,
        org_identifier: str,
        requested_tokens: int,
        reason: Optional[str] = None
    ) -> UserTokenQuotaRequest:
        """
        Submits a token top-up request from a user to their Organization Admin.
        Enforces strict exhaustion guard: user remaining tokens must be <= 0.
        """
        if requested_tokens <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_TOKEN_AMOUNT: Requested tokens must be greater than 0."
            )

        if not org_identifier or not org_identifier.strip() or org_identifier == "Default Organization":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ORGANIZATION_SELECTION_REQUIRED"
            )

        org_id, org = self.tenant_resolver.resolve(org_identifier)
        canonical_name = org.name

        # 1. Check user token wallet balance (Exhaustion Guard)
        user_wallet = self.session.query(UserTokenWallet).filter(
            UserTokenWallet.user_id == user_id,
            (UserTokenWallet.organization_id == org_id) | (func.lower(UserTokenWallet.organization_name) == canonical_name.lower())
        ).first()

        remaining_tokens = user_wallet.remaining_tokens if user_wallet else 0

        # Check if org is PAYG (PAYG users have unlimited quota and don't need prepaid allocations)
        org_wallet = self.session.query(OrganizationWallet).filter(
            (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == canonical_name.lower())
        ).first()
        if org_wallet and org_wallet.payg_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PAYG_ACTIVE: Organization has PAYG active; user tokens are unlimited."
            )

        if remaining_tokens > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TOKENS_NOT_EXHAUSTED: You still have {remaining_tokens:,} tokens remaining. Top-up requests can only be submitted after complete exhaustion."
            )

        # 2. Check for duplicate pending requests
        existing_pending = self.session.query(UserTokenQuotaRequest).filter(
            UserTokenQuotaRequest.user_id == user_id,
            (UserTokenQuotaRequest.organization_id == org_id) | (func.lower(UserTokenQuotaRequest.organization_name) == canonical_name.lower()),
            UserTokenQuotaRequest.status == UserQuotaRequestStatus.PENDING.value
        ).first()

        if existing_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="PENDING_REQUEST_EXISTS: You already have a pending top-up request under review by your Organization Admin."
            )

        # 3. Create the request
        req = UserTokenQuotaRequest(
            user_id=user_id,
            organization_name=canonical_name,
            organization_id=org_id,
            requested_tokens=requested_tokens,
            reason=reason.strip() if reason else None,
            status=UserQuotaRequestStatus.PENDING.value,
            created_at=datetime.utcnow()
        )
        self.session.add(req)
        self.session.commit()
        self.session.refresh(req)

        logger.info(
            f"User {user_id} submitted top-up request #{req.id} for {requested_tokens:,} tokens "
            f"in org '{canonical_name}'."
        )
        return req

    def get_user_latest_request(
        self,
        user_id: int,
        org_identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the latest token top-up request for the specified user and organization.
        """
        try:
            org_id, org = self.tenant_resolver.resolve(org_identifier)
            canonical_name = org.name
        except Exception:
            return None

        req = self.session.query(UserTokenQuotaRequest).filter(
            UserTokenQuotaRequest.user_id == user_id,
            (UserTokenQuotaRequest.organization_id == org_id) | (func.lower(UserTokenQuotaRequest.organization_name) == canonical_name.lower())
        ).order_by(UserTokenQuotaRequest.created_at.desc()).first()

        if not req:
            return None

        return {
            "id": req.id,
            "requested_tokens": req.requested_tokens,
            "reason": req.reason,
            "status": req.status,
            "admin_notes": req.admin_notes,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        }

    def get_org_requests(
        self,
        org_identifier: str,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lists member token quota top-up requests for an organization.
        """
        org_id, org = self.tenant_resolver.resolve(org_identifier)
        canonical_name = org.name

        query = self.session.query(UserTokenQuotaRequest).filter(
            (UserTokenQuotaRequest.organization_id == org_id) | (func.lower(UserTokenQuotaRequest.organization_name) == canonical_name.lower())
        )

        if status_filter and status_filter.upper() != "ALL":
            query = query.filter(UserTokenQuotaRequest.status == status_filter.upper())

        requests = query.order_by(UserTokenQuotaRequest.created_at.desc()).all()

        # Batch load user details and wallets to avoid n+1 queries
        user_ids = list(set([r.user_id for r in requests if r.user_id]))
        user_map = {}
        if user_ids:
            users = self.session.query(User).filter(User.id.in_(user_ids)).all()
            for u in users:
                name_parts = [u.first_name or "", u.last_name or ""]
                full_name = " ".join([p for p in name_parts if p]).strip() or (u.email.split("@")[0] if u.email else f"User #{u.id}")
                user_map[u.id] = {
                    "name": full_name,
                    "email": u.email
                }

            wallets = self.session.query(UserTokenWallet).filter(
                UserTokenWallet.user_id.in_(user_ids),
                (UserTokenWallet.organization_id == org_id) | (func.lower(UserTokenWallet.organization_name) == canonical_name.lower())
            ).all()
            wallet_map = {w.user_id: w.remaining_tokens for w in wallets}
        else:
            wallet_map = {}

        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": user_map.get(r.user_id, {}).get("name", f"User #{r.user_id}"),
                "user_email": user_map.get(r.user_id, {}).get("email"),
                "current_remaining_tokens": wallet_map.get(r.user_id, 0),
                "requested_tokens": r.requested_tokens,
                "reason": r.reason,
                "status": r.status,
                "admin_notes": r.admin_notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in requests
        ]

    def review_request(
        self,
        request_id: int,
        admin_user_id: int,
        org_identifier: str,
        action: str,
        approved_tokens: Optional[int] = None,
        admin_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reviews (Approves or Rejects) a user token top-up request.
        Upon approval, automatically allocates tokens from the organization reserve to the user wallet.
        """
        org_id, org = self.tenant_resolver.resolve(org_identifier)
        canonical_name = org.name

        req = self.session.query(UserTokenQuotaRequest).filter(
            UserTokenQuotaRequest.id == request_id,
            (UserTokenQuotaRequest.organization_id == org_id) | (func.lower(UserTokenQuotaRequest.organization_name) == canonical_name.lower())
        ).first()

        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="REQUEST_NOT_FOUND: Quota request not found in your organization."
            )

        if req.status != UserQuotaRequestStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"REQUEST_ALREADY_REVIEWED: This request has already been {req.status.lower()}."
            )

        norm_action = action.upper()
        if norm_action not in ("APPROVE", "REJECT"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ACTION: Action must be 'APPROVE' or 'REJECT'."
            )

        if norm_action == "APPROVE":
            tokens_to_give = approved_tokens if (approved_tokens is not None and approved_tokens > 0) else req.requested_tokens
            
            # Instantiate OrgWalletService with all required dependencies
            from tokenops.services.org_admin.org_audit_service import OrgAuditService
            from tokenops.repositories.organization_wallet import OrganizationWalletRepository
            from tokenops.repositories.user_wallet import UserWalletRepository
            from tokenops.services.wallet_service import WalletService
            from tokenops.services.validation_service import ValidationService
            from tokenops.services.ledger_service import LedgerService
            from tokenops.repositories.ledger import LedgerRepository
            from tokenops.services.idempotency_service import IdempotencyService
            from tokenops.repositories.idempotency import IdempotencyRepository
            from tokenops.services.pricing_service import PricingService
            from tokenops.repositories.pricing import PricingRepository

            org_repo = OrganizationWalletRepository(self.session)
            user_repo = UserWalletRepository(self.session)
            validation = ValidationService(org_repo, user_repo)
            ledger_repo = LedgerRepository(self.session)
            ledger = LedgerService(ledger_repo)
            idempotency_repo = IdempotencyRepository(self.session)
            idempotency = IdempotencyService(idempotency_repo)
            pricing_repo = PricingRepository(self.session)
            pricing_service = PricingService(pricing_repo)
            audit_service = OrgAuditService(session=self.session)

            wallet_service = WalletService(self.session, org_repo, user_repo, validation, ledger, idempotency)
            org_wallet_service = OrgWalletService(self.session, wallet_service, audit_service, org_repo, user_repo, pricing_service)

            request_id_str = f"user_quota_req_{req.id}_{uuid.uuid4().hex[:8]}"
            allocation_remarks = f"Approved Member Quota Request #{req.id}: {admin_notes or 'Top-up granted'}"

            try:
                org_wallet_service.allocate_tokens(
                    admin_user_id=admin_user_id,
                    organization_name=canonical_name,
                    request_id=request_id_str,
                    user_id=req.user_id,
                    token_amount=tokens_to_give,
                    remarks=allocation_remarks
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to allocate tokens for approved user request #{req.id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ALLOCATION_FAILED: {str(e)}"
                )

            req.status = UserQuotaRequestStatus.APPROVED.value
            req.reviewed_by = admin_user_id
            req.reviewed_at = datetime.utcnow()
            req.admin_notes = admin_notes or "Approved"
            self.session.commit()

            logger.info(f"Org Admin {admin_user_id} approved user top-up request #{req.id} (+{tokens_to_give:,} tokens).")
        else:
            req.status = UserQuotaRequestStatus.REJECTED.value
            req.reviewed_by = admin_user_id
            req.reviewed_at = datetime.utcnow()
            req.admin_notes = admin_notes or "Rejected"
            self.session.commit()

            logger.info(f"Org Admin {admin_user_id} rejected user top-up request #{req.id}.")

        return {
            "id": req.id,
            "status": req.status,
            "admin_notes": req.admin_notes,
            "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        }
