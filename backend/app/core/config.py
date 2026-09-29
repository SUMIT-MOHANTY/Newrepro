import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")

class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Frontend URL (for CORS)
    frontend_url: str = "http://localhost:5173"

    # SMTP / email delivery
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: str = "DSuite"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 20
    daily_billing_email_enabled: bool = True
    daily_billing_email_hour: int = 1
    
    # Microsoft OAuth for SMTP
    microsoft_tenant_id: Optional[str] = None
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None

    # Database
    database_url: str = "sqlite:///./app.db"
    
    # JWT
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours - increased from 30 minutes to reduce unexpected logouts
    
    # AI API Settings (OpenAI-compatible)
    ai_api_url: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    ai_api_key: Optional[str] = None
    ai_model: str = "minimaxai/minimax-m2.5"
    use_brn_llama: bool = False
    brn_llama_url: str = "https://brn-llama.bourntec.com/api/process"
    brn_model: str = "BournAI"
    brn_agent_id: str = "uhli23jn3oiuhgo847yyjvdhtrdy3tgfe8gfgoe87rugekuuyjommjferhjgo5go49uoi3uyrp938ry"
    brn_platform_id: str = "DSuite"
    brn_temperature: float = 0.7
    use_chunked_analysis: bool = True
    use_direct_ai_ingestion: bool = True

    # GitHub OAuth
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    # Azure DevOps OAuth
    azure_devops_client_id: Optional[str] = None
    azure_devops_client_secret: Optional[str] = None

    # DSuite OAuth Provider (for plugin apps)
    oauth_issuer: str = "dsuite"
    oauth_nxdune_client_id: str = "nxdune"
    oauth_nxdune_client_secret: str = "nxdune_local_change_me"
    oauth_nxdune_redirect_uri: str = "https://stg-nxdune.bourntec.com/auth/dsuite/callback"
    oauth_nxdune_login_url: str = "https://stg-nxdune.bourntec.com/login"
    oauth_kaktox_client_id: str = "kaktox"
    oauth_kaktox_client_secret: str = "kaktox_local_change_me"
    oauth_kaktox_redirect_uri: str = "http://localhost:9002/auth/dsuite/callback"
    oauth_kaktox_login_url: str = "http://localhost:9002/login"
    oauth_cloudspx_client_id: str = "cloudspx"
    oauth_cloudspx_client_secret: str = "cloudspx_local_change_me"
    oauth_cloudspx_redirect_uri: str = "http://localhost:9003/auth/dsuite/callback"
    oauth_cloudspx_login_url: str = "http://localhost:9003/login"
    nxdune_org_create_url: str = "https://stg-nxdune.bourntec.com/api/organizations/create/"
    nxdune_org_create_auth_token: Optional[str] = None
    nxdune_org_create_timeout_seconds: int = 20
    task_api_base_url: Optional[str] = "https://stg-nxdune.bourntec.com/api"
    task_api_client_id: Optional[str] = None
    task_api_client_secret: Optional[str] = None

    # Agent Runtime & Docker Sandbox Settings
    agent_runtime_image: str = "dsuite-agent-runtime:latest"
    project_storage_root: str = os.path.abspath(os.path.join(BASE_DIR, "storage", "projects"))
    agent_callback_url: str = "http://host.docker.internal:8000/api/v1"
    agent_callback_secret: str = "dsuite-agent-callback-secret"
    agent_container_memory_limit: str = "2g"
    agent_container_cpu_quota: int = 200000

    class Config:
        env_file = ENV_PATH if os.path.exists(ENV_PATH) else ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
