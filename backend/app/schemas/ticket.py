from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5)
    category: str = "Technical Issue"
    priority: str = "MEDIUM"


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to_user_id: Optional[int] = None


class TicketResolvePayload(BaseModel):
    resolution_summary: Optional[str] = None


class TicketMessageCreate(BaseModel):
    message: str = Field(..., min_length=1)
    is_internal_note: bool = False
    attachments: Optional[list] = None


class TicketSenderInfo(BaseModel):
    id: int
    email: str
    role_name: str = "User"
    is_super_admin: bool = False
    is_org_admin: bool = False
    organization_name: Optional[str] = None

    class Config:
        from_attributes = True


class TicketMessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_user_id: int
    sender: Optional[TicketSenderInfo] = None
    message: str
    is_internal_note: bool = False
    attachments: Optional[list] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TicketResponse(BaseModel):
    id: int
    ticket_code: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    organization_name: Optional[str] = None
    created_by_user_id: int
    created_by: Optional[TicketSenderInfo] = None
    assigned_to_user_id: Optional[int] = None
    assigned_to: Optional[TicketSenderInfo] = None
    resolution_summary: Optional[str] = None
    resolved_by_user_id: Optional[int] = None
    resolved_by: Optional[TicketSenderInfo] = None
    resolved_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    unread: bool = False
    message_count: int = 0
    messages: List[TicketMessageResponse] = Field(default_factory=list)
    can_change_status: bool = False
    can_resolve: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketStatsResponse(BaseModel):
    total: int = 0
    open: int = 0
    in_progress: int = 0
    awaiting_info: int = 0
    resolved: int = 0
    closed: int = 0
    urgent: int = 0
    unread_messages: int = 0


__all__ = [
    "TicketCreate",
    "TicketUpdate",
    "TicketResolvePayload",
    "TicketMessageCreate",
    "TicketSenderInfo",
    "TicketMessageResponse",
    "TicketResponse",
    "TicketStatsResponse",
]
