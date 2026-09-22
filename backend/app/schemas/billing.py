"""
Billing & SuperAdmin Schemas (DTOs)
Contracts for SuperAdmin platform telemetry, billing log audits, capacity approvals, and daily email scheduling.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SuperAdminDashboardStatsResponse(BaseModel):
    total_organizations: int = 0
    total_onboarded_agents: int = 0
    running_docker_containers: int = 0
    dedicated_agents: int = 0
    shared_agents: int = 0
    borrowed_dedicated_agents: int = 0
    pending_capacity_requests: int = 0
    organization_billing: float = 0.0
    ai_token_usage: int = 0
    project_statistics: Dict[str, Any] = Field(default_factory=dict)
    active_users: int = 0
    agent_utilization: float = 0.0


class SuperAdminCapUpdate(BaseModel):
    max_agent_capacity: int = Field(..., gt=0)


class CapacityIncreaseRequestReview(BaseModel):
    approved_capacity: Optional[int] = None
    comment: Optional[str] = None


class DailyBillingEmailLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    email: str
    date_key: str
    sent_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    total_tokens: int = 0
    total_cost: float = 0.0
    is_admin_report: bool = False
    cc_recipients: Optional[str] = None

    class Config:
        from_attributes = True


class OrganizationCostSummary(BaseModel):
    organization_name: str
    total_cost: float
    total_tokens: int
    total_requests: int
    active_users_count: int
    agent_capacity: int


class BillingEmailControls(BaseModel):
    scheduler: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    super_user: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    routing: Optional[Dict[str, Any]] = None
    profiles: Optional[Dict[str, Any]] = None


class BillingTriggerResponse(BaseModel):
    message: str
    success: bool
    details: Optional[Dict[str, Any]] = None
