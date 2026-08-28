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
    payg_grace_period_months: int
    payg_current_spend_usd: Optional[float] = 0.0
    payg_reserved_spend_usd: Optional[float] = 0.0
    payg_soft_limit_usd: Optional[float] = None
    payg_hard_limit_usd: Optional[float] = None
    payg_billing_email: Optional[str] = None

class PaginatedOrganizationResponse(BaseModel):
    items: List[OrganizationWalletView]
    total: int
    page: int
    size: int

class PurchaseRequest(BaseModel):
    organization_name: str
    token_amount: int
    remarks: Optional[str] = None

class SetGracePeriodRequest(BaseModel):
    organization_name: str
    grace_period_months: int

class BulkSetGracePeriodRequest(BaseModel):
    grace_period_months: int

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
    low_balance_organizations: int = 0
    pending_quota_requests: int = 0
    payg_limit_breaches: int = 0
    total_payg_current_spend_usd: float = 0.0

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

class TrendPoint(BaseModel):
    date: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost_usd: float

class UsageTrendsResponse(BaseModel):
    range: str
    from_date: str
    to_date: str
    points: List[TrendPoint]

class ModelUsageView(BaseModel):
    model: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost_usd: float
    percentage: float = 0.0

class TopOrganizationItem(BaseModel):
    organization_name: str
    organization_id: Optional[str] = None
    billing_mode: str
    total_tokens: int
    request_count: int
    total_cost_usd: float
    payg_spend_usd: float = 0.0
    remaining_tokens: int = 0
    is_blocked: bool = False

class TopOrganizationsResponse(BaseModel):
    by_tokens: List[TopOrganizationItem]
    by_cost: List[TopOrganizationItem]

class AlertItem(BaseModel):
    organization_name: str
    organization_id: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    metric_value: Optional[str] = None
    created_at: Optional[str] = None

class OperationalAlertsResponse(BaseModel):
    critical: List[AlertItem]
    warning: List[AlertItem]
    action_required: List[AlertItem]
    total_alerts: int
