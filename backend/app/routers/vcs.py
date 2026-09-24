"""
DSuite BRD Analyzer - Domain Router: VCS Integrations (GitHub, Azure DevOps, Git)
Auto-extracted enterprise clean architecture domain router.
"""

import asyncio
import base64
import concurrent.futures
import hashlib
import html as html_lib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import requests
from fastapi import (
    APIRouter, Depends, File, Form, Header, HTTPException, Query,
    Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core import security as auth
import models
import schemas
from app.core.config import settings
from app.core.database import SessionLocal, engine, get_db

import github_service
import azure_devops_service
import azure_devops_oauth_service
from app.routers.helpers import _resolve_project_global_credential


logger = logging.getLogger(__name__)

router = APIRouter(tags=["VCS Integrations"])

# --- Extracted Block (Lines 10291-11112) ---
@router.get("/github/auth-url")
async def github_auth_url(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Return the GitHub OAuth authorization URL."""
    try:
        url = github_service.get_oauth_url(state=str(current_user.id))
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


class GitHubCallbackPayload(BaseModel):
    code: str


@router.post("/github/callback")
async def github_callback(
    payload: GitHubCallbackPayload,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exchange an OAuth code for a GitHub access token and persist it
    on the current user.
    """
    try:
        token_data = await github_service.exchange_code_for_token(payload.code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain GitHub token")

        # Fetch GitHub username
        gh_user = await github_service.get_github_user(access_token)
        github_username = gh_user.get("login", "")

        # Store on user record
        current_user.github_token = access_token
        current_user.github_username = github_username
        db.commit()

        return {
            "status": "connected",
            "github_username": github_username,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub OAuth error: {e}")


@router.get("/github/status")
async def github_status(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Check whether the user has connected their GitHub account."""
    return {
        "connected": bool(current_user.github_token),
        "github_username": current_user.github_username or None,
    }


@router.post("/github/disconnect")
async def github_disconnect(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored GitHub token."""
    current_user.github_token = None
    current_user.github_username = None
    db.commit()
    return {"status": "disconnected"}


@router.get("/github/repos")
async def github_repos(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = 1,
    per_page: int = 30,
):
    """List the authenticated user's GitHub repositories."""
    if not current_user.github_token:
        raise HTTPException(status_code=400, detail="GitHub not connected")
    try:
        repos = await github_service.list_repos(
            current_user.github_token, per_page=per_page, page=page
        )
        return {"repos": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch repos: {e}")


@router.get("/azure-devops/auth-url")
async def azure_devops_auth_url(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Return the Azure DevOps OAuth authorization URL. Supports project-specific credentials."""
    try:
        project_client_id = None
        project_client_secret = None
        checked_project_credentials = False
        
        # If project_token is provided, try to get project-specific credentials
        if project_token:
            gov_res = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
                models.GovernanceResponse.owner_id == current_user.id
            ).first()
            if gov_res:
                checked_project_credentials = True
                project_client_id = gov_res.azure_devops_client_id
                project_client_secret = gov_res.azure_devops_client_secret
        
        # Include project_token in state so callback can use it
        state_data = {"user_id": str(current_user.id)}
        if project_token:
            state_data["project_token"] = project_token
        
        import json
        state = json.dumps(state_data)
        
        url = azure_devops_oauth_service.get_oauth_url(
            state=state,
            client_id=project_client_id,
            client_secret=project_client_secret,
            checked_project_credentials=checked_project_credentials
        )
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


class AzureDevOpsCallbackPayload(BaseModel):
    code: str


@router.post("/azure-devops/callback")
async def azure_devops_callback(
    payload: AzureDevOpsCallbackPayload,
    state: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange an OAuth code for an Azure DevOps token and persist it. Supports project-specific credentials."""
    try:
        project_token = None
        project_client_id = None
        project_client_secret = None
        
        # Parse state to get project_token if present
        if state:
            try:
                import json
                state_data = json.loads(state)
                project_token = state_data.get("project_token")
            except:
                pass
        
        # If project_token is provided, get project-specific credentials
        if project_token:
            gov_res = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
                models.GovernanceResponse.owner_id == current_user.id
            ).first()
            if gov_res:
                project_client_id = gov_res.azure_devops_client_id
                project_client_secret = gov_res.azure_devops_client_secret
        
        token_data = await azure_devops_oauth_service.exchange_code_for_token(
            payload.code,
            client_id=project_client_id,
            client_secret=project_client_secret
        )
        access_token = (token_data.get("access_token") or "").strip()
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain Azure DevOps token")

        profile = await azure_devops_oauth_service.get_current_profile(access_token)
        display_name = str(
            profile.get("displayName")
            or profile.get("emailAddress")
            or profile.get("id")
            or ""
        ).strip()

        current_user.azure_devops_token = access_token
        current_user.azure_devops_username = display_name or None
        db.commit()

        return {
            "status": "connected",
            "azure_devops_username": current_user.azure_devops_username,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        detail = "Azure DevOps OAuth error."
        if e.response is not None:
            try:
                payload = e.response.json() or {}
                detail = str(payload.get("error_description") or payload.get("message") or detail)
            except Exception:
                detail = str(e.response.text or detail)
        raise HTTPException(status_code=status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Azure DevOps OAuth error: {e}")


@router.get("/azure-devops/status")
async def azure_devops_status(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Check whether the user has connected their Azure DevOps account."""
    return {
        "connected": bool(current_user.azure_devops_token),
        "azure_devops_username": current_user.azure_devops_username or None,
    }


class AzureDevOpsCredentialsPayload(BaseModel):
    project_token: str
    organization: Optional[str] = None
    project: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


@router.get("/azure-devops/credentials/{project_token}")
async def get_azure_devops_credentials(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Get Azure DevOps OAuth credentials for a specific project."""
    try:
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        if not gov_res:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {
            "organization": gov_res.azure_devops_organization or None,
            "project": gov_res.azure_devops_project or None,
            "tenant_id": gov_res.azure_devops_tenant_id or None,
            "client_id": gov_res.azure_devops_client_id or None,
            "client_secret": gov_res.azure_devops_client_secret or None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get credentials: {e}")


@router.post("/azure-devops/save-credentials")
async def save_azure_devops_credentials(
    payload: AzureDevOpsCredentialsPayload,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save Azure DevOps OAuth credentials for a specific project."""
    try:
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == payload.project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        if not gov_res:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Update credentials if provided
        if payload.organization is not None:
            gov_res.azure_devops_organization = payload.organization
        if payload.project is not None:
            gov_res.azure_devops_project = payload.project
        if payload.tenant_id is not None:
            gov_res.azure_devops_tenant_id = payload.tenant_id
        if payload.client_id is not None:
            gov_res.azure_devops_client_id = payload.client_id
        if payload.client_secret is not None:
            gov_res.azure_devops_client_secret = payload.client_secret
        
        db.commit()
        
        return {
            "status": "saved",
            "message": "Azure DevOps credentials saved successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {e}")


@router.post("/azure-devops/disconnect")
async def azure_devops_disconnect(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored Azure DevOps token."""
    current_user.azure_devops_token = None
    current_user.azure_devops_username = None
    db.commit()
    return {"status": "disconnected"}


class ValidateGitRepoRequest(BaseModel):
    repo_url: str
    pat: Optional[str] = None
    provider: str = "github"  # "github" or "azure-devops"


@router.post("/git/validate-connection")
async def validate_git_connection(
    payload: ValidateGitRepoRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Validate git repository URL and PAT by attempting a lightweight operation.
    For Azure DevOps, this normalizes the URL and tests authentication.
    For GitHub, this tests if the repo is accessible.
    """
    try:
        repo_url = payload.repo_url.strip()
        pat = (payload.pat or "").strip()
        provider = payload.provider.lower()
        
        if not repo_url:
            raise HTTPException(status_code=400, detail="Repository URL is required")
        
        # Normalize the URL based on provider
        if provider == "azure-devops":
            try:
                # Parse and normalize Azure DevOps URL
                parsed = azure_devops_service.parse_azure_repo_url(repo_url)
                normalized_url = parsed["url"]
                organization = parsed["organization"]
                project = parsed["project"]
                repo = parsed["repo"]
                
                # If PAT is provided, test the connection
                if pat:
                    try:
                        # Try to list repositories to validate credentials
                        repos = await azure_devops_service.list_project_repositories(
                            organization=organization,
                            project=project,
                            pat=pat
                        )
                        
                        # Check if the specific repo exists
                        repo_found = any(r.get("name") == repo for r in repos)
                        
                        return {
                            "valid": True,
                            "normalized_url": normalized_url,
                            "provider": "azure-devops",
                            "organization": organization,
                            "project": project,
                            "repo": repo,
                            "pat_valid": True,
                            "repo_accessible": repo_found,
                            "message": f"Connection successful! Repository '{repo}' {'found' if repo_found else 'not found in project'}."
                        }
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 401:
                            raise HTTPException(
                                status_code=401,
                                detail="Invalid PAT. Please check your Personal Access Token has 'Code (Read & Write)' permissions."
                            )
                        elif e.response.status_code == 404:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Project '{project}' not found in organization '{organization}'. Please verify the URL."
                            )
                        else:
                            raise HTTPException(
                                status_code=e.response.status_code,
                                detail=f"Azure DevOps API error: {e.response.text[:200]}"
                            )
                    except Exception as e:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to validate Azure DevOps connection: {str(e)[:200]}"
                        )
                else:
                    # No PAT provided, just validate URL format
                    return {
                        "valid": True,
                        "normalized_url": normalized_url,
                        "provider": "azure-devops",
                        "organization": organization,
                        "project": project,
                        "repo": repo,
                        "pat_valid": None,
                        "repo_accessible": None,
                        "message": "URL format is valid. Provide PAT to test connection."
                    }
                    
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Azure DevOps URL: {str(e)}"
                )
        
        elif provider == "github":
            # For GitHub, validate URL format
            if not repo_url.startswith("https://github.com/"):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid GitHub URL. Must start with https://github.com/"
                )
            
            # Extract owner/repo from URL
            parts = repo_url.replace("https://github.com/", "").replace(".git", "").strip("/").split("/")
            if len(parts) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid GitHub URL format. Expected: https://github.com/owner/repo"
                )
            
            owner, repo = parts[0], parts[1]
            
            # If PAT provided, test connection
            if pat:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(
                            f"https://api.github.com/repos/{owner}/{repo}",
                            headers={"Authorization": f"token {pat}"}
                        )
                        
                        if response.status_code == 200:
                            return {
                                "valid": True,
                                "normalized_url": f"https://github.com/{owner}/{repo}.git",
                                "provider": "github",
                                "owner": owner,
                                "repo": repo,
                                "pat_valid": True,
                                "repo_accessible": True,
                                "message": f"Connection successful! Repository '{owner}/{repo}' is accessible."
                            }
                        elif response.status_code == 401:
                            raise HTTPException(
                                status_code=401,
                                detail="Invalid GitHub token. Please check your Personal Access Token."
                            )
                        elif response.status_code == 404:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Repository '{owner}/{repo}' not found or not accessible with this token."
                            )
                        else:
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"GitHub API error: {response.text[:200]}"
                            )
                except httpx.TimeoutException:
                    raise HTTPException(
                        status_code=504,
                        detail="GitHub API request timed out. Please try again."
                    )
            else:
                # No PAT, just validate URL
                return {
                    "valid": True,
                    "normalized_url": f"https://github.com/{owner}/{repo}.git",
                    "provider": "github",
                    "owner": owner,
                    "repo": repo,
                    "pat_valid": None,
                    "repo_accessible": None,
                    "message": "URL format is valid. Provide PAT to test connection."
                }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {provider}. Use 'github' or 'azure-devops'."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)[:200]}"
        )


@router.get("/azure-devops/repos")
async def azure_devops_repos(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = 1,
    per_page: int = 30,
):
    """List Azure DevOps repositories available to the authenticated user."""
    access_token = (current_user.azure_devops_token or "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Azure DevOps not connected")
    try:
        repos = await azure_devops_oauth_service.list_repos(
            access_token,
            per_page=per_page,
            page=page,
        )
        return {"repos": repos}
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        raise HTTPException(status_code=status_code, detail="Failed to fetch Azure DevOps repositories.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Azure DevOps repositories: {e}")


class ListProjectReposRequest(BaseModel):
    project_token: str
    organization: str
    project: str


@router.post("/azure-devops/list-project-repos")
async def list_project_repos(
    payload: ListProjectReposRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """List repositories in a specific Azure DevOps project."""
    try:
        # Try to get project-specific credentials first
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == payload.project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        access_token = None
        
        # Try OAuth token from user's connected account
        user_token = (current_user.azure_devops_token or "").strip()
        access_token = user_token or None
        
        # Try project-level PAT if user-level OAuth is empty
        db_pat = None
        if not access_token:
            cred = _resolve_project_global_credential(db, current_user, payload.project_token)
            if cred and cred.git_token:
                db_pat = cred.git_token
        
        if not access_token and not db_pat:
            raise HTTPException(
                status_code=400,
                detail="Azure DevOps authentication required. Please connect your account or provide a PAT in project settings."
            )
        
        repos = await azure_devops_service.list_project_repositories(
            organization=payload.organization,
            project=payload.project,
            pat=db_pat,
            access_token=access_token,
        )
        
        return {"repos": repos}
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        detail = "Failed to fetch repositories from Azure DevOps project."
        if e.response is not None:
            try:
                error_payload = e.response.json() or {}
                detail = str(error_payload.get("message") or error_payload.get("value") or detail)
            except Exception:
                detail = str(e.response.text or detail)
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list project repositories: {e}")


class RepoContextRequest(BaseModel):
    owner: str
    repo: str
    branch: str = "main"
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class AzureDevOpsRepoContextRequest(BaseModel):
    repo_url: str
    token: Optional[str] = None
    branch: Optional[str] = None
    project_token: Optional[str] = None


@router.post("/github/repo-context")
async def github_repo_context(
    payload: RepoContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch repository source code and return a structured text context
    suitable for feeding into the AI model alongside the BRD.
    """
    provided_token = (payload.token or "").strip() or None
    provided_username = (payload.username or "").strip() or None
    provided_password = str(payload.password or "") if payload.password is not None else None
    has_basic_credentials = bool(provided_username or (provided_password is not None and provided_password != ""))
    if has_basic_credentials and not (provided_username and provided_password):
        raise HTTPException(status_code=400, detail="Provide both GitHub username and password.")
    if provided_token and has_basic_credentials:
        raise HTTPException(status_code=400, detail="Use either PAT or username/password, not both.")

    saved_oauth_token = (current_user.github_token or "").strip() or None
    token_to_use = provided_token if provided_token else saved_oauth_token

    owner, repo = github_service.normalize_repo_identity(payload.owner, payload.repo)
    branch = (payload.branch or "main").strip() or "main"
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL or owner/repo values.")

    async def _build_context(
        token_value: Optional[str],
        username_value: Optional[str] = None,
        password_value: Optional[str] = None,
    ) -> Dict[str, str]:
        return await github_service.build_repo_context(
            token_value,
            owner,
            repo,
            branch,
            username=username_value,
            password=password_value,
        )

    async def _build_context_from_zip() -> Dict[str, str]:
        return await github_service.build_repo_context_from_zip(
            owner,
            repo,
            branch,
        )

    def _is_rate_limited(err: httpx.HTTPStatusError) -> bool:
        if err.response is None:
            return False
        if err.response.status_code != 403:
            return False
        try:
            message = str((err.response.json() or {}).get("message") or "").lower()
        except Exception:
            message = str(err.response.text or "").lower()
        return "rate limit" in message

    def _raise_repo_context_error(err: httpx.HTTPStatusError) -> None:
        status_code = err.response.status_code if err.response is not None else 502
        response_msg = ""
        if err.response is not None:
            try:
                response_msg = str((err.response.json() or {}).get("message") or "").strip()
            except Exception:
                response_msg = str(err.response.text or "").strip()
        response_msg_lc = response_msg.lower()

        if status_code == 404:
            detail = (
                "Repository or branch was not found. Verify the URL, remove any trailing .git, "
                "and provide a PAT for private repositories."
            )
        elif status_code == 403 and "rate limit" in response_msg_lc:
            detail = "GitHub API rate limit exceeded. Add a valid PAT or reconnect GitHub OAuth and try again."
        elif status_code in (401, 403):
            detail = "GitHub authentication failed or access denied. Check your PAT, username/password, or OAuth access."
        elif status_code == 409:
            detail = (
                "The repository is empty (contains no commits). "
                "Please push at least one commit to the repository before attempting to use it."
            )
        else:
            detail = f"Failed to fetch repository context from GitHub (HTTP {status_code})."
        raise HTTPException(status_code=status_code, detail=detail)

    try:
        username_to_use = provided_username if has_basic_credentials else None
        password_to_use = provided_password if has_basic_credentials else None
        token_for_primary = None if has_basic_credentials else token_to_use
        repo_data = await _build_context(token_for_primary, username_to_use, password_to_use)
        return {
            "context": repo_data["context"],
            "repo": f"{repo_data['owner']}/{repo_data['repo']}",
            "branch": repo_data["branch"],
        }
    except httpx.HTTPStatusError as e:
        if _is_rate_limited(e):
            try:
                repo_data = await _build_context_from_zip()
                return {
                    "context": repo_data["context"],
                    "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                    "branch": repo_data["branch"],
                }
            except httpx.HTTPStatusError:
                # If zip fallback also fails, continue to the regular error path below.
                pass

        # If saved OAuth token is stale/invalid and no PAT was explicitly provided,
        # retry without auth so public repositories still work.
        status_code = e.response.status_code if e.response is not None else 502
        should_retry_without_auth = (
            status_code in (401, 403)
            and provided_token is None
            and not has_basic_credentials
            and saved_oauth_token is not None
        )
        if should_retry_without_auth:
            try:
                repo_data = await _build_context(None)
                return {
                    "context": repo_data["context"],
                    "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                    "branch": repo_data["branch"],
                }
            except httpx.HTTPStatusError as retry_err:
                if _is_rate_limited(retry_err):
                    try:
                        repo_data = await _build_context_from_zip()
                        return {
                            "context": repo_data["context"],
                            "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                            "branch": repo_data["branch"],
                        }
                    except httpx.HTTPStatusError:
                        pass
                _raise_repo_context_error(retry_err)
        _raise_repo_context_error(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build repo context: {e}")

@router.post("/azure-devops/repo-context")
async def azure_devops_repo_context(
    payload: AzureDevOpsRepoContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fetch Azure DevOps repository source and return a structured context
    suitable for feeding into the AI model alongside BRD content.
    """
    provided_token = (payload.token or "").strip() or None
    saved_oauth_token = (current_user.azure_devops_token or "").strip() or None
    
    # Try to find a project-specific PAT in the database if no token is provided
    db_pat = None
    if not provided_token and not saved_oauth_token:
        project_token = payload.project_token
        # If no project_token in payload, try to use user's last active project
        if not project_token and current_user.last_project_token:
            project_token = current_user.last_project_token
            
        if project_token:
            cred = _resolve_project_global_credential(db, current_user, project_token)
            if cred and cred.git_token:
                db_pat = cred.git_token

    token_to_use = provided_token or saved_oauth_token or db_pat
    branch = (payload.branch or "").strip() or None

    try:
        repo_data = await azure_devops_service.build_repo_context_from_url(
            repo_url=payload.repo_url,
            pat=token_to_use,
            branch=branch,
        )
        return {
            "context": repo_data["context"],
            "repo": repo_data["repo"],
            "branch": repo_data["branch"],
            "provider": "azure-devops",
            "url": repo_data["url"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        response_msg = ""
        if e.response is not None:
            try:
                response_msg = str((e.response.json() or {}).get("message") or "").strip()
            except Exception:
                response_msg = str(e.response.text or "").strip()
        response_msg_lc = response_msg.lower()

        if status_code == 404:
            detail = (
                "Azure DevOps repository or branch was not found. Verify organization/project/repository URL "
                "and branch name."
            )
        elif status_code in (401, 403):
            if "pat" in response_msg_lc or "token" in response_msg_lc:
                detail = "Azure DevOps authentication failed. Check your PAT permissions or reconnect OAuth."
            else:
                detail = "Azure DevOps authentication failed or access denied. Provide a valid PAT or reconnect OAuth."
        elif status_code == 409:
            detail = (
                "The repository is empty (contains no commits). "
                "Please push at least one commit to the repository before attempting to use it."
            )
        else:
            detail = f"Failed to fetch repository context from Azure DevOps (HTTP {status_code})."
        raise HTTPException(status_code=status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build Azure DevOps repo context: {e}")


# --- Extracted Block (Lines 11383-11398) ---
@router.get("/api/github/pr-status/{project_token}")
async def get_pr_status(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the status of merged branches and created PRs."""
    from app.services.agents.agent_service import _ensure_project_state
    state = _ensure_project_state(project_token)
    return {
        "project_token": project_token,
        "merged_branches": state.get("merged_branches", []),
        "merge_queue_length": len(state.get("git_merge_queue", [])),
        "is_merging": state.get("git_merge_running", False)
    }



