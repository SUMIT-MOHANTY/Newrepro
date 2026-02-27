import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Frontend URL (for CORS)
    frontend_url: str = "http://localhost:5173"
    
    # Database
    database_url: str = "sqlite:///./app.db"
    
    # JWT
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # AI API Settings (OpenAI-compatible)
    ai_api_url: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    ai_api_key: Optional[str] = None
    # ai_model: str = "qwen/qwen3.5-397b-a17b"
    ai_model: str = "z-ai/glm4.7"

    # GitHub OAuth
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None

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

    # Task Management API
    task_api_base_url: str = "https://01e5-49-42-156-24.ngrok-free.app"
    task_api_client_id: str = "proj_240_4aba49b2"
    task_api_client_secret: str = "IKaVcrdkLSxOAnE_q1PFcol7p_Bq3heoEj-uuxTyaKE"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

