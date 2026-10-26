import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, JSON, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

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
    is_super_admin = Column(Boolean, default=False)
    github_token = Column(String, nullable=True)
    github_username = Column(String, nullable=True)
    azure_devops_token = Column(String, nullable=True)
    azure_devops_username = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_page_path = Column(String, nullable=True)  # Track last visited page
    last_project_token = Column(String, nullable=True)  # Track last active project
    daily_emails_enabled = Column(Boolean, default=True)

    documents = relationship("Document", back_populates="owner")
    governance_responses = relationship("GovernanceResponse", back_populates="owner")
    agent_credentials = relationship("AgentCredential", back_populates="owner")
    organization_sso_settings = relationship("OrganizationSSOSetting", back_populates="admin_user")
    oauth_authorization_codes = relationship("OAuthAuthorizationCode", back_populates="user")
    organization_role_mappings = relationship("UserOrganizationRole", back_populates="user")
    password_resets = relationship("PasswordReset", back_populates="user")

class CapacityIncreaseRequest(Base):
    """
    Capacity Increase Requests submitted by Org Admins (aggregated from project requests)
    to Super Admin for organization-wide agent capacity cap increases.
    """
    __tablename__ = "capacity_increase_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_token = Column(String, nullable=True)
    requested_shared_count = Column(Integer, default=0)
    requested_dedicated_count = Column(Integer, default=0)
    total_requested_increase = Column(Integer, nullable=False, default=1)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING", index=True)  # PENDING | APPROVED | REJECTED
    approved_total_capacity = Column(Integer, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])


class ProjectAgentRequest(Base):
    """
    Agent requests raised by End Users / Project Members to the Org Admin
    specifying shared and dedicated agent counts needed for a specific project.
    """
    __tablename__ = "project_agent_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    project_token = Column(String, index=True, nullable=False)
    project_name = Column(String, nullable=True)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    requested_shared_count = Column(Integer, default=0)
    requested_dedicated_count = Column(Integer, default=0)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING", index=True)  # PENDING | APPROVED | REJECTED | ESCALATED
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])


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

class UserProjectAssociation(Base):
    __tablename__ = "user_project_associations"
    __table_args__ = (
        UniqueConstraint("user_id", "project_token", name="uq_user_project_assoc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_token = Column(String, ForeignKey("governance_responses.project_token"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    display_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=True)
    project_token = Column(String, index=True, nullable=True)
    skills_content = Column(Text, nullable=True)
    skills_summary = Column(String(500), nullable=True)
    skills_tags = Column(JSON, nullable=True)
    specialization = Column(String, nullable=True)
    face = Column(Text, nullable=True)
    allowed_tools = Column(JSON, nullable=True)
    model_name = Column(String, nullable=True, default="claude")
    created_at = Column(DateTime, default=datetime.utcnow)

class OrganizationAgentQuota(Base):
    """
    Organization-wide capacity (license) for agent slots.
    - max_agent_capacity: Overall total capacity cap set by Super Admin (single combined limit, default 0)
    - shared_quota: how many shared agents the org is allowed to create
    - dedicated_quota: how many dedicated agents the org is allowed to create across ALL projects
    - *_dev_quota / *_test_quota: sub_type breakdown of the above quotas
    """
    __tablename__ = "organization_agent_quotas"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, unique=True, index=True, nullable=False)
    max_agent_capacity = Column(Integer, nullable=False, default=10) # Set by Super Admin
    shared_quota = Column(Integer, nullable=False, default=10)
    dedicated_quota = Column(Integer, nullable=False, default=10)
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
    
    shared_count / dedicated_count track how many instances of this agent type are allocated
    to a project as shared or dedicated, enabling quantity-based allocation.
    home_project_token: The project to which this dedicated agent is bound.
    current_borrowed_project_token: Project borrowing this agent as a shared agent when idle.
    is_borrowed: Flag indicating if an idle dedicated agent is currently borrowed by another project.
    is_virtual_shared: Flag indicating if this shared agent is virtually onboarded without extra physical worker containers.
    """
    __tablename__ = "organization_agent_mappings"
    __table_args__ = (
        UniqueConstraint("organization_name", "agent_id", name="uq_org_agent_mapping"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, index=True, nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), index=True, nullable=False)
    project_token = Column(String, index=True, nullable=True)
    home_project_token = Column(String, index=True, nullable=True)
    current_borrowed_project_token = Column(String, index=True, nullable=True)
    is_borrowed = Column(Boolean, default=False)
    is_virtual_shared = Column(Boolean, default=False)
    agent_kind = Column(String, index=True, nullable=True)
    agent_sub_type = Column(String, index=True, nullable=True)  # 'dev' or 'test'
    is_default = Column(Boolean, default=False)
    # Quantity-based allocation counts (0 means unallocated for that type)
    shared_count = Column(Integer, nullable=False, default=0)
    dedicated_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    content_preview = Column(String, nullable=True) # First few chars of extraction
    full_content = Column(String, nullable=True)    # Full markdown content
    analysis_result = Column(String, nullable=True) # JSON string of analysis
    file_path = Column(String, nullable=True)       # Path/unique name of the uploaded document on disk
    screening_inputs = Column(JSON, nullable=True)  # Raw requirement screening inputs (uploaded_files, linked_documents, manual_text, url_content, repository_context, skills_files)
    project_token = Column(String, index=True, nullable=True)  # Link document directly to a project
    revision_version = Column(Integer, nullable=True)  # Which revision version this document belongs to (None = initial/original)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="documents")

class ProjectTag(Base):
    __tablename__ = "project_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    project_id = Column(Integer, ForeignKey("governance_responses.id", ondelete="CASCADE"), index=True, nullable=False)

    project = relationship("GovernanceResponse", back_populates="tags")

class GovernanceResponse(Base):
    __tablename__ = "governance_responses"

    tags = relationship("ProjectTag", back_populates="project", cascade="all, delete-orphan")

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    organization_name = Column(String, index=True, nullable=True)
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
    # Current revision version counter (starts at 1, increments with each revision)
    current_revision_version = Column(Integer, nullable=False, default=1)

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
    # Store raw prerequisite items, user selections, and filled inputs
    prerequisites_data = Column(JSON, nullable=True)

    # Store roadmap steps data (steps, step_statuses, current_step, etc.)
    steps_data = Column(JSON, nullable=True)
    
    # Store claude.md files (always loaded for all agents)
    claude_md_files = Column(JSON, nullable=True)  # Array of {name, content, uploadedAt}
    
    # Store skills.md files (selectively loaded based on task relevance)
    skills_md_files = Column(JSON, nullable=True)  # Array of {name, content, uploadedAt}

    # AI-classified project type: greenfield | brownfield | modernization
    # Populated automatically after analysis completes from metrics.project_type
    project_type = Column(String, nullable=True, default="greenfield")

    # Project-wise Git Repository settings
    source_repo_url = Column(String, nullable=True)
    source_repo_token = Column(String, nullable=True)
    dest_repo_url = Column(String, nullable=True)
    dest_repo_token = Column(String, nullable=True)
    repo_action = Column(String, nullable=True)
    repo_custom_instructions = Column(Text, nullable=True)

    # Soft-delete / archive flag — when True, project is hidden from UI but stays in DB
    is_archived = Column(Boolean, default=False)

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
    
    # Modern Jira/Linear Task Lifecycle & Execution tracking
    status = Column(String(32), default="TODO", index=True)  # BACKLOG, TODO, IN_PROGRESS, IN_REVIEW, DONE, BLOCKED, FAILED
    assigned_agent_role = Column(String(64), nullable=True)  # Architect, Frontend Developer, Backend Developer, QA Engineer
    assigned_agent_id = Column(String(64), nullable=True)
    verification_status = Column(String(32), default="PENDING")  # PENDING, PASSED, FAILED
    files_modified = Column(JSON, default=list)  # List of modified file paths
    execution_logs = Column(Text, nullable=True)  # Terminal / Agent run logs
    error_details = Column(Text, nullable=True)

    @property
    def is_selected_for_execution(self) -> bool:
        return bool(self.selected or self.synced_to_nxdune or self.status != "BACKLOG")
    
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
    is_archived = Column(Boolean, default=False)
    
    # Relationships
    owner = relationship("User")
    shared_documents = relationship("SharedDocument", back_populates="share_project")


class AIUsageLog(Base):
    """Store AI usage logs for cost calculation and metrics"""
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    project_token = Column(String, index=True, nullable=True)
    organization_name = Column(String, index=True, nullable=True)
    organization_id = Column(String(36), index=True, nullable=True)
    model = Column(String, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    usage_status = Column(String, nullable=False, default="COMPLETED")  # COMPLETED or UNKNOWN
    purpose = Column(String, nullable=True, index=True)  # Circumstance or feature (e.g. Requirement Screening, BRD Analysis)
    project_name = Column(String, nullable=True, index=True)  # Human-readable project name
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


from sqlalchemy import event

@event.listens_for(AIUsageLog, "before_insert")
def validate_ai_usage_log_project_token(mapper, connection, target):
    """
    Enforces that NO new AIUsageLog record is ever saved at the organization level
    or without a valid project token.
    """
    is_invalid = False
    if not target.project_token or not str(target.project_token).strip():
        is_invalid = True
    elif target.organization_name and str(target.project_token).strip().lower() == str(target.organization_name).strip().lower():
        is_invalid = True
    elif target.organization_id and str(target.project_token).strip().lower() == str(target.organization_id).strip().lower():
        is_invalid = True

    if is_invalid:
        from database import SessionLocal
        from tokenops.services.project_token_resolver import resolve_or_ensure_project_token
        s = SessionLocal()
        try:
            tok, nm = resolve_or_ensure_project_token(
                session=s,
                user_id=target.user_id,
                organization_name=target.organization_name,
                candidate_project_token=target.project_token,
                candidate_project_name=target.project_name
            )
            target.project_token = tok
            target.project_name = nm
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()


class UserActivityLog(Base):
    """Store detailed user activity logs for security/audit tracking"""
    __tablename__ = "user_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    action = Column(String, nullable=False)
    method = Column(String, nullable=True)
    path = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Revision(Base):
    """
    Tracks revision versions for a project.
    Each revision snapshots the screening_inputs and document list at that point in time.
    """
    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("project_token", "version_number", name="uq_revision_version"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)
    version_number = Column(Integer, nullable=False)  # 1, 2, 3...
    reason = Column(String, nullable=True)  # Why this revision was created
    
    # Snapshot of screening_inputs at the time of revision (JSON copy)
    screening_snapshot = Column(JSON, nullable=True)
    # Snapshot of document IDs that were in the project at this revision
    document_snapshots = Column(JSON, nullable=True)  # List of document IDs
    
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ProjectRuntimeState(Base):
    """Store active project runtime states like claimed tasks, agent state logs, etc."""
    __tablename__ = "project_runtime_states"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True, nullable=False)
    master_tree_created = Column(Boolean, default=False)
    claimed_task_ids = Column(JSON, default=list)  # List/Set of claimed task IDs
    agent_states = Column(JSON, default=dict)      # Agent status & output logs
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Local-First State Management Models ──────────────────────────────────────
# These models form the primary source of truth for agent orchestration.
# NXDune is treated as a secondary synchronization layer only.

class AgentTaskOwnership(Base):
    """
    Canonical record of which agent owns which task, written atomically at claim time.
    Survives server restarts — eliminates the "Skipping persisted assignment restore" problem.
    Local DB wins over NXDune for completed tasks (NXDune may have stale status).
    """
    __tablename__ = "agent_task_ownerships"
    __table_args__ = (
        UniqueConstraint("project_token", "task_id", name="uq_agent_task_ownership"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)
    task_id = Column(String, index=True, nullable=False)        # e.g. "TASK-01"
    agent_id = Column(String, index=True, nullable=False)       # which agent owns it

    # Task metadata snapshot (stored at claim time so agents can resume without NXDune)
    task_title = Column(String, nullable=True)
    task_data = Column(JSON, nullable=True)                     # Full task dict snapshot
    task_lane = Column(String, nullable=True)                   # "frontend" | "backend" | "qa" | "devops"

    # Execution lifecycle
    status = Column(String, nullable=False, default="claimed")  # claimed | in_progress | done | failed
    claimed_at = Column(DateTime, nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Output artifacts
    branch_name = Column(String, nullable=True)                 # git branch e.g. "agent/task-01-auth"
    files_written = Column(JSON, default=list)                  # list of file paths created/modified
    error_message = Column(Text, nullable=True)

    # NXDune sync tracking
    nxdune_synced = Column(Boolean, default=False)
    nxdune_synced_at = Column(DateTime, nullable=True)
    nxdune_sync_attempts = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectCanonicalState(Base):
    """
    Immutable bootstrap artifacts: canonical project tree, technical spec, and tech stack.
    Written ONCE when the bootstrap task completes successfully.
    Subsequent writes are no-ops unless force_reset=True is explicitly passed.

    All agents read from here instead of re-generating or querying NXDune.
    Resolves: repeated canonical tree/spec regeneration across restarts.
    """
    __tablename__ = "project_canonical_states"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True, nullable=False)

    # Immutable bootstrap artifacts
    canonical_tree = Column(Text, nullable=True)        # JSON string of the project tree
    technical_spec = Column(Text, nullable=True)        # Full technical specification text
    tech_stack = Column(JSON, nullable=True)            # Detected tech stack dict
    bootstrap_branch = Column(String, nullable=True)    # Branch where bootstrap was pushed

    # Domain-to-paths mapping for targeted context injection
    # {domain: [file_paths]} — populated from canonical_tree after bootstrap
    domain_file_map = Column(JSON, nullable=True)

    # State flags
    is_ready = Column(Boolean, default=False)           # True = bootstrap fully completed
    force_reset = Column(Boolean, default=False)        # True = allow overwrite (admin only)

    # Version tracking for debugging
    version = Column(Integer, default=1)
    last_agent_id = Column(String, nullable=True)       # Which agent wrote this

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentExecutionCheckpoint(Base):
    """
    Versioned snapshots of per-agent execution progress.
    Written at each major execution milestone so agents can resume after server restart
    without re-querying NXDune or losing progress context.
    """
    __tablename__ = "agent_execution_checkpoints"
    __table_args__ = (
        UniqueConstraint("project_token", "agent_id", name="uq_agent_execution_checkpoint"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=False)

    # Latest task context
    current_task_id = Column(String, nullable=True, index=True)
    current_task_data = Column(JSON, nullable=True)     # Full task dict
    current_task_status = Column(String, nullable=True) # "claimed" | "in_progress" | "done"

    # Execution state for resume
    progress = Column(Integer, default=0)               # 0-100
    progress_message = Column(String, nullable=True)
    last_milestone = Column(String, nullable=True)      # Last completed milestone name

    # Files written so far in current task (for file ownership tracking)
    files_written_so_far = Column(JSON, default=list)

    # Version counter — incremented on every update
    version = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NXDuneSyncLog(Base):
    """
    Audit trail of all NXDune sync attempts.
    When NXDune updates fail, the failure is recorded here so no state is lost.
    Agents can query this to determine if their last push reached NXDune or is pending retry.
    No background service — the existing NXDune update flow writes here on failure.
    """
    __tablename__ = "nxdune_sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=True)
    task_id = Column(String, index=True, nullable=True)

    # What operation was attempted
    operation = Column(String, nullable=False)          # "task_complete" | "progress_update" | "task_claim"
    payload = Column(JSON, nullable=True)               # The data that was (or should be) sent to NXDune

    # Result
    success = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)

    # Retry tracking
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime, nullable=True)
    permanently_failed = Column(Boolean, default=False)  # True = stop retrying

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AgentNote(Base):
    """Local storage of agent notes for local-first coordination"""
    __tablename__ = "agent_notes"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, index=True, nullable=False)
    title = Column(String, index=True, nullable=False)  # e.g. "STATUS::..." or "MASTER::..."
    content_payload = Column(JSON, nullable=False)
    content_text = Column(Text, nullable=True)
    user = Column(String, nullable=True)
    
    # Sync tracking
    synced_to_nxdune = Column(Boolean, default=False)
    nxdune_note_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyBillingEmailLog(Base):
    __tablename__ = "daily_billing_email_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    email = Column(String, index=True, nullable=False)
    date_key = Column(String, index=True, nullable=False)  # YYYY-MM-DD
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String, index=True, nullable=False)  # "success", "failed", "skipped_by_filters"
    error_message = Column(Text, nullable=True)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    is_admin_report = Column(Boolean, default=False)
    cc_recipients = Column(Text, nullable=True)  # Comma-separated list of CC'd emails


class SupportTicket(Base):
    """
    Support ticket raised by an End User or Org Admin for technical assistance,
    capacity allocation, billing, or platform support.
    """
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_code = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)  # e.g. "Agent Allocation", "Technical Issue", etc.
    priority = Column(String(50), nullable=False, default="MEDIUM", index=True)  # "LOW", "MEDIUM", "HIGH", "URGENT"
    status = Column(String(50), nullable=False, default="OPEN", index=True)      # "OPEN", "IN_PROGRESS", "AWAITING_INFO", "RESOLVED", "CLOSED"
    
    organization_name = Column(String, index=True, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    resolution_summary = Column(Text, nullable=True)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    last_message_at = Column(DateTime, default=datetime.utcnow, index=True)
    unread_by_admin = Column(Boolean, default=True)
    unread_by_user = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_user_id])
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.created_at.asc()")


class TicketMessage(Base):
    """
    Discussion message or admin internal note within a SupportTicket thread.
    """
    __tablename__ = "ticket_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    message = Column(Text, nullable=False)
    is_internal_note = Column(Boolean, default=False)
    attachments = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_user_id])


class AgentSession(Base):
    """Durable record of an isolated container execution session for a project."""
    __tablename__ = "agent_sessions"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), nullable=True, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), default="pending", nullable=False, index=True)
    container_id = Column(String(255), nullable=True)
    preview_url = Column(String(512), nullable=True)
    preview_port = Column(Integer, nullable=True)

    started_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks = relationship("AgentTask", back_populates="session", cascade="all, delete-orphan", order_by="AgentTask.created_at.asc()")
    events = relationship("AgentEvent", back_populates="session", cascade="all, delete-orphan", order_by="AgentEvent.created_at.asc()")


class AgentTask(Base):
    """Single unit of work within an agent session."""
    __tablename__ = "agent_tasks"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(64), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String(64), default="initial_generation")
    description = Column(Text, nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    model_name = Column(String(128), nullable=True)
    files_changed = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("AgentSession", back_populates="tasks")


class AgentEvent(Base):
    """Real-time lifecycle or tool execution event dispatched by agent runtime."""
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    session = relationship("AgentSession", back_populates="events")




