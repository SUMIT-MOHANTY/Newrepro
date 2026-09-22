"""
Agent Repository Layer
Handles persistence operations for Agents, AgentNotes, ProjectAgentRequests, Quotas, and Capacity Requests.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.agent import (
    Agent,
    AgentNote,
    ProjectAgentRequest,
    OrganizationAgentQuota,
    CapacityIncreaseRequest,
)
from app.repositories.base import BaseRepository


class AgentRepository(BaseRepository[Agent, Any, Any]):
    def __init__(self):
        super().__init__(Agent)

    def get_by_id(self, db: Session, agent_id: str) -> Optional[Agent]:
        """Fetch an agent by its unique string identifier (e.g. 'architect_01')."""
        return db.query(Agent).filter(Agent.id == agent_id).first()

    def list_by_project(self, db: Session, project_token: Optional[str] = None) -> List[Agent]:
        """List all agents, optionally filtered by project_token."""
        query = db.query(Agent)
        if project_token:
            query = query.filter(Agent.project_token == project_token)
        return query.all()

    def get_or_create(
        self,
        db: Session,
        agent_id: str,
        name: str,
        type: str = "custom",
        project_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Agent:
        """Fetch existing agent or persist a new record if missing."""
        agent = self.get_by_id(db, agent_id)
        if not agent:
            agent = Agent(
                id=agent_id,
                name=name,
                type=type,
                project_token=project_token,
                created_at=datetime.utcnow(),
                **kwargs,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
        return agent

    # ── Notes Management ────────────────────────────────────────────────────────

    def list_notes(self, db: Session, project_token: str) -> List[AgentNote]:
        """List all notes logged for a project workspace."""
        return (
            db.query(AgentNote)
            .filter(AgentNote.project_token == project_token)
            .order_by(AgentNote.created_at.desc())
            .all()
        )

    def create_note(
        self,
        db: Session,
        project_token: str,
        title: str,
        content_text: str,
        user: Optional[str] = None,
        content_payload: Optional[Dict[str, Any]] = None,
    ) -> AgentNote:
        """Create and persist an agent / project note."""
        note = AgentNote(
            project_token=project_token,
            title=title,
            content_text=content_text,
            content_payload=content_payload or {},
            user=user,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note

    # ── Quotas & Project Allocation ─────────────────────────────────────────────

    def get_quota(self, db: Session, organization_name: str) -> Optional[OrganizationAgentQuota]:
        """Fetch the organization agent allocation and physical worker quota."""
        return (
            db.query(OrganizationAgentQuota)
            .filter(OrganizationAgentQuota.organization_name == organization_name)
            .first()
        )

    def get_or_create_quota(
        self,
        db: Session,
        organization_name: str,
        default_capacity: int = 10,
    ) -> OrganizationAgentQuota:
        """Fetch existing quota or initialize default quotas for the organization."""
        quota = self.get_quota(db, organization_name)
        if not quota:
            quota = OrganizationAgentQuota(
                organization_name=organization_name,
                max_agent_capacity=default_capacity,
                shared_quota=default_capacity,
                dedicated_quota=0,
                shared_dev_quota=default_capacity // 2,
                shared_test_quota=default_capacity // 2,
                dedicated_dev_quota=0,
                dedicated_test_quota=0,
                updated_at=datetime.utcnow(),
            )
            db.add(quota)
            db.commit()
            db.refresh(quota)
        return quota

    def create_project_request(
        self,
        db: Session,
        organization_name: str,
        project_token: str,
        user_id: int,
        requested_shared: int,
        requested_dedicated: int,
        reason: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> ProjectAgentRequest:
        """Submit a project agent allocation request to the Org Admin."""
        req = ProjectAgentRequest(
            organization_name=organization_name,
            project_token=project_token,
            project_name=project_name,
            requested_by_user_id=user_id,
            requested_shared_count=requested_shared,
            requested_dedicated_count=requested_dedicated,
            reason=reason,
            status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    def list_project_requests(
        self,
        db: Session,
        organization_name: str,
        status: Optional[str] = None,
    ) -> List[ProjectAgentRequest]:
        """Fetch project agent allocation requests for an organization."""
        query = db.query(ProjectAgentRequest).filter(
            ProjectAgentRequest.organization_name == organization_name
        )
        if status:
            query = query.filter(ProjectAgentRequest.status == status)
        return query.order_by(ProjectAgentRequest.created_at.desc()).all()

    def update_project_request_status(
        self,
        db: Session,
        request_id: int,
        status: str,
        reviewed_by_user_id: int,
        review_comment: Optional[str] = None,
    ) -> Optional[ProjectAgentRequest]:
        """Update request status (approved, rejected, escalated)."""
        req = db.query(ProjectAgentRequest).filter(ProjectAgentRequest.id == request_id).first()
        if req:
            req.status = status
            req.reviewed_by_user_id = reviewed_by_user_id
            req.review_comment = review_comment
            req.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(req)
        return req

    # ── Capacity Increase Requests ──────────────────────────────────────────────

    def create_capacity_increase_request(
        self,
        db: Session,
        organization_name: str,
        user_id: int,
        project_token: Optional[str] = None,
        shared_count: int = 0,
        dedicated_count: int = 0,
        total_increase: int = 1,
        reason: Optional[str] = None,
    ) -> CapacityIncreaseRequest:
        """Org Admin submits request to Super Admin for total physical capacity increase."""
        req = CapacityIncreaseRequest(
            organization_name=organization_name,
            requested_by_user_id=user_id,
            project_token=project_token,
            requested_shared_count=shared_count,
            requested_dedicated_count=dedicated_count,
            total_requested_increase=total_increase,
            reason=reason,
            status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req


agent_repository = AgentRepository()
