"""
Agent & Orchestration Schemas (DTOs)
Strict validation and serialization for multi-agent execution, coordination, and capacity management.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Agent Core Schemas ────────────────────────────────────────────────────────

class AgentBase(BaseModel):
    name: str
    role: str
    kind: str = "shared"  # 'shared' or 'dedicated'
    subtype: str = "development"  # 'development' or 'testing'
    status: str = "idle"  # 'idle', 'busy', 'blocked', 'done', 'error'
    current_task: Optional[str] = None


class AgentResponse(AgentBase):
    id: str
    project_token: Optional[str] = None
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True
        from_attributes = True


class AgentStatusUpdate(BaseModel):
    status: str
    current_task: Optional[str] = None
    progress: Optional[int] = None
    message: Optional[str] = None


# ── Agent Notes ───────────────────────────────────────────────────────────────

class AgentNoteCreate(BaseModel):
    agent_id: str
    project_token: str
    title: str
    content: str
    category: Optional[str] = "general"
    task_id: Optional[str] = None


class AgentNoteResponse(BaseModel):
    id: int
    agent_id: str
    project_token: str
    title: str
    content: str
    category: str
    task_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True


# ── Project Agent Quota & Requests ────────────────────────────────────────────

class ProjectAgentRequestCreate(BaseModel):
    project_token: str
    requested_shared_count: int = 0
    requested_dedicated_count: int = 0
    reason: Optional[str] = None


class ProjectAgentRequestAction(BaseModel):
    action: str  # 'approve', 'reject', 'escalate'
    reason: Optional[str] = None


class ProjectAgentRequestResponse(BaseModel):
    id: int
    project_token: str
    organization_name: str
    requested_by_user_id: int
    requested_shared_count: int
    requested_dedicated_count: int
    reason: Optional[str] = None
    status: str  # 'pending', 'approved', 'rejected', 'escalated'
    reviewed_by_user_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True


class CapacityIncreaseRequestCreate(BaseModel):
    organization_name: str
    project_token: Optional[str] = None
    requested_shared_count: int = 0
    requested_dedicated_count: int = 0
    total_requested_increase: int = 1
    reason: Optional[str] = None


class CapacityIncreaseRequestResponse(BaseModel):
    id: int
    organization_name: str
    requested_by_user_id: int
    project_token: Optional[str] = None
    requested_shared_count: int = 0
    requested_dedicated_count: int = 0
    total_requested_increase: int = 1
    reason: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True


class OrganizationAgentQuotaResponse(BaseModel):
    organization_name: str
    max_agent_capacity: int = 0
    total_onboarded_agents: int = 0
    physical_workers_onboarded: int = 0
    virtual_shared_onboarded: int = 0
    available_capacity: int = 0
    shared_quota: int = 0
    dedicated_quota: int = 0
    shared_used: int = 0
    dedicated_used: int = 0
    shared_available: int = 0
    dedicated_available: int = 0
    shared_dev_quota: int = 0
    shared_test_quota: int = 0
    dedicated_dev_quota: int = 0
    dedicated_test_quota: int = 0
    shared_dev_used: int = 0
    shared_test_used: int = 0
    dedicated_dev_used: int = 0
    dedicated_test_used: int = 0
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True


class OrganizationAgentQuotaIncreaseRequest(BaseModel):
    additional_capacity: int = Field(..., gt=0)
    reason: Optional[str] = None


# ── Multi-Agent Coordination Schemas ──────────────────────────────────────────

class CoordinationStatusResponse(BaseModel):
    project_token: str
    agents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    shared_context: Dict[str, Any] = Field(default_factory=dict)
    file_locks: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    sync_points: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    communication_log: List[Dict[str, Any]] = Field(default_factory=list)
    phase_gates: Dict[str, bool] = Field(default_factory=dict)


class RunCoordinatedAgentsRequest(BaseModel):
    project_token: str
    agents_config: Dict[str, Dict[str, str]]
    task_token: Optional[str] = None


class SendMessageRequest(BaseModel):
    project_token: str
    sender_id: str
    recipient_id: str
    message_type: str
    payload: Dict[str, Any]


# ── AI Assistant & Chat Schemas ───────────────────────────────────────────────

class AssistantChatRequest(BaseModel):
    message: str
    project_token: Optional[str] = None
    agent_id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    reply: str
    agent_id: Optional[str] = None
    project_token: Optional[str] = None
    tokens_used: Optional[int] = None
