from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, JSON, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

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

    documents = relationship("Document", back_populates="owner")
    governance_responses = relationship("GovernanceResponse", back_populates="owner")
    agent_credentials = relationship("AgentCredential", back_populates="owner")
    organization_sso_settings = relationship("OrganizationSSOSetting", back_populates="admin_user")
    oauth_authorization_codes = relationship("OAuthAuthorizationCode", back_populates="user")

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
    """
    __tablename__ = "organization_agent_quotas"

    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, unique=True, index=True, nullable=False)
    shared_quota = Column(Integer, nullable=False, default=0)
    dedicated_quota = Column(Integer, nullable=False, default=0)
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

    owner = relationship("User", back_populates="governance_responses")
