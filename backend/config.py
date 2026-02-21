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
    ai_model: str = "moonshotai/kimi-k2.5"

    # GitHub OAuth
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None

    # Task Management API
    task_api_base_url: str = "https://01e5-49-42-156-24.ngrok-free.app"
    task_api_client_id: str = "proj_26_24a39ae3"
    task_api_client_secret: str = "aKQGDatX0lXgU2nU2yMQVUumbRH-m_LAqZcc1AF9ZoY"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

