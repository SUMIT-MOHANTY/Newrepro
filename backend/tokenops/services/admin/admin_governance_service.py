from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.models.payg import PAYGRequest, PAYGStatus
from tokenops.models.quota_request import TokenQuotaRequest, QuotaRequestType, QuotaRequestStatus
from tokenops.services.wallet_service import WalletService
from tokenops.utils.retry import retry_on_lock

UNSET = object()

class AdminGovernanceService:
    def __init__(
        self,
        session: Session,
        audit_service: AdminAuditService,
        org_repo: OrganizationWalletRepository,
        user_repo: UserWalletRepository,
        wallet_service: WalletService | None = None
    ):
        self.session = session
        self.audit_service = audit_service
        self.org_repo = org_repo
        self.user_repo = user_repo
        self.wallet_service = wallet_service

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

    @retry_on_lock(max_retries=3)
    def set_organization_block_status(self, admin_user_id: int, organization_name: str, is_blocked: bool):
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.models.token_wallet import OrganizationWallet
        from sqlalchemy import func

        resolver = TenantResolverService(self.session)
        with self._tx():
            org_id, org = resolver.resolve(organization_name)
            wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == org.name.lower())
            ).first()

            if not wallet:
                wallet = OrganizationWallet(
                    id=org_id,
                    organization_name=org.name,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False,
                )
                self.session.add(wallet)
                self.session.flush()

            wallet.is_blocked = is_blocked

            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="BLOCK_ORG" if is_blocked else "UNBLOCK_ORG",
                target_entity=org.name
            )
        self.session.commit()

    @retry_on_lock(max_retries=3)
    def set_user_block_status(self, admin_user_id: int, user_id: int, organization_name: str, is_active: bool):
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.models.token_wallet import UserOrganization
        from sqlalchemy import func

        resolver = TenantResolverService(self.session)
        with self._tx():
            org_id, org = resolver.resolve(organization_name)
            membership = self.session.query(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                func.lower(UserOrganization.organization_name) == org.name.lower()
            ).first()

            if not membership:
                raise HTTPException(status_code=404, detail="User membership not found")

            membership.is_active = is_active

            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="UNBLOCK_USER" if is_active else "BLOCK_USER",
                target_entity=f"{user_id}@{org.name}"
            )
        self.session.commit()

    def get_payg_requests(self):
        return self.session.query(PAYGRequest).filter(
            PAYGRequest.status == PAYGStatus.REQUESTED.value
        ).all()

    @retry_on_lock(max_retries=3)
    def handle_payg_request(self, admin_user_id: int, organization_name: str, approve: bool, remarks: str = None):
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.models.token_wallet import OrganizationWallet
        from sqlalchemy import func

        resolver = TenantResolverService(self.session)
        with self._tx():
            org_id, org = resolver.resolve(organization_name)
            wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == org.name.lower())
            ).first()

            if not wallet:
                wallet = OrganizationWallet(
                    id=org_id,
                    organization_name=org.name,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False,
                )
                self.session.add(wallet)
                self.session.flush()

            req = self.session.query(PAYGRequest).filter(
                func.lower(PAYGRequest.organization_name) == org.name.lower(),
                PAYGRequest.status == PAYGStatus.REQUESTED.value
            ).first()

            # Allow approval even if no request exists for flexibility, or require it
            if req:
                req.status = PAYGStatus.APPROVED.value if approve else PAYGStatus.REJECTED.value

            if approve:
                wallet.payg_enabled = True

            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="APPROVE_PAYG" if approve else "REJECT_PAYG",
                target_entity=org.name,
                details={"remarks": remarks}
            )
        self.session.commit()

    @retry_on_lock(max_retries=3)
    def suspend_payg(self, admin_user_id: int, organization_name: str):
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.models.token_wallet import OrganizationWallet
        from sqlalchemy import func

        resolver = TenantResolverService(self.session)
        with self._tx():
            org_id, org = resolver.resolve(organization_name)
            wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == org.name.lower())
            ).first()

            if not wallet:
                wallet = OrganizationWallet(
                    id=org_id,
                    organization_name=org.name,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False,
                )
                self.session.add(wallet)
                self.session.flush()

            wallet.payg_enabled = False

            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="SUSPEND_PAYG",
                target_entity=org.name
            )
        self.session.commit()

    @retry_on_lock(max_retries=3)
    def set_payg_limits(
        self,
        admin_user_id: int,
        organization_name: str,
        soft_limit_usd: Any = UNSET,
        hard_limit_usd: Any = UNSET,
        billing_email: Any = UNSET
    ):
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.models.token_wallet import OrganizationWallet
        from decimal import Decimal
        from sqlalchemy import func

        resolver = TenantResolverService(self.session)
        with self._tx():
            org_id, org = resolver.resolve(organization_name)
            wallet = self.session.query(OrganizationWallet).filter(
                (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == org.name.lower())
            ).first()
            if not wallet:
                wallet = OrganizationWallet(
                    id=org_id,
                    organization_name=org.name,
                    purchased_tokens=0,
                    remaining_tokens=0,
                    reserved_tokens=0,
                    payg_enabled=False,
                    is_blocked=False,
                )
                self.session.add(wallet)
                self.session.flush()

            if soft_limit_usd is not UNSET:
                wallet.payg_soft_limit_usd = Decimal(str(round(soft_limit_usd, 2))) if soft_limit_usd is not None else None
            if hard_limit_usd is not UNSET:
                wallet.payg_hard_limit_usd = Decimal(str(round(hard_limit_usd, 2))) if hard_limit_usd is not None else None
            if billing_email is not UNSET:
                wallet.payg_billing_email = billing_email.strip() if billing_email is not None else None

            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="UPDATE_PAYG_LIMITS",
                target_entity=org.name,
                details={
                    "soft_limit_usd": float(wallet.payg_soft_limit_usd) if wallet.payg_soft_limit_usd else None,
                    "hard_limit_usd": float(wallet.payg_hard_limit_usd) if wallet.payg_hard_limit_usd else None,
                    "billing_email": wallet.payg_billing_email
                }
            )
        self.session.commit()
        return wallet

    def get_quota_requests(self, status: str = None):
        query = self.session.query(TokenQuotaRequest)
        if status:
            query = query.filter(TokenQuotaRequest.status == status)
        return query.order_by(TokenQuotaRequest.created_at.desc()).all()

    @retry_on_lock(max_retries=3)
    def handle_quota_request(self, admin_user_id: int, request_id: int, approve: bool, remarks: str = None):
        with self._tx():
            req = self.session.query(TokenQuotaRequest).filter(
                TokenQuotaRequest.id == request_id
            ).first()
            if not req:
                raise HTTPException(status_code=404, detail="Quota request not found")

            if req.status != QuotaRequestStatus.REQUESTED.value and req.status != QuotaRequestStatus.REQUESTED:
                raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

            if approve:
                if req.request_type == QuotaRequestType.TOKEN_INCREASE.value or req.request_type == QuotaRequestType.TOKEN_INCREASE:
                    # Inject tokens into organization wallet reserve and record in ledger
                    if self.wallet_service and req.requested_tokens > 0:
                        self.wallet_service.purchase_tokens(
                            organization_name=req.organization_name,
                            amount=req.requested_tokens,
                            request_id=f"quota_req_{req.id}",
                            remarks=f"Approved Quota Request #{req.id}: {remarks or ''}"
                        )
                elif req.request_type == QuotaRequestType.PAYG_ENABLEMENT.value or req.request_type == QuotaRequestType.PAYG_ENABLEMENT:
                    wallet = self.org_repo.get_or_create(req.organization_name)
                    wallet.payg_enabled = True
                elif req.request_type == QuotaRequestType.LIMIT_INCREASE.value or req.request_type == QuotaRequestType.LIMIT_INCREASE:
                    wallet = self.org_repo.get_or_create(req.organization_name)
                    if req.requested_limit_usd is not None and req.requested_limit_usd > 0:
                        wallet.payg_hard_limit_usd = req.requested_limit_usd
                elif req.request_type == QuotaRequestType.PAYG_DISABLEMENT.value or req.request_type == QuotaRequestType.PAYG_DISABLEMENT:
                    wallet = self.org_repo.get_or_create(req.organization_name)
                    wallet.payg_enabled = False

                req.status = QuotaRequestStatus.APPROVED.value
                req.approved_by = admin_user_id
                req.approved_at = datetime.utcnow()
                req.admin_notes = remarks
                self.audit_service.log_action(
                    admin_user_id=admin_user_id,
                    action="APPROVE_QUOTA_REQUEST",
                    target_entity=f"{req.organization_name} (req #{req.id})",
                    details={"tokens": req.requested_tokens, "limit_usd": float(req.requested_limit_usd) if req.requested_limit_usd else None, "type": str(req.request_type), "notes": remarks}
                )
            else:
                req.status = QuotaRequestStatus.REJECTED.value
                req.approved_by = admin_user_id
                req.approved_at = datetime.utcnow()
                req.admin_notes = remarks
                self.audit_service.log_action(
                    admin_user_id=admin_user_id,
                    action="REJECT_QUOTA_REQUEST",
                    target_entity=f"{req.organization_name} (req #{req.id})",
                    details={"tokens": req.requested_tokens, "limit_usd": float(req.requested_limit_usd) if req.requested_limit_usd else None, "type": str(req.request_type), "notes": remarks}
                )
        self.session.commit()
        return req
