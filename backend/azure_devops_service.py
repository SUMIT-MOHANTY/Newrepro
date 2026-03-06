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

    if host.endswith("dev.azure.com"):
        if len(parts) < 4 or parts[2].lower() != "_git":
            raise ValueError(
                "Invalid Azure DevOps URL. Use format: https://dev.azure.com/{org}/{project}/_git/{repo}"
            )
        organization = parts[0]
        project = parts[1]
        repo = parts[3]
    elif host.endswith(".visualstudio.com"):
        organization = host.split(".visualstudio.com", 1)[0]
        if len(parts) < 3 or parts[1].lower() != "_git":
            raise ValueError(
                "Invalid Azure DevOps URL. Use format: https://{org}.visualstudio.com/{project}/_git/{repo}"
            )
        project = parts[0]
        repo = parts[2]
    else:
        raise ValueError(
            "Invalid Azure DevOps URL host. Use dev.azure.com or *.visualstudio.com."
        )

    repo = repo.replace(".git", "").strip()
    if not organization or not project or not repo:
        raise ValueError("Unable to parse organization/project/repository from Azure DevOps URL.")

    inferred_branch = _extract_branch_from_query(parse_qs(parsed.query or ""))

    return {
        "organization": organization,
        "project": project,
        "repo": repo,
        "branch": inferred_branch,
        "url": f"https://dev.azure.com/{organization}/{project}/_git/{repo}",
    }


def _auth_headers(pat: Optional[str]) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    cleaned_pat = str(pat or "").strip()
    if cleaned_pat:
        basic = base64.b64encode(f":{cleaned_pat}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"
    return headers


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
    async with httpx.AsyncClient(timeout=30.0) as client:
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

    async with httpx.AsyncClient(timeout=60.0) as client:
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

    async with httpx.AsyncClient(timeout=45.0) as client:
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
