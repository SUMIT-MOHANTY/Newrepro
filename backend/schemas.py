import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

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
    file_path: Optional[str] = ""
    screening_inputs: Optional[dict] = None
    project_token: Optional[str] = None
    revision_version: Optional[int] = None  # Links document to a specific revision version

    @field_validator("file_path", mode="before")
    @classmethod
    def default_file_path(cls, v):
        return "" if v is None else v

    @field_validator("screening_inputs", mode="before")
    @classmethod
    def default_screening_inputs(cls, v, info):
        if v is not None:
            return v
        
        full_content = (info.data.get("full_content") if info.data else "") or ""
        manual_text = ""
        url_content = ""
        uploaded_files = []
        linked_documents = []
        skills_files = []
        repo_context = None

        if "--- MANUAL TEXT INPUT ---" in full_content:
            try:
                manual_text = full_content.split("--- MANUAL TEXT INPUT ---")[1].split("---")[0].strip()
            except Exception:
                pass

        if "--- WEBSITE REQUIREMENTS" in full_content:
            try:
                parts = full_content.split("--- WEBSITE REQUIREMENTS")
                if len(parts) > 1:
                    url_content = parts[1].split("---")[0].strip()
                    if ")" in url_content and "\n" in url_content:
                        url_content = url_content.split("\n", 1)[1].strip()
            except Exception:
                pass

        if not manual_text and not url_content:
            analysis_str = (info.data.get("analysis_result") if info.data else "") or ""
            if analysis_str:
                try:
                    parsed_a = json.loads(analysis_str)
                    if isinstance(parsed_a, dict) and "sections" in parsed_a and isinstance(parsed_a["sections"], list):
                        for sec in parsed_a["sections"]:
                            title = sec.get("title", "")
                            content = sec.get("content", "")
                            if title == "MANUAL TEXT INPUT" and not manual_text:
                                manual_text = content
                            elif "WEBSITE REQUIREMENTS" in title and not url_content:
                                url_content = content
                except Exception:
                    pass

        return {
            "uploaded_files": uploaded_files,
            "linked_documents": linked_documents,
            "manual_text": manual_text,
            "url_content": url_content,
            "repository_context": repo_context,
            "skills_files": skills_files,
        }

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    upload_date: Optional[datetime] = None
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
    business_value: Optional[float] = 0.0
    data_sensitivity: Optional[float] = 0.0
    integration_complexity: Optional[float] = 0.0
    operational_impact: Optional[float] = 0.0
    ai_risk: Optional[float] = 0.0
    ownership: Optional[float] = 0.0

class GovernanceResult(BaseModel):
    """Final governance scoring result"""
    id: int
    project_token: str
    project_name: Optional[str] = ""
    submission_date: Optional[datetime] = None
    
    # Individual dimension scores (0-10)
    dimension_scores: Optional[GovernanceDimensionScores] = None
    
    # Weighted composite score (0-10)
    weighted_score: Optional[float] = 0.0
    
    # Classification
    classification: Optional[str] = "SANDBOX"  # SANDBOX, CONTROLLED_SANDBOX, ENTERPRISE
    classification_description: Optional[str] = ""
    
    # Recommendation with reasoning
    recommendation: Optional[str] = ""
    
    # Hard stops triggered (if any)
    hard_stops: list[str] = []
    
    # Active revision reason attached directly to the project
    pending_revision_reason: Optional[str] = None
    
    # Original question answers (optional, included when fetching detailed result)
    answers: Optional[list[GovernanceAnswer]] = None

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    prerequisites_data: Optional[list] = None
    
    class Config:
        from_attributes = True

class PrerequisitesSaveRequest(BaseModel):
    prerequisites: Optional[list] = None
    custom_rules: Optional[str] = None
class AccessRequest(BaseModel):
    path: str
    section_name: str

# ===== REVISION MANAGEMENT =====

class RevisionCreate(BaseModel):
    """Payload for creating a new project revision."""
    reason: Optional[str] = None
    version_number: Optional[int] = None  # If not provided, auto-incremented

class RevisionResponse(BaseModel):
    """Response model for a single revision record."""
    id: int
    project_token: str
    version_number: int
    reason: Optional[str] = None
    screening_snapshot: Optional[dict] = None
    document_snapshots: Optional[list] = None
    created_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

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

