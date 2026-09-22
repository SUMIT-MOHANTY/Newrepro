"""
SuperAdmin & Billing Service Layer
Business logic for SuperAdmin dashboard telemetry, organization capacity governance,
and billing email execution.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.agent import CapacityIncreaseRequest, OrganizationAgentQuota
from app.models.user import User
from app.repositories.billing_repository import billing_repository
from app.schemas.billing import (
    SuperAdminDashboardStatsResponse,
    SuperAdminCapUpdate,
    CapacityIncreaseRequestReview,
    OrganizationCostSummary,
)
from app.workers.daily_billing_worker import daily_billing_worker

logger = logging.getLogger(__name__)


class SuperAdminService:
    def __init__(self):
        self.repo = billing_repository
        self.billing_worker = daily_billing_worker

    def assert_super_admin(self, user: User) -> None:
        """Enforce strict SuperAdmin authorization."""
        if not getattr(user, "is_super_admin", False):
            raise ForbiddenException("SuperAdmin privileges are required for this action")

    def get_dashboard_stats(self, db: Session, user: User) -> SuperAdminDashboardStatsResponse:
        self.assert_super_admin(user)
        stats = self.repo.get_platform_dashboard_stats(db)
        return SuperAdminDashboardStatsResponse(**stats)

    def list_organizations(self, db: Session, user: User) -> List[OrganizationCostSummary]:
        self.assert_super_admin(user)
        raw_summaries = self.repo.list_organization_costs(db)
        return [OrganizationCostSummary(**s) for s in raw_summaries]

    def update_organization_capacity(
        self,
        db: Session,
        user: User,
        org_name: str,
        payload: SuperAdminCapUpdate,
    ) -> OrganizationAgentQuota:
        self.assert_super_admin(user)
        if payload.max_agent_capacity <= 0:
            raise ValidationException("Agent capacity must be a positive integer")

        quota = self.repo.update_organization_capacity(db, org_name, payload.max_agent_capacity)
        return quota

    def list_capacity_requests(
        self,
        db: Session,
        user: User,
        status: Optional[str] = None,
    ) -> List[CapacityIncreaseRequest]:
        self.assert_super_admin(user)
        return self.repo.list_capacity_requests(db, status=status)

    def review_capacity_request(
        self,
        db: Session,
        user: User,
        request_id: int,
        action: str,  # 'approve' or 'reject'
        review_data: Optional[CapacityIncreaseRequestReview] = None,
    ) -> CapacityIncreaseRequest:
        self.assert_super_admin(user)
        if action not in ["approve", "reject"]:
            raise ValidationException(f"Invalid review action '{action}'")

        status = "approved" if action == "approve" else "rejected"
        approved_capacity = review_data.approved_capacity if review_data else None
        comment = review_data.comment if review_data else None

        req = self.repo.review_capacity_request(
            db=db,
            request_id=request_id,
            status=status,
            reviewer_id=user.id,
            approved_capacity=approved_capacity,
            comment=comment,
        )
        if not req:
            raise NotFoundException(f"Capacity request {request_id} not found")
        return req

    # ── Daily Billing Controls & Triggers ───────────────────────────────────────

    def get_email_controls(self, user: User) -> Dict[str, Any]:
        self.assert_super_admin(user)
        return self.billing_worker.get_controls()

    def update_email_controls(self, user: User, controls: Dict[str, Any]) -> Dict[str, Any]:
        self.assert_super_admin(user)
        success = self.billing_worker.update_controls(controls)
        return {"success": success, "controls": controls}

    async def trigger_billing_emails(self, db: Session, user: User) -> Dict[str, Any]:
        self.assert_super_admin(user)
        return await self.billing_worker.trigger_dispatch(db)


superadmin_service = SuperAdminService()
