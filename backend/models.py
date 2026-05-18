from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, JSON, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from models_bootstrap_state import BootstrapState

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    organization_name = Column(String, index=True, nullable=True)
    is_org_admin = Column(Boolean, default=False)
    github_token = Column(String, nullable=True)
    github_username = Column(String, nullable=True)
    azure_devops_token = Column(String, nullable=True)
    azure_devops_username = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_page_path = Column(String, nullable=True)  # Track last visited page
    last_project_token = Column(String, nullable=True)  # Track last active project

    documents = relationship("Document", back_populates="owner")
    governance_responses = relationship("GovernanceResponse", back_populates="owner")
    agent_credentials = relationship("AgentCredential", back_populates="owner")
    organization_sso_settings = relationship("OrganizationSSOSetting", back_populates="admin_user")
    oauth_authorization_codes = relationship("OAuthAuthorizationCode", back_populates="user")
    organization_role_mappings = relationship("UserOrganizationRole", back_populates="user")
    password_resets = relationship("PasswordReset", back_populates="user")

class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    token_hash = Column(String, index=True, unique=True, nullable=False)
    expires_at = Column(DateTime, index=True, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="password_resets")

class OrganizationRole(Base):
    __tablename__ = "organization_roles"
    __table_args__ = (
        UniqueConstraint("organization_name", "name", name="uq_org_role_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    permissions = relationship("OrganizationRolePermission", back_populates="role", cascade="all, delete-orphan")
    user_mappings = relationship("UserOrganizationRole", back_populates="role")
    invites = relationship("OrganizationInvite", back_populates="role")

class OrganizationRolePermission(Base):
    __tablename__ = "organization_role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "path", name="uq_role_permission_path"),
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("organization_roles.id"), index=True, nullable=False)
    path = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("OrganizationRole", back_populates="permissions")

class UserOrganizationRole(Base):
    __tablename__ = "user_organization_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_name", name="uq_user_org_role"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    organization_name = Column(String, index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("organization_roles.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="organization_role_mappings")
    role = relationship("OrganizationRole", back_populates="user_mappings")

class OrganizationInvite(Base):
    __tablename__ = "organization_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_org_invite_token_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=True)
    role_id = Column(Integer, ForeignKey("organization_roles.id"), index=True, nullable=False)
    token_hash = Column(String, index=True, nullable=False)
    expires_at = Column(DateTime, index=True, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    accepted_by_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("OrganizationRole", back_populates="invites")

class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    client_id = Column(String, unique=True, index=True, nullable=False)
    client_secret = Column(String, nullable=False)
    redirect_uri = Column(String, nullable=False)
    login_url = Column(String, nullable=True)
    allowed_organization = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization_connections = relationship("OrganizationPluginConnection", back_populates="oauth_client")

class OAuthAuthorizationCode(Base):
    __tablename__ = "oauth_authorization_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    client_id = Column(String, ForeignKey("oauth_clients.client_id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    organization_name = Column(String, index=True, nullable=True)
    redirect_uri = Column(String, nullable=False)
    scope = Column(String, nullable=True)
    nonce = Column(String, nullable=True)
    state = Column(String, nullable=True)
    expires_at = Column(DateTime, index=True, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="oauth_authorization_codes")

class OrganizationPluginConnection(Base):
    __tablename__ = "organization_plugin_connections"
    __table_args__ = (
        UniqueConstraint("organization_name", "oauth_client_id", name="uq_org_plugin_connection"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    oauth_client_id = Column(String, ForeignKey("oauth_clients.client_id"), index=True, nullable=False)
    is_connected = Column(Boolean, default=False)
    remote_org_tenant = Column(String, nullable=True)
    last_message = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    connected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    oauth_client = relationship("OAuthClient", back_populates="organization_connections")

class OrganizationSSOSetting(Base):
    __tablename__ = "organization_sso_settings"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, unique=True, index=True, nullable=False)
    admin_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    sso_provider = Column(String, nullable=True)
    tenant_id = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    client_secret = Column(String, nullable=True)
    authority_url = Column(String, nullable=True)
    redirect_uri = Column(String, nullable=True)
    logout_url = Column(String, nullable=True)
    scopes = Column(String, nullable=True)
    domain_hint = Column(String, nullable=True)
    sso_enabled = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    admin_user = relationship("User", back_populates="organization_sso_settings")

class AgentCredential(Base):
    __tablename__ = "agent_credentials"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    project_token = Column(String, index=True, nullable=True)
    agent_id = Column(String, index=True)
    git_repo_url = Column(String, nullable=True)
    git_token = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="agent_credentials")

class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=True)
    project_token = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class OrganizationAgentQuota(Base):
    """
    Organization-wide capacity (license) for agent slots.
    - shared_quota: how many shared agents the org is allowed to create (in addition to defaults)
    - dedicated_quota: how many dedicated agents the org is allowed to create across ALL projects (in addition to defaults)
    - *_dev_quota / *_test_quota: sub_type breakdown of the above quotas
    """
    __tablename__ = "organization_agent_quotas"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, unique=True, index=True, nullable=False)
    shared_quota = Column(Integer, nullable=False, default=0)
    dedicated_quota = Column(Integer, nullable=False, default=0)
    # Sub-type breakdown
    shared_dev_quota = Column(Integer, nullable=False, default=0)
    shared_test_quota = Column(Integer, nullable=False, default=0)
    dedicated_dev_quota = Column(Integer, nullable=False, default=0)
    dedicated_test_quota = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class OrganizationAgentMapping(Base):
    """
    Maps an agent record in `agents` table to an organization, and flags whether it is a built-in default.
    This avoids changing the existing `agents` schema while allowing org-scoped listing/quotas.
    """
    __tablename__ = "organization_agent_mappings"
    __table_args__ = (
        UniqueConstraint("organization_name", "agent_id", name="uq_org_agent_mapping"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), index=True, nullable=False)
    project_token = Column(String, index=True, nullable=True)
    agent_kind = Column(String, index=True, nullable=True)
    agent_sub_type = Column(String, index=True, nullable=True)  # 'dev' or 'test'
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    content_preview = Column(String, nullable=True) # First few chars of extraction
    full_content = Column(String, nullable=True)    # Full markdown content
    analysis_result = Column(String, nullable=True) # JSON string of analysis
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="documents")

class GovernanceResponse(Base):
    __tablename__ = "governance_responses"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    project_name = Column(String, index=True)
    submission_date = Column(DateTime, default=datetime.utcnow)
    
    # Store all 17 question answers as JSON
    answers = Column(JSON)  # Dict mapping question_id -> score
    
    # Computed scores
    business_value_score = Column(Float, nullable=True)
    data_sensitivity_score = Column(Float, nullable=True)
    integration_complexity_score = Column(Float, nullable=True)
    operational_impact_score = Column(Float, nullable=True)
    ai_risk_score = Column(Float, nullable=True)
    ownership_score = Column(Float, nullable=True)
    
    # Final weighted score (0-10)
    weighted_score = Column(Float, nullable=True)
    
    # Classification result
    classification = Column(String)  # SANDBOX, CONTROLLED_SANDBOX, ENTERPRISE
    # Recommendation with reasoning
    recommendation = Column(Text)  # Detailed recommendation text

    # Tracks an active request to start a new BRD revision on this project
    pending_revision_reason = Column(String, nullable=True)

    # dynamically generated project API credentials for external task system
    client_id = Column(String, nullable=True)
    client_secret = Column(String, nullable=True)

    # Azure DevOps OAuth credentials (per-project)
    azure_devops_client_id = Column(String, nullable=True)
    azure_devops_client_secret = Column(String, nullable=True)
    azure_devops_organization = Column(String, nullable=True)
    azure_devops_project = Column(String, nullable=True)
    azure_devops_tenant_id = Column(String, nullable=True)

    # Track when prerequisites were acknowledged
    prerequisites_completed_at = Column(DateTime, nullable=True)

    # Store roadmap steps data (steps, step_statuses, current_step, etc.)
    steps_data = Column(JSON, nullable=True)
    
    # Store claude.md files (always loaded for all agents)
    claude_md_files = Column(JSON, nullable=True)  # Array of {name, content, uploadedAt}
    
    # Store skills.md files (selectively loaded based on task relevance)
    skills_md_files = Column(JSON, nullable=True)  # Array of {name, content, uploadedAt}

    owner = relationship("User", back_populates="governance_responses")

class GovernanceQuestion(Base):
    __tablename__ = "governance_questions"

    id = Column(Integer, primary_key=True, index=True)
    dimension = Column(String, index=True, nullable=False)
    question_text = Column(String, nullable=False)
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    options = relationship("GovernanceQuestionOption", back_populates="question", cascade="all, delete-orphan")

class GovernanceQuestionOption(Base):
    __tablename__ = "governance_question_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("governance_questions.id"), index=True, nullable=False)
    label = Column(String, nullable=False)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    question = relationship("GovernanceQuestion", back_populates="options")


class Task(Base):
    """Local task storage before syncing to NXDUNE"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True, nullable=False)  # EPIC-01, TASK-01, etc.
    project_token = Column(String, index=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Task details
    task_name = Column(String, nullable=False)
    task_type = Column(String, nullable=False)  # EPIC, FEATURE, STORY, TASK, BUG
    description = Column(Text, nullable=True)
    priority = Column(String, default="medium")  # high, medium, low
    task_wallet = Column(Integer, default=1)
    
    # Dates
    startdate = Column(String, nullable=True)
    planned_start = Column(String, nullable=True)
    deadline = Column(String, nullable=True)
    
    # Assignment
    assigned_to = Column(JSON, default=list)  # List of assignee IDs
    reported_by = Column(String, default="system")
    
    # Organization
    sprint = Column(String, default="new")
    milestone = Column(String, default="main")
    linked_tasks = Column(JSON, default=list)  # List of parent/dependent task IDs
    
    # Checklist
    checklist = Column(Text, nullable=True)  # JSON string of checklist items
    
    # Selection and sync status
    selected = Column(Boolean, default=False)  # User has selected this task for sync
    synced_to_nxdune = Column(Boolean, default=False)
    nxdune_task_id = Column(Integer, nullable=True)  # ID from NXDUNE after sync
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = relationship("User")


class AgentMessage(Base):
    """Persistent agent-to-agent communication messages"""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)

    # Who sent it and who it's for (None = broadcast to all)
    from_agent = Column(String, index=True, nullable=False)
    to_agent = Column(String, index=True, nullable=True)  # None = broadcast

    # Message classification
    # BLOCKED | OFFERING | READY | HELP_REQUEST | RESPONSE | INFO | RESOLVED
    msg_type = Column(String, nullable=False, default="INFO")

    message = Column(Text, nullable=False)

    # Optional structured payload (e.g. which file/model is needed)
    payload = Column(JSON, nullable=True)

    # Which task this message relates to
    related_task_id = Column(String, nullable=True, index=True)

    # Whether this blocker was resolved
    resolved = Column(Boolean, default=False)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class HandoffToken(Base):
    """Store VibeCoding handoff tokens with full payload to avoid URL length limits"""
    __tablename__ = "handoff_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(String, unique=True, index=True, nullable=False)
    payload = Column(Text, nullable=False)  # JSON string of the full handoff data
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)  # Track when token was used


class ChatMessage(Base):
    """Store BRD chat messages for persistent conversation history"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    
    # Message content
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    
    # Optional metadata
    is_error = Column(Boolean, default=False)
    is_qa = Column(Boolean, default=False)  # Whether this is a Q&A submission
    affected_sections = Column(JSON, nullable=True)  # Sections affected by this update
    change_summary = Column(Text, nullable=True)  # Summary of changes made
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    document = relationship("Document")
    user = relationship("User")


class SharedDocument(Base):
    """Store shared BRD documents with secure access controls"""
    __tablename__ = "shared_documents"

    id = Column(Integer, primary_key=True, index=True)
    share_token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    share_project_id = Column(Integer, ForeignKey("share_projects.id"), index=True, nullable=True)
    title = Column(String, nullable=True)
    access_type = Column(String, default="once")  # 'once' or 'always'
    expiration_time = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    require_password = Column(Boolean, default=False)
    password_hash = Column(String, nullable=True)
    access_count = Column(Integer, default=0)
    view_limit = Column(Integer, nullable=True)  # Limit number of views
    can_download = Column(Boolean, default=True)  # Control download permissions
    allow_anonymous = Column(Boolean, default=True)  # Allow public access without individual token
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User")
    share_project = relationship("ShareProject", back_populates="shared_documents")
    files = relationship("SharedDocumentFile", back_populates="shared_document", cascade="all, delete-orphan")
    recipients = relationship("SharedDocumentRecipient", back_populates="shared_document", cascade="all, delete-orphan")
    access_logs = relationship("SharedDocumentAccessLog", back_populates="shared_document", cascade="all, delete-orphan")


class SharedDocumentFile(Base):
    """Store files associated with shared documents"""
    __tablename__ = "shared_document_files"

    id = Column(Integer, primary_key=True, index=True)
    share_id = Column(Integer, ForeignKey("shared_documents.id"), index=True, nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    zip_password = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    shared_document = relationship("SharedDocument", back_populates="files")


class SharedDocumentRecipient(Base):
    """Store email recipients for shared documents"""
    __tablename__ = "shared_document_recipients"

    id = Column(Integer, primary_key=True, index=True)
    share_id = Column(Integer, ForeignKey("shared_documents.id"), index=True, nullable=False)
    email = Column(String, nullable=False)
    share_token = Column(String, unique=True, index=True, nullable=True) # Unique token for this recipient
    access_level = Column(String, default="view") # 'view' or 'download' (if global allows)
    notified_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    shared_document = relationship("SharedDocument", back_populates="recipients")


class SharedDocumentAccessLog(Base):
    """Log access attempts to shared documents"""
    __tablename__ = "shared_document_access_log"

    id = Column(Integer, primary_key=True, index=True)
    share_id = Column(Integer, ForeignKey("shared_documents.id"), index=True, nullable=False)
    accessed_at = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    recipient_email = Column(String, nullable=True) # To track specific recipients
    action = Column(String, default="view") # 'view' or 'download'
    filename = Column(String, nullable=True) # Which file was accessed

    # Relationships
    shared_document = relationship("SharedDocument", back_populates="access_logs")


class ShareProject(Base):
    """Store share document projects - separate from regular governance projects"""
    __tablename__ = "share_projects"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_name = Column(String, nullable=False)
    description = Column(String, default="Shared Documents")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_step = Column(Integer, default=0) # Track last visited step
    
    # Relationships
    owner = relationship("User")
    shared_documents = relationship("SharedDocument", back_populates="share_project")


# Update SharedDocument to include share_project_id
