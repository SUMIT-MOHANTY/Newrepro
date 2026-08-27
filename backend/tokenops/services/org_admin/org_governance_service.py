from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.models.token_wallet import UserTokenWallet
from tokenops.models.token_wallet import UserOrganization
from models import User, UserOrganizationRole, OrganizationRole
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
            # 1. Prevent self-block
            if user_id == admin_user_id:
                raise HTTPException(status_code=403, detail="Cannot block an Organization Admin")

            # 2. Check explicit RBAC role mapping in this organization first
            role_mapping = self.session.query(UserOrganizationRole).join(OrganizationRole).filter(
                UserOrganizationRole.user_id == user_id,
                func.lower(UserOrganizationRole.organization_name) == organization_name.lower()
            ).first()

            if role_mapping:
                # If RBAC mapping exists for this organization, it is authoritative
                role = self.session.query(OrganizationRole).filter(OrganizationRole.id == role_mapping.role_id).first()
                if role and (role.name in ["ORG_ADMIN", "Admin", "admin"] or "admin" in role.name.lower()):
                    raise HTTPException(status_code=403, detail="Cannot block another Organization Admin")
            else:
                # 3. Backward-compatible fallback: check legacy native user record if no RBAC mapping exists
                target_user = self.session.query(User).filter(User.id == user_id).first()
                if target_user and bool(getattr(target_user, "is_org_admin", False)) and (
                    target_user.organization_name and target_user.organization_name.lower() == organization_name.lower()
                ):
                    raise HTTPException(status_code=403, detail="Cannot block another Organization Admin")

            # 4. Check if wallet exists in this organization (case-insensitive)
            wallet = self.session.query(UserTokenWallet).filter(
                UserTokenWallet.user_id == user_id,
                func.lower(UserTokenWallet.organization_name) == organization_name.lower()
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
