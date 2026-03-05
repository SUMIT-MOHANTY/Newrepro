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
    ai_model: str = "minimaxai/minimax-m2.5"
    # If true, /ai/analyze will call BRN Llama endpoint instead of AI_API_URL.
    use_brn_llama: bool = False
    brn_llama_url: str = "https://brn-llama.bourntec.com/api/process"
    brn_model: str = "BournAI"
    brn_agent_id: str = "uhli23jn3oiuhgo847yyjvdhtrdy3tgfe8gfgoe87rugekuuyjommjferhjgo5go49uoi3uyrp938ry"
    brn_platform_id: str = "DSuite"
    brn_max_tokens: int = 4000
    brn_temperature: float = 0.7

    # GitHub OAuth
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None

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

