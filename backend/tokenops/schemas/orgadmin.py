from pydantic import BaseModel
from typing import List, Optional, Any

# Inherit the BaseAPIResponse format or redefine it locally for consistency
class ErrorDetail(BaseModel):
    code: str
    message: str

class BaseAPIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None

# Users
class UserWalletView(BaseModel):
    user_id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = "member"
    allocated_tokens: int
    consumed_tokens: int
    remaining_tokens: int
    is_blocked: bool
    reference_price: float

class PaginatedUserWalletResponse(BaseModel):
    items: List[UserWalletView]
    total: int
    page: int
    size: int

# Allocation
class AllocateRequest(BaseModel):
    request_id: Optional[str] = None
    user_id: int
    token_amount: int
    remarks: Optional[str] = None

class ReallocateRequest(BaseModel):
    request_id: Optional[str] = None
    source_user_id: int
    destination_user_id: int
    token_amount: int

class RevokeRequest(BaseModel):
    request_id: Optional[str] = None
    user_id: int
    token_amount: int

# Reserve
class ReserveWalletView(BaseModel):
    organization_name: str
    purchased_tokens: int
    reserved_tokens: int
    allocated_tokens: int # Derived from SUM(user_token_wallet.allocated_tokens) for org
    consumed_tokens: int
    remaining_tokens: int
    reference_price: float
    payg_enabled: bool = False
    payg_soft_limit_usd: Optional[float] = None
    payg_hard_limit_usd: Optional[float] = None
    payg_current_spend_usd: Optional[float] = 0.0

# Governance
class BlockUserRequest(BaseModel):
    user_id: int

# Analytics
class OrgKPIView(BaseModel):
    total_users: int
    active_users: int
    reserved_tokens: int
    remaining_tokens: int
    consumed_tokens: int
    total_requests: int

class TopUserView(BaseModel):
    user_id: int
    total_tokens: int
    total_cost: float
    request_count: int

# Reports
class DailyUsageView(BaseModel):
    date: str
    tokens: int
    requests: int

class UsageReportView(BaseModel):
    organization_name: str
    daily_usage: List[DailyUsageView]

class UserConsumptionView(BaseModel):
    user_id: int
    total_tokens: int
    total_cost: float

class FinancialLedgerView(BaseModel):
    transaction_id: int
    user_id: Optional[int]
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    transaction_type: str
    purpose: Optional[str] = None
    project_token: Optional[str] = None
    project_name: Optional[str] = None
    token_delta: int
    balance_after: Optional[int] = None
    cost_usd: Optional[float] = None
    payg_cost_usd: Optional[float] = None
    created_at: str
    reference_id: Optional[str]
    remarks: Optional[str]

class PaginatedLedgerResponse(BaseModel):
    items: List[FinancialLedgerView]
    total: int
    page: int
    size: int
