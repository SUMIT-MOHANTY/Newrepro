"""
Azure DevOps OAuth and repository browsing service.
Provides OAuth URL creation, code exchange, profile lookup, and repo listing.
"""

from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from config import settings


AZDO_OAUTH_AUTHORIZE_URL = "https://app.vssps.visualstudio.com/oauth2/authorize"
AZDO_OAUTH_TOKEN_URL = "https://app.vssps.visualstudio.com/oauth2/token"
AZDO_PROFILE_URL = "https://app.vssps.visualstudio.com/_apis/profile/profiles/me"
AZDO_ACCOUNTS_URL = "https://app.vssps.visualstudio.com/_apis/accounts"


def _normalize_branch(value: Optional[str]) -> str:
    branch = str(value or "").strip()
    if branch.startswith("refs/heads/"):
        branch = branch[len("refs/heads/"):]
    return branch or "main"


def _auth_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _frontend_callback_url() -> str:
    return f"{settings.frontend_url.rstrip('/')}/azure-devops/callback"


def get_oauth_url(state: str = "", client_id: Optional[str] = None, client_secret: Optional[str] = None, checked_project_credentials: bool = False) -> str:
    """
    Get Azure DevOps OAuth URL.
    
    Args:
        state: OAuth state parameter
        client_id: Optional project-specific client_id. If not provided, uses global settings.
        client_secret: Optional project-specific client_secret (not used in URL, but validated).
        checked_project_credentials: True if project credentials were checked (even if they were None/empty).
    """
    # Use project-specific client_id if provided, otherwise fall back to global settings
    effective_client_id = (client_id or "").strip() or (settings.azure_devops_client_id or "").strip()
    if not effective_client_id:
        if checked_project_credentials:
            # Project-specific credentials were checked but are empty/NULL
            raise ValueError("Azure DevOps OAuth is not configured for this project. Please set azure_devops_client_id and azure_devops_client_secret for this project in the database, or configure global AZURE_DEVOPS_CLIENT_ID in backend .env file.")
        else:
            # No project credentials provided, and global is also not set
            raise ValueError("AZURE_DEVOPS_CLIENT_ID is not configured. Please set AZURE_DEVOPS_CLIENT_ID and AZURE_DEVOPS_CLIENT_SECRET in backend .env file.")
    
    # Validate client_secret if provided (for consistency check)
    if client_secret:
        effective_secret = (client_secret or "").strip()
        if not effective_secret:
            raise ValueError("AZURE_DEVOPS_CLIENT_SECRET is not configured for this project")

    redirect_uri = quote(_frontend_callback_url(), safe="")
    scope = quote("vso.code", safe="")
    encoded_state = quote(state or "", safe="")

    return (
        f"{AZDO_OAUTH_AUTHORIZE_URL}"
        f"?client_id={quote(effective_client_id, safe='')}"
        f"&response_type=Assertion"
        f"&state={encoded_state}"
        f"&scope={scope}"
        f"&redirect_uri={redirect_uri}"
    )


async def exchange_code_for_token(code: str, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchange OAuth code for access token.
    
    Args:
        code: OAuth authorization code
        client_id: Optional project-specific client_id. If not provided, uses global settings.
        client_secret: Optional project-specific client_secret. If not provided, uses global settings.
    """
    # Use project-specific credentials if provided, otherwise fall back to global settings
    effective_client_id = (client_id or "").strip() or (settings.azure_devops_client_id or "").strip()
    effective_client_secret = (client_secret or "").strip() or (settings.azure_devops_client_secret or "").strip()
    
    if not effective_client_id or not effective_client_secret:
        raise ValueError("Azure DevOps OAuth credentials are not configured")

    payload = {
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_secret,
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": code,
        "redirect_uri": _frontend_callback_url(),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            AZDO_OAUTH_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise ValueError(f"Azure DevOps OAuth error: {message}")
        return data


async def get_current_profile(access_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            AZDO_PROFILE_URL,
            params={"api-version": "7.1-preview.3"},
            headers=_auth_headers(access_token),
        )
        resp.raise_for_status()
        return resp.json()


async def list_repos(access_token: str, per_page: int = 30, page: int = 1) -> List[Dict[str, Any]]:
    profile = await get_current_profile(access_token)
    profile_id = str(profile.get("id") or "").strip()
    if not profile_id:
        return []

    async with httpx.AsyncClient(timeout=45.0) as client:
        accounts_resp = await client.get(
            AZDO_ACCOUNTS_URL,
            params={
                "memberId": profile_id,
                "api-version": "7.1-preview.1",
            },
            headers=_auth_headers(access_token),
        )
        accounts_resp.raise_for_status()
        accounts_payload = accounts_resp.json() or {}
        accounts = accounts_payload.get("value") or []

        repos: List[Dict[str, Any]] = []
        max_accounts = 5
        max_projects_per_account = 40

        for account in accounts[:max_accounts]:
            org = str(account.get("accountName") or "").strip()
            if not org:
                continue

            projects_resp = await client.get(
                f"https://dev.azure.com/{quote(org, safe='')}/_apis/projects",
                params={
                    "stateFilter": "all",
                    "$top": max_projects_per_account,
                    "api-version": "7.1-preview.4",
                },
                headers=_auth_headers(access_token),
            )
            if projects_resp.status_code >= 400:
                continue

            projects_payload = projects_resp.json() if "application/json" in (projects_resp.headers.get("content-type") or "") else {}
            projects = projects_payload.get("value") or []

            for project in projects:
                project_name = str(project.get("name") or "").strip()
                if not project_name:
                    continue
                repos_resp = await client.get(
                    f"https://dev.azure.com/{quote(org, safe='')}/{quote(project_name, safe='')}/_apis/git/repositories",
                    params={"api-version": "7.1"},
                    headers=_auth_headers(access_token),
                )
                if repos_resp.status_code >= 400:
                    continue

                repos_payload = repos_resp.json() if "application/json" in (repos_resp.headers.get("content-type") or "") else {}
                repo_values = repos_payload.get("value") or []

                for repo in repo_values:
                    repo_name = str(repo.get("name") or "").strip()
                    if not repo_name:
                        continue
                    default_branch = _normalize_branch(repo.get("defaultBranch"))
                    repo_url = f"https://dev.azure.com/{org}/{project_name}/_git/{repo_name}"
                    repos.append(
                        {
                            "id": str(repo.get("id") or f"{org}:{project_name}:{repo_name}"),
                            "name": repo_name,
                            "full_name": f"{org}/{project_name}/{repo_name}",
                            "description": repo.get("project", {}).get("description"),
                            "language": None,
                            "private": True,
                            "html_url": repo.get("webUrl") or repo_url,
                            "default_branch": default_branch,
                            "updated_at": repo.get("project", {}).get("lastUpdateTime"),
                            "stargazers_count": 0,
                            "organization": org,
                            "project": project_name,
                            "repo_url": repo_url,
                        }
                    )

    repos.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    offset = max(0, (max(1, page) - 1) * max(1, per_page))
    return repos[offset: offset + max(1, per_page)]

