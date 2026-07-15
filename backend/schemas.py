from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    password: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    is_org_admin: bool = False

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    requires_selection: Optional[bool] = False
    organizations: Optional[list[str]] = None

class TokenData(BaseModel):
    email: Optional[str] = None

class SSOStartRequest(BaseModel):
    email: Optional[EmailStr] = None
    organization_name: Optional[str] = None
    next: Optional[str] = None

class SSOStartResponse(BaseModel):
    auth_url: str

class OAuthClientPublic(BaseModel):
    name: str
    client_id: str
    login_url: Optional[str] = None
    connected: bool = False
    connected_at: Optional[datetime] = None
    remote_org_tenant: Optional[str] = None
    connection_message: Optional[str] = None
    connection_error: Optional[str] = None

class OAuthPluginLaunchResponse(BaseModel):
    launch_url: str
    connected: bool = False

class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scope: Optional[str] = None

class OrganizationSSOSettingsUpdate(BaseModel):
    sso_provider: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    authority_url: Optional[str] = None
    redirect_uri: Optional[str] = None
    logout_url: Optional[str] = None
    scopes: Optional[str] = None
    domain_hint: Optional[str] = None
    sso_enabled: bool = False

class OrganizationSSOSettingsResponse(OrganizationSSOSettingsUpdate):
    organization_name: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class OrganizationAgentQuotaResponse(BaseModel):
    organization_name: str
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
    # Usage breakdown
    shared_dev_used: int = 0
    shared_test_used: int = 0
    dedicated_dev_used: int = 0
    dedicated_test_used: int = 0
    updated_at: Optional[datetime] = None

class OrganizationAgentQuotaIncreaseRequest(BaseModel):
    kind: str          # "shared" | "dedicated"
    sub_type: Optional[str] = None  # "dev" | "test" — tracks sub_type quota
    amount: int = 1

# ===== ORG RBAC + INVITES =====

class OrganizationPage(BaseModel):
    path: str
    label: str

class OrganizationRoleUpsert(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    allowed_paths: list[str] = Field(default_factory=list)

class OrganizationRoleResponse(BaseModel):
    id: int
    organization_name: str
    name: str
    description: Optional[str] = None
    allowed_paths: list[str] = Field(default_factory=list)
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class OrganizationInviteCreate(BaseModel):
    email: Optional[EmailStr] = None
    role_id: int
    expires_in_days: int = 7

class OrganizationInviteResponse(BaseModel):
    id: int
    organization_name: str
    email: Optional[EmailStr] = None
    role_id: int
    role_name: str
    invite_url: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class OrganizationInvitePreviewResponse(BaseModel):
    organization_name: str
    email: Optional[EmailStr] = None
    role_name: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None

class OrganizationInviteAcceptRequest(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class OrganizationInviteAcceptResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_name: str
    role_name: str
    allowed_paths: list[str] = Field(default_factory=list)

class OrganizationRbacMeResponse(BaseModel):
    is_org_admin: bool = False
    organization_name: Optional[str] = None
    role_name: Optional[str] = None
    allowed_paths: list[str] = Field(default_factory=list)

class SelectOrganizationRequest(BaseModel):
    organization_name: str

class OrganizationUserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role_name: Optional[str] = None
    last_login: Optional[datetime] = None
    is_org_admin: bool = False

    class Config:
        from_attributes = True

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

    class Config:
        from_attributes = True

class DocumentBase(BaseModel):
    filename: str
    content_preview: Optional[str] = None
    full_content: Optional[str] = None
    analysis_result: Optional[str] = None
    file_path: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    upload_date: datetime
    owner_id: int

    class Config:
        from_attributes = True

class GovernanceRevisionReason(BaseModel):
    reason: Optional[str] = None

# ===== GOVERNANCE QUESTIONNAIRE =====

class GovernanceQuestionOptionBase(BaseModel):
    label: str
    score: int

class GovernanceQuestionOptionCreate(GovernanceQuestionOptionBase):
    pass

class GovernanceQuestionOption(GovernanceQuestionOptionBase):
    id: int
    question_id: int

    class Config:
        from_attributes = True

class GovernanceQuestionBase(BaseModel):
    dimension: str
    question_text: str
    order: int = 0
    is_active: bool = True

class GovernanceQuestionCreate(GovernanceQuestionBase):
    options: list[GovernanceQuestionOptionCreate]

class GovernanceQuestionUpdate(BaseModel):
    dimension: Optional[str] = None
    question_text: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None
    options: Optional[list[GovernanceQuestionOptionCreate]] = None

class GovernanceQuestion(GovernanceQuestionBase):
    id: int
    options: list[GovernanceQuestionOption]

    class Config:
        from_attributes = True

class GovernanceAnswer(BaseModel):
    """Single answer to a governance question"""
    question_id: int  # 1-17
    score: int        # 0-3, or special values like +2
    selected_option: str  # The text of the selected option

class GovernanceSubmission(BaseModel):
    """User submits answers to all 17 questions"""
    project_name: str
    answers: list[GovernanceAnswer]  # All 17 answers
    project_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

class GovernanceDimensionScores(BaseModel):
    """Calculated dimension scores (each 0-10)"""
    business_value: float
    data_sensitivity: float
    integration_complexity: float
    operational_impact: float
    ai_risk: float
    ownership: float

class GovernanceResult(BaseModel):
    """Final governance scoring result"""
    id: int
    project_token: str
    project_name: str
    submission_date: datetime
    
    # Individual dimension scores (0-10)
    dimension_scores: GovernanceDimensionScores
    
    # Weighted composite score (0-10)
    weighted_score: float
    
    # Classification
    classification: str  # SANDBOX, CONTROLLED_SANDBOX, ENTERPRISE
    classification_description: str
    
    # Recommendation with reasoning
    recommendation: str
    
    # Hard stops triggered (if any)
    hard_stops: list[str] = []
    
    # Active revision reason attached directly to the project
    pending_revision_reason: Optional[str] = None
    
    # Original question answers (optional, included when fetching detailed result)
    answers: Optional[list[GovernanceAnswer]] = None

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    
    class Config:
        from_attributes = True
class AccessRequest(BaseModel):
    path: str
    section_name: str

class ProjectGitConfigRequest(BaseModel):
    source_repo_url: Optional[str] = None
    source_repo_token: Optional[str] = None
    dest_repo_url: Optional[str] = None
    dest_repo_token: Optional[str] = None

class ProjectGitConfigResponse(BaseModel):
    source_repo_url: Optional[str] = None
    source_repo_token: Optional[str] = None
    dest_repo_url: Optional[str] = None
    dest_repo_token: Optional[str] = None

