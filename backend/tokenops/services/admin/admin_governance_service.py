from sqlalchemy.orm import Session
from fastapi import HTTPException
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.models.payg import PAYGRequest, PAYGStatus
from tokenops.utils.retry import retry_on_lock

class AdminGovernanceService:
    def __init__(
        self,
        session: Session,
        audit_service: AdminAuditService,
        org_repo: OrganizationWalletRepository,
        user_repo: UserWalletRepository
    ):
        self.session = session
        self.audit_service = audit_service
        self.org_repo = org_repo
        self.user_repo = user_repo

    @retry_on_lock(max_retries=3)
    def set_organization_block_status(self, admin_user_id: int, organization_name: str, is_blocked: bool):
        with self.session.begin():
            wallet = self.org_repo.get_by_organization(organization_name)
            if not wallet:
                raise HTTPException(status_code=404, detail="Organization not found")
            
            wallet.is_blocked = is_blocked
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="BLOCK_ORG" if is_blocked else "UNBLOCK_ORG",
                target_entity=organization_name
            )

    @retry_on_lock(max_retries=3)
    def set_user_block_status(self, admin_user_id: int, user_id: int, organization_name: str, is_active: bool):
        with self.session.begin():
            # is_active = False means blocked inside this specific organization
            membership = self.user_repo.get_membership(user_id, organization_name)
            if not membership:
                raise HTTPException(status_code=404, detail="User membership not found")
                
            membership.is_active = is_active
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="UNBLOCK_USER" if is_active else "BLOCK_USER",
                target_entity=f"{user_id}@{organization_name}"
            )

    def get_payg_requests(self):
        return self.session.query(PAYGRequest).filter(
            PAYGRequest.status == PAYGStatus.PENDING.value
        ).all()

    @retry_on_lock(max_retries=3)
    def handle_payg_request(self, admin_user_id: int, organization_name: str, approve: bool, remarks: str = None):
        with self.session.begin():
            wallet = self.org_repo.get_by_organization(organization_name)
            if not wallet:
                raise HTTPException(status_code=404, detail="Organization not found")
                
            req = self.session.query(PAYGRequest).filter(
                PAYGRequest.organization_name == organization_name,
                PAYGRequest.status == PAYGStatus.PENDING.value
            ).first()
            
            # Allow approval even if no request exists for flexibility, or require it
            if req:
                req.status = PAYGStatus.APPROVED.value if approve else PAYGStatus.REJECTED.value
            
            if approve:
                wallet.payg_enabled = True
                
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="APPROVE_PAYG" if approve else "REJECT_PAYG",
                target_entity=organization_name,
                details={"remarks": remarks}
            )

    @retry_on_lock(max_retries=3)
    def suspend_payg(self, admin_user_id: int, organization_name: str):
        with self.session.begin():
            wallet = self.org_repo.get_by_organization(organization_name)
            if not wallet:
                raise HTTPException(status_code=404, detail="Organization not found")
                
            wallet.payg_enabled = False
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="SUSPEND_PAYG",
                target_entity=organization_name
            )
