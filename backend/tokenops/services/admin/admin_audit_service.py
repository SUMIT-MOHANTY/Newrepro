import json
from typing import Any, Dict
from sqlalchemy.orm import Session
from tokenops.models.audit import AdminAuditLog

class AdminAuditService:
    def __init__(self, session: Session):
        self.session = session

    def log_action(
        self, 
        admin_user_id: int, 
        action: str, 
        target_entity: str, 
        details: Dict[str, Any] = None,
        actor_type: str = "SUPER_ADMIN",
        organization_name: str = None,
        request_id: str = None
    ):
        """
        Write an audit log for an admin action.
        """
        details_str = json.dumps(details) if details else None
        
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            actor_type=actor_type,
            action=action,
            target_entity=target_entity,
            organization_name=organization_name,
            request_id=request_id,
            details=details_str
        )
        self.session.add(audit_entry)
        # Assuming the caller will commit the transaction
