from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

# Base API Response
class ErrorDetail(BaseModel):
    code: str
    message: str

class BaseAPIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None

# Wallet Schemas

class OrganizationWalletView(BaseModel):
    organization_name: str
    purchased_tokens: int
    consumed_tokens: int
    reserved_tokens: int
    remaining_tokens: int
    payg_enabled: bool
    is_blocked: bool
    reference_price: float

class PaginatedOrganizationResponse(BaseModel):
    items: List[OrganizationWalletView]
    total: int
    page: int
    size: int

class PurchaseRequest(BaseModel):
    organization_name: str
    token_amount: int
    remarks: Optional[str] = None

# Pricing Schemas
class PricingView(BaseModel):
    model_name: str
    price_per_token: float
    is_active: bool

class PricingUpdateRequest(BaseModel):
    price_per_token: float

class NewModelRequest(BaseModel):
    model_name: str
    price_per_token: float

# Blocking Schemas
class BlockOrgRequest(BaseModel):
    organization_name: str

class BlockUserRequest(BaseModel):
    user_id: int
    organization_name: str

# PAYG Schemas
class PAYGRequestView(BaseModel):
    id: int
    organization_name: str
    status: str
    requested_by: Optional[int] = None
    created_at: str

class PAYGDecisionRequest(BaseModel):
    organization_name: str
    remarks: Optional[str] = None

class PAYGLimitsUpdateRequest(BaseModel):
    organization_name: str
    soft_limit_usd: Optional[float] = None
    hard_limit_usd: Optional[float] = None
    billing_email: Optional[str] = None

class GenerateInvoiceRequest(BaseModel):
    organization_name: str
    billing_month: str
    force_regenerate: Optional[bool] = False
    recipient_email: Optional[str] = None
    send_email: Optional[bool] = True

class GenerateMonthlyInvoicesRequest(BaseModel):
    billing_month: Optional[str] = None

class InvoiceLineItem(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    rate_per_token: float
    input_cost: float
    output_cost: float
    total_cost: float

class PAYGInvoiceView(BaseModel):
    id: int
    organization_name: str
    organization_id: Optional[str] = None
    billing_month: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    line_items: Optional[List[Dict[str, Any]]] = None
    invoice_status: str
    recipient_email: Optional[str] = None
    generated_at: str
    paid_at: Optional[str] = None

# Analytics Schemas
class AnalyticsOverview(BaseModel):
    total_organizations: int
    prepaid_organizations: int
    payg_organizations: int
    blocked_organizations: int
    total_tokens_consumed: int
    total_requests: int
    total_historical_cost: float

class DailyUsageView(BaseModel):
    date: str
    tokens: int
    requests: int

class TopUserView(BaseModel):
    user_id: int
    tokens: int

class OrganizationAnalytics(BaseModel):
    organization_name: str
    daily_usage: List[DailyUsageView]
    top_users: List[TopUserView]
    token_burn: int
    remaining_balance: int
    total_historical_cost: float
