from sqlalchemy.orm import Session
from fastapi import HTTPException
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.models.token_wallet import UserTokenWallet
from tokenops.models.token_wallet import UserOrganization
from models import UserOrganizationRole, OrganizationRole
from tokenops.utils.retry import retry_on_lock

class OrgGovernanceService:
    def __init__(
        self,
        session: Session,
        audit_service: OrgAuditService
    ):
        self.session = session
        self.audit_service = audit_service

    def _tx(self):
        if self.session.in_transaction():
            return self.session.begin_nested()
        return self.session.begin()

    @retry_on_lock(max_retries=3)
    def set_user_block_status(self, admin_user_id: int, organization_name: str, user_id: int, is_blocked: bool):
        with self._tx():
            # Check if target is an org admin
            role_mapping = self.session.query(UserOrganizationRole).join(OrganizationRole).filter(
                UserOrganizationRole.user_id == user_id,
                UserOrganizationRole.organization_name == organization_name,
                OrganizationRole.name == "ORG_ADMIN"
            ).first()
            
            if role_mapping:
                raise HTTPException(status_code=403, detail="Cannot block another Organization Admin")

            # Check if wallet exists
            wallet = self.session.query(UserTokenWallet).filter_by(
                user_id=user_id, organization_name=organization_name
            ).first()
            
            if not wallet:
                raise HTTPException(status_code=404, detail="User wallet not found in this organization")
                
            wallet.is_blocked = is_blocked
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                organization_name=organization_name,
                action="BLOCK_USER" if is_blocked else "UNBLOCK_USER",
                target_entity=str(user_id)
            )
