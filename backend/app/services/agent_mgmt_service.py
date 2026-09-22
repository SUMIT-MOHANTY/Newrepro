"""
Agent & Orchestration Service Layer
Encapsulates business logic for agent lifecycle, note management, capacity quotas,
AI assistant chat, and multi-agent coordination.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.integrations.llm.gateway import llm_gateway
from app.models.agent import Agent, AgentNote, ProjectAgentRequest, OrganizationAgentQuota, CapacityIncreaseRequest
from app.repositories.agent_repository import agent_repository
from app.schemas.agent import (
    AgentNoteCreate,
    ProjectAgentRequestCreate,
    CapacityIncreaseRequestCreate,
    AssistantChatRequest,
    AssistantChatResponse,
)
from app.workers.container_pool import container_pool_worker
from app.workers.job_manager import analysis_job_worker

try:
    from agent_coordination_service import coordination_service
except ImportError:
    coordination_service = None

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self):
        self.repo = agent_repository
        self.llm = llm_gateway
        self.pool = container_pool_worker
        self.jobs = analysis_job_worker
        self.coordination = coordination_service

    # ── Agent Queries ───────────────────────────────────────────────────────────

    def get_agent(self, db: Session, agent_id: str) -> Agent:
        agent = self.repo.get_by_id(db, agent_id)
        if not agent:
            raise NotFoundException(f"Agent '{agent_id}' not found")
        return agent

    def list_agents(self, db: Session, project_token: Optional[str] = None) -> List[Agent]:
        return self.repo.list_by_project(db, project_token)

    # ── Notes Management ────────────────────────────────────────────────────────

    def get_project_notes(self, db: Session, project_token: str) -> List[AgentNote]:
        return self.repo.list_notes(db, project_token)

    def add_project_note(
        self,
        db: Session,
        payload: AgentNoteCreate,
        user_email: Optional[str] = None,
    ) -> AgentNote:
        return self.repo.create_note(
            db=db,
            project_token=payload.project_token,
            title=payload.title,
            content_text=payload.content,
            user=user_email,
            content_payload={"category": payload.category, "agent_id": payload.agent_id, "task_id": payload.task_id},
        )

    # ── Quotas & Requests ───────────────────────────────────────────────────────

    def get_organization_quota(self, db: Session, organization_name: str) -> OrganizationAgentQuota:
        return self.repo.get_or_create_quota(db, organization_name)

    def create_project_agent_request(
        self,
        db: Session,
        organization_name: str,
        user_id: int,
        payload: ProjectAgentRequestCreate,
    ) -> ProjectAgentRequest:
        if payload.requested_shared_count <= 0 and payload.requested_dedicated_count <= 0:
            raise ValidationException("Must request at least 1 shared or dedicated agent")

        return self.repo.create_project_request(
            db=db,
            organization_name=organization_name,
            project_token=payload.project_token,
            user_id=user_id,
            requested_shared=payload.requested_shared_count,
            requested_dedicated=payload.requested_dedicated_count,
            reason=payload.reason,
        )

    def list_project_agent_requests(
        self,
        db: Session,
        organization_name: str,
        status: Optional[str] = None,
    ) -> List[ProjectAgentRequest]:
        return self.repo.list_project_requests(db, organization_name, status=status)

    def review_project_agent_request(
        self,
        db: Session,
        request_id: int,
        action: str,
        reviewer_id: int,
        comment: Optional[str] = None,
    ) -> ProjectAgentRequest:
        valid_actions = ["approve", "reject", "escalate"]
        if action not in valid_actions:
            raise ValidationException(f"Invalid action '{action}'. Must be one of {valid_actions}")

        status_mapping = {
            "approve": "approved",
            "reject": "rejected",
            "escalate": "escalated",
        }
        req = self.repo.update_project_request_status(
            db=db,
            request_id=request_id,
            status=status_mapping[action],
            reviewed_by_user_id=reviewer_id,
            review_comment=comment,
        )
        if not req:
            raise NotFoundException(f"Project request {request_id} not found")
        return req

    def create_capacity_increase_request(
        self,
        db: Session,
        user_id: int,
        payload: CapacityIncreaseRequestCreate,
    ) -> CapacityIncreaseRequest:
        return self.repo.create_capacity_increase_request(
            db=db,
            organization_name=payload.organization_name,
            user_id=user_id,
            project_token=payload.project_token,
            shared_count=payload.requested_shared_count,
            dedicated_count=payload.requested_dedicated_count,
            total_increase=payload.total_requested_increase,
            reason=payload.reason,
        )

    # ── AI Assistant & Chat ─────────────────────────────────────────────────────

    async def chat_with_assistant(
        self,
        payload: AssistantChatRequest,
        user_id: Optional[int] = None,
    ) -> AssistantChatResponse:
        system_prompt = (
            "You are the DSuite AI Multi-Agent Engineering Assistant. You assist engineers, architects, "
            "and project leads in designing, reviewing, deploying, and inspecting multi-agent workflows, "
            "code changes, and system architectures. Provide concise, expert, and actionable responses."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for item in payload.history[-6:]:
            messages.append(item)
        messages.append({"role": "user", "content": payload.message})

        reply = await self.llm.complete(
            messages=messages,
            purpose="agent_assistant_chat",
            project_token=payload.project_token,
        )

        return AssistantChatResponse(
            reply=reply,
            agent_id=payload.agent_id,
            project_token=payload.project_token,
        )

    # ── Multi-Agent Coordination ────────────────────────────────────────────────

    async def get_coordination_status(self, project_token: str) -> Dict[str, Any]:
        if not self.coordination:
            return {
                "project_token": project_token,
                "agents": {},
                "shared_context": {},
                "file_locks": {},
                "sync_points": {},
                "communication_log": [],
                "phase_gates": {},
            }
        state = await self.coordination.get_coordination_state(project_token)
        return state or {
            "project_token": project_token,
            "agents": {},
            "shared_context": {},
            "file_locks": {},
            "sync_points": {},
            "communication_log": [],
            "phase_gates": {},
        }


agent_service = AgentService()
