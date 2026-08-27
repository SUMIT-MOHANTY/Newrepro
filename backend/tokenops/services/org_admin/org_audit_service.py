import json
from typing import Any, Dict
from sqlalchemy.orm import Session
from tokenops.models.audit import AdminAuditLog

class OrgAuditService:
    def __init__(self, session: Session):
        self.session = session

    def log_action(
        self, 
        admin_user_id: int, 
        organization_name: str,
        action: str, 
        target_entity: str, 
        request_id: str = None,
        details: Dict[str, Any] = None
    ):
        """
        Write an audit log for an Org Admin action.
        """
        details_str = json.dumps(details) if details else None
        
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            actor_type="ORG_ADMIN",
            action=action,
            target_entity=target_entity,
            organization_name=organization_name,
            request_id=request_id,
            details=details_str
        )
        self.session.add(audit_entry)
