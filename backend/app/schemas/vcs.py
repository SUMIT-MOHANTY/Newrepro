from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GitHubCallbackPayload(BaseModel):
    code: str


class AzureDevOpsCallbackPayload(BaseModel):
    code: str


class AzureDevOpsSaveCredentialsPayload(BaseModel):
    project_token: str
    client_id: str
    client_secret: str


class RepoContextRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    project_token: Optional[str] = None


class GitValidationRequest(BaseModel):
    git_repo_url: str
    git_branch: Optional[str] = "main"
    git_token: Optional[str] = None
    git_username: Optional[str] = None
    git_password: Optional[str] = None
    git_provider: Optional[str] = "github"


class VCSStatusResponse(BaseModel):
    connected: bool
    username: Optional[str] = None
    provider: str


__all__ = [
    "GitHubCallbackPayload",
    "AzureDevOpsCallbackPayload",
    "AzureDevOpsSaveCredentialsPayload",
    "RepoContextRequest",
    "GitValidationRequest",
    "VCSStatusResponse",
]
