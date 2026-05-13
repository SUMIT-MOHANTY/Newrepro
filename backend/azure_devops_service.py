"""
Azure DevOps Integration Service for BRD Analysis.
Builds repository context for AI analysis from Azure DevOps Git repositories.
"""

from __future__ import annotations

import base64
import os
import posixpath
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx


CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb",
    ".cs", ".cpp", ".c", ".h", ".swift", ".kt", ".scala", ".php",
    ".html", ".css", ".scss", ".sql", ".sh", ".yaml", ".yml",
    ".json", ".toml", ".xml", ".md", ".txt", ".env.example",
    ".dockerfile", ".tf", ".proto",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".DS_Store", "Thumbs.db",
}

MAX_FILE_SIZE_BYTES = 100_000
MAX_FILES_TO_FETCH = 40


def _normalize_branch(value: Optional[str]) -> str:
    branch = str(value or "").strip()
    if branch.startswith("refs/heads/"):
        branch = branch[len("refs/heads/"):]
    if branch.startswith("GB"):
        branch = branch[2:]
    return branch.strip()


def _extract_branch_from_query(query: Dict[str, List[str]]) -> Optional[str]:
    for key in ("version", "versionDescriptor.version"):
        values = query.get(key) or []
        for value in values:
            branch = _normalize_branch(value)
            if branch:
                return branch
    return None


def parse_azure_repo_url(repo_url: str) -> Dict[str, Optional[str]]:
    raw = str(repo_url or "").strip()
    if not raw:
        raise ValueError("Azure DevOps repository URL is required.")

    normalized = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    parts = [unquote(p) for p in (parsed.path or "").split("/") if p]

    organization = ""
    project = ""
    repo = ""
    is_project_url = False

    if host.endswith("dev.azure.com"):
        if len(parts) >= 2 and (len(parts) < 4 or parts[2].lower() != "_git"):
            # This is a project URL (org/project) without /_git/{repo}
            if len(parts) == 2:
                organization = parts[0]
                project = parts[1]
                is_project_url = True
            else:
                raise ValueError(
                    "Invalid Azure DevOps URL. Use format: https://dev.azure.com/{org}/{project}/_git/{repo} or https://dev.azure.com/{org}/{project}"
                )
        elif len(parts) >= 4 and parts[2].lower() == "_git":
            # This is a repository URL
            organization = parts[0]
            project = parts[1]
            repo = parts[3]
        else:
            raise ValueError(
                "Invalid Azure DevOps URL. Use format: https://dev.azure.com/{org}/{project}/_git/{repo} or https://dev.azure.com/{org}/{project}"
            )
    elif host.endswith(".visualstudio.com"):
        organization = host.split(".visualstudio.com", 1)[0]
        if len(parts) >= 1 and (len(parts) < 3 or parts[1].lower() != "_git"):
            # This is a project URL
            if len(parts) == 1:
                project = parts[0]
                is_project_url = True
            else:
                raise ValueError(
                    "Invalid Azure DevOps URL. Use format: https://{org}.visualstudio.com/{project}/_git/{repo} or https://{org}.visualstudio.com/{project}"
                )
        elif len(parts) >= 3 and parts[1].lower() == "_git":
            # This is a repository URL
            project = parts[0]
            repo = parts[2]
        else:
            raise ValueError(
                "Invalid Azure DevOps URL. Use format: https://{org}.visualstudio.com/{project}/_git/{repo} or https://{org}.visualstudio.com/{project}"
            )
    else:
        raise ValueError(
            "Invalid Azure DevOps URL host. Use dev.azure.com or *.visualstudio.com."
        )

    if is_project_url:
        if not organization or not project:
            raise ValueError("Unable to parse organization/project from Azure DevOps project URL.")
        
        # URL-encode the components for git compatibility
        from urllib.parse import quote
        org_encoded = quote(organization, safe='')
        project_encoded = quote(project, safe='')
        
        return {
            "organization": organization,
            "project": project,
            "repo": None,
            "branch": None,
            "url": f"https://dev.azure.com/{org_encoded}/{project_encoded}",
            "is_project_url": True,
        }

    repo = repo.replace(".git", "").strip()
    if not organization or not project or not repo:
        raise ValueError("Unable to parse organization/project/repository from Azure DevOps URL.")

    inferred_branch = _extract_branch_from_query(parse_qs(parsed.query or ""))

    # URL-encode the components for git compatibility (spaces become %20)
    from urllib.parse import quote
    org_encoded = quote(organization, safe='')
    project_encoded = quote(project, safe='')
    repo_encoded = quote(repo, safe='')

    return {
        "organization": organization,
        "project": project,
        "repo": repo,
        "branch": inferred_branch,
        "url": f"https://dev.azure.com/{org_encoded}/{project_encoded}/_git/{repo_encoded}",
        "is_project_url": False,
    }


async def list_project_repositories(
    organization: str,
    project: str,
    pat: Optional[str] = None,
    access_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all repositories in a specific Azure DevOps project.
    
    Args:
        organization: Azure DevOps organization name
        project: Project name
        pat: Personal Access Token (optional, for PAT-based auth)
        access_token: OAuth access token (optional, for OAuth-based auth)
    
    Returns:
        List of repository dictionaries with name, id, url, default_branch, etc.
    """
    if not pat and not access_token:
        raise ValueError("Either PAT or access_token is required.")
    
    headers = _auth_headers(pat) if pat else {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        repos_url = f"https://dev.azure.com/{quote(organization, safe='')}/{quote(project, safe='')}/_apis/git/repositories"
        resp = await client.get(
            repos_url,
            params={"api-version": "7.1"},
            headers=headers,
        )
        resp.raise_for_status()
        
        payload = resp.json() if "application/json" in (resp.headers.get("content-type") or "") else {}
        repo_values = payload.get("value") or []
        
        repos = []
        for repo in repo_values:
            repo_name = str(repo.get("name") or "").strip()
            if not repo_name:
                continue
            default_branch = _normalize_branch(repo.get("defaultBranch"))
            repo_url = f"https://dev.azure.com/{organization}/{project}/_git/{repo_name}"
            repos.append({
                "id": str(repo.get("id") or f"{organization}:{project}:{repo_name}"),
                "name": repo_name,
                "full_name": f"{organization}/{project}/{repo_name}",
                "description": repo.get("project", {}).get("description"),
                "language": None,
                "private": True,
                "html_url": repo.get("webUrl") or repo_url,
                "default_branch": default_branch,
                "updated_at": repo.get("project", {}).get("lastUpdateTime"),
                "stargazers_count": 0,
                "organization": organization,
                "project": project,
                "repo_url": repo_url,
            })
        
        return repos


def _auth_headers(pat: Optional[str]) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    cleaned_pat = str(pat or "").strip()
    if cleaned_pat:
        basic = base64.b64encode(f":{cleaned_pat}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"
    return headers


import time
_REPO_PUBLIC_CACHE: Dict[str, Tuple[bool, float]] = {}
_CACHE_TTL_SECONDS = 600  # 10 minutes

async def is_repo_public(
    organization: str,
    project: str,
    repo: str,
    pat: Optional[str] = None,
) -> bool:
    """
    Check if an Azure DevOps repository is accessible. 
    Results are cached permanently for the current PAT/URL combination.
    """
    url = _repo_api_base(organization, project, repo)
    
    # Create a unique cache key based on repo and PAT
    pat_key = str(pat or "")[-8:] # Use last 8 chars of PAT for the key
    cache_key = f"{url}:{pat_key}"
    
    current_time = time.time()
    # If we have already checked this specific combination, return the cached result
    if cache_key in _REPO_PUBLIC_CACHE:
        result, _ = _REPO_PUBLIC_CACHE[cache_key]
        return result

    has_pat = bool(pat and len(str(pat).strip()) > 0)
    import logging
    logger = logging.getLogger("azure_devops_service")
    logger.info(f"[is_repo_public] Checking {url} (Using PAT: {has_pat})")

    # Use follow_redirects=False to avoid being pushed to the Microsoft login page
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        try:
            resp = await client.get(
                url,
                params={"api-version": "7.1"},
                headers=_auth_headers(pat),
            )
            
            is_accessible = (resp.status_code == 200)
            
            if not is_accessible:
                logger.warning(f"[is_repo_public] Repo {repo} returned {resp.status_code}. Accessible: False")
            
            # Update cache
            _REPO_PUBLIC_CACHE[cache_key] = (is_accessible, current_time)
            return is_accessible
        except Exception as e:
            logger.error(f"[is_repo_public] Error checking repo {repo}: {e}")
            return False


def _repo_api_base(organization: str, project: str, repo: str) -> str:
    org_enc = quote(organization, safe="")
    project_enc = quote(project, safe="")
    repo_enc = quote(repo, safe="")
    return f"https://dev.azure.com/{org_enc}/{project_enc}/_apis/git/repositories/{repo_enc}"


async def _get_repo_metadata(
    organization: str,
    project: str,
    repo: str,
    pat: Optional[str],
) -> Dict[str, Any]:
    url = _repo_api_base(organization, project, repo)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            url,
            params={"api-version": "7.1"},
            headers=_auth_headers(pat),
        )
        resp.raise_for_status()
        return resp.json()


async def _list_repo_files(
    organization: str,
    project: str,
    repo: str,
    branch: str,
    pat: Optional[str],
) -> List[Dict[str, Any]]:
    base = _repo_api_base(organization, project, repo)
    url = f"{base}/items"

    params = {
        "scopePath": "/",
        "recursionLevel": "Full",
        "includeContentMetadata": "true",
        "latestProcessedChange": "false",
        "versionDescriptor.versionType": "branch",
        "versionDescriptor.version": branch,
        "api-version": "7.1",
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=_auth_headers(pat))
        resp.raise_for_status()
        payload = resp.json() if "application/json" in (resp.headers.get("content-type") or "") else {}

    files: List[Dict[str, Any]] = []
    for item in payload.get("value", []) or []:
        if item.get("isFolder"):
            continue
        rel_path = str(item.get("path") or "").strip().lstrip("/")
        if not rel_path:
            continue
        size_raw = (item.get("contentMetadata") or {}).get("size", item.get("size", 0))
        try:
            size = int(size_raw or 0)
        except (TypeError, ValueError):
            size = 0
        files.append({"path": rel_path, "type": "blob", "size": size})
    return files


def _should_include_file(path: str, size: int) -> bool:
    basename = os.path.basename(path)
    if basename in SKIP_FILES:
        return False

    parts = path.split("/")
    if any(p.startswith(".") and p not in {".env.example", ".azure-pipelines"} for p in parts):
        return False

    skip_dirs = {"node_modules", "vendor", "dist", "build", "__pycache__", ".git", "venv", ".venv"}
    if any(p in skip_dirs for p in parts):
        return False

    if size > MAX_FILE_SIZE_BYTES:
        return False

    _, ext = os.path.splitext(basename)
    return ext.lower() in CODE_EXTENSIONS


async def _get_file_content(
    organization: str,
    project: str,
    repo: str,
    branch: str,
    path: str,
    pat: Optional[str],
) -> Optional[str]:
    base = _repo_api_base(organization, project, repo)
    url = f"{base}/items"
    params = {
        "path": f"/{path.lstrip('/')}",
        "versionDescriptor.versionType": "branch",
        "versionDescriptor.version": branch,
        "download": "true",
        "api-version": "7.1",
    }

    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=_auth_headers(pat))
        if resp.status_code != 200:
            return None
        text = resp.content.decode("utf-8", errors="ignore")
        return text if text.strip() else None


async def build_repo_context_from_url(
    repo_url: str,
    pat: Optional[str] = None,
    branch: Optional[str] = None,
) -> Dict[str, str]:
    parsed = parse_azure_repo_url(repo_url)
    organization = str(parsed["organization"] or "")
    project = str(parsed["project"] or "")
    repo = str(parsed["repo"] or "")

    explicit_branch = _normalize_branch(branch)
    inferred_branch = _normalize_branch(parsed.get("branch"))

    default_branch = ""
    try:
        metadata = await _get_repo_metadata(organization, project, repo, pat)
        default_branch = _normalize_branch(metadata.get("defaultBranch"))
    except httpx.HTTPStatusError:
        # Let list/fetch calls surface auth/repo errors if metadata is unavailable.
        default_branch = ""

    candidates: List[str] = []
    for candidate in [explicit_branch, inferred_branch, default_branch, "main", "master"]:
        normalized = _normalize_branch(candidate)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    last_error: Optional[Exception] = None
    tree: List[Dict[str, Any]] = []
    resolved_branch = candidates[0] if candidates else "main"

    for candidate in candidates:
        try:
            tree = await _list_repo_files(organization, project, repo, candidate, pat)
            resolved_branch = candidate
            break
        except httpx.HTTPStatusError as err:
            last_error = err
            status_code = err.response.status_code if err.response is not None else 0
            if status_code == 404:
                continue
            raise

    if not tree and last_error:
        raise last_error

    tree_lines = [f"  {item['path']}" for item in tree if item.get("type") == "blob"]
    tree_text = "\n".join(tree_lines[:200])

    files_to_fetch = [
        item for item in tree
        if item.get("type") == "blob" and _should_include_file(item.get("path", ""), int(item.get("size", 0)))
    ]

    priority_names = {
        "README.md", "readme.md", "README", "package.json", "requirements.txt",
        "Pipfile", "pyproject.toml", "Dockerfile", "docker-compose.yml",
        "docker-compose.yaml", ".env.example", "Makefile", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle",
    }
    files_to_fetch.sort(
        key=lambda f: (0 if posixpath.basename(str(f.get("path", ""))) in priority_names else 1, str(f.get("path", "")))
    )
    files_to_fetch = files_to_fetch[:MAX_FILES_TO_FETCH]

    file_contents: List[str] = []
    for item in files_to_fetch:
        path = str(item.get("path") or "")
        if not path:
            continue
        content = await _get_file_content(organization, project, repo, resolved_branch, path, pat)
        if content:
            file_contents.append(f"--- FILE: {path} ---\n{content}\n")

    context = (
        "AZURE DEVOPS REPOSITORY CONTEXT\n"
        "===============================\n"
        f"Repository: {organization}/{project}/{repo} (branch: {resolved_branch})\n\n"
        f"FILE TREE:\n{tree_text}\n\n"
        f"KEY SOURCE FILES ({len(file_contents)} files):\n"
        f"{''.join(file_contents)}\n"
    )

    return {
        "context": context,
        "organization": organization,
        "project": project,
        "repo_name": repo,
        "repo": f"{organization}/{project}/{repo}",
        "branch": resolved_branch,
        "url": f"https://dev.azure.com/{organization}/{project}/_git/{repo}",
    }
