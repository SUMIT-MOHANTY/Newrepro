"""
Billing & SuperAdmin Repository Layer
Performs cost aggregations, organization capacity updates, and billing log retrieval.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import Agent, CapacityIncreaseRequest, OrganizationAgentQuota
from app.models.billing import AIUsageLog, DailyBillingEmailLog
from app.models.user import User
from app.repositories.base import BaseRepository


class BillingRepository(BaseRepository[DailyBillingEmailLog, Any, Any]):
    def __init__(self):
        super().__init__(DailyBillingEmailLog)

    def get_platform_dashboard_stats(self, db: Session) -> Dict[str, Any]:
        """Aggregate platform-wide high-level metrics for SuperAdmin dashboard."""
        total_users = db.query(User).count()
        total_orgs = (
            db.query(User.organization_name)
            .filter(User.organization_name.isnot(None))
            .distinct()
            .count()
        )
        total_agents = db.query(Agent).count() if Agent else 0
        pending_requests = (
            db.query(CapacityIncreaseRequest)
            .filter(CapacityIncreaseRequest.status == "pending")
            .count()
            if CapacityIncreaseRequest
            else 0
        )

        # AI Usage Aggregates
        usage_query = db.query(
            func.sum(AIUsageLog.cost),
            func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens),
        ).first()

        total_cost = float(usage_query[0] or 0.0)
        total_tokens = int(usage_query[1] or 0)

        return {
            "total_organizations": total_orgs,
            "total_onboarded_agents": total_agents,
            "running_docker_containers": 0,
            "dedicated_agents": 0,
            "shared_agents": total_agents,
            "borrowed_dedicated_agents": 0,
            "pending_capacity_requests": pending_requests,
            "organization_billing": total_cost,
            "ai_token_usage": total_tokens,
            "project_statistics": {},
            "active_users": total_users,
            "agent_utilization": 0.0,
        }

    def list_organization_costs(self, db: Session) -> List[Dict[str, Any]]:
        """Group and sum AI consumption metrics by organization."""
        results = (
            db.query(
                AIUsageLog.organization_name,
                func.sum(AIUsageLog.cost).label("total_cost"),
                func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens).label("total_tokens"),
                func.count(AIUsageLog.id).label("total_requests"),
            )
            .filter(AIUsageLog.organization_name.isnot(None))
            .group_by(AIUsageLog.organization_name)
            .all()
        )

        summaries = []
        for r in results:
            quota = (
                db.query(OrganizationAgentQuota)
                .filter(OrganizationAgentQuota.organization_name == r[0])
                .first()
            )
            users_count = (
                db.query(User)
                .filter(User.organization_name == r[0])
                .count()
            )
            summaries.append({
                "organization_name": r[0],
                "total_cost": float(r[1] or 0.0),
                "total_tokens": int(r[2] or 0),
                "total_requests": int(r[3] or 0),
                "active_users_count": users_count,
                "agent_capacity": quota.max_agent_capacity if quota else 10,
            })
        return summaries

    # ── Capacity Increase Requests ──────────────────────────────────────────────

    def list_capacity_requests(
        self,
        db: Session,
        status: Optional[str] = None,
    ) -> List[CapacityIncreaseRequest]:
        """Fetch all organization capacity increase requests."""
        query = db.query(CapacityIncreaseRequest)
        if status:
            query = query.filter(CapacityIncreaseRequest.status == status)
        return query.order_by(CapacityIncreaseRequest.created_at.desc()).all()

    def get_capacity_request(
        self,
        db: Session,
        request_id: int,
    ) -> Optional[CapacityIncreaseRequest]:
        """Fetch a specific capacity increase request by ID."""
        return (
            db.query(CapacityIncreaseRequest)
            .filter(CapacityIncreaseRequest.id == request_id)
            .first()
        )

    def review_capacity_request(
        self,
        db: Session,
        request_id: int,
        status: str,
        reviewer_id: int,
        approved_capacity: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> Optional[CapacityIncreaseRequest]:
        """Record SuperAdmin approval or rejection of an org capacity request."""
        req = self.get_capacity_request(db, request_id)
        if not req:
            return None

        req.status = status
        req.reviewed_by_user_id = reviewer_id
        req.review_comment = comment
        if approved_capacity is not None:
            req.approved_total_capacity = approved_capacity
        req.updated_at = datetime.utcnow()

        if status == "approved" and approved_capacity:
            self.update_organization_capacity(db, req.organization_name, approved_capacity)

        db.commit()
        db.refresh(req)
        return req

    def update_organization_capacity(
        self,
        db: Session,
        org_name: str,
        new_capacity: int,
    ) -> Optional[OrganizationAgentQuota]:
        """Directly adjust organization agent capacity cap."""
        quota = (
            db.query(OrganizationAgentQuota)
            .filter(OrganizationAgentQuota.organization_name == org_name)
            .first()
        )
        if not quota:
            quota = OrganizationAgentQuota(
                organization_name=org_name,
                max_agent_capacity=new_capacity,
                shared_quota=new_capacity,
                dedicated_quota=0,
                shared_dev_quota=new_capacity // 2,
                shared_test_quota=new_capacity // 2,
                dedicated_dev_quota=0,
                dedicated_test_quota=0,
                updated_at=datetime.utcnow(),
            )
            db.add(quota)
        else:
            quota.max_agent_capacity = new_capacity
            quota.shared_quota = new_capacity
            quota.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(quota)
        return quota

    # ── Daily Billing Email Logs ────────────────────────────────────────────────

    def list_daily_billing_logs(
        self,
        db: Session,
        user_id: Optional[int] = None,
        date_key: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[DailyBillingEmailLog]:
        """Query dispatched daily billing email audit records."""
        query = db.query(DailyBillingEmailLog)
        if user_id:
            query = query.filter(DailyBillingEmailLog.user_id == user_id)
        if date_key:
            query = query.filter(DailyBillingEmailLog.date_key == date_key)
        return query.order_by(DailyBillingEmailLog.sent_at.desc()).offset(skip).limit(limit).all()


billing_repository = BillingRepository()
