"""
GitHub Integration Service for BRD Analysis
Handles OAuth flow & fetching repository data for AI context.
"""
import io
import base64
import posixpath
import re
import zipfile
import httpx
from typing import Optional, Dict, Any, List, Tuple
from config import settings

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"

# File extensions we care about for repo summaries
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb",
    ".cs", ".cpp", ".c", ".h", ".swift", ".kt", ".scala", ".php",
    ".html", ".css", ".scss", ".sql", ".sh", ".yaml", ".yml",
    ".json", ".toml", ".xml", ".md", ".txt", ".env.example",
    ".dockerfile", ".tf", ".proto",
}

# Files to always skip
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".DS_Store", "Thumbs.db",
}

MAX_FILE_SIZE_BYTES = 100_000  # ~100 KB per file
MAX_FILES_TO_FETCH = 40       # cap context to avoid token overflow


def _build_github_headers(
    accept: str,
    token: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, str]:
    headers = {"Accept": accept}
    cleaned_token = (token or "").strip()
    cleaned_username = (username or "").strip()
    raw_password = str(password or "")

    if cleaned_token:
        headers["Authorization"] = f"Bearer {cleaned_token}"
    elif cleaned_username and raw_password:
        basic = base64.b64encode(f"{cleaned_username}:{raw_password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"

    return headers


def normalize_repo_identity(owner: str, repo: str) -> Tuple[str, str]:
    """Normalize owner/repo values from user-provided URLs."""
    normalized_owner = str(owner or "").strip().strip("/")
    normalized_repo = str(repo or "").strip().strip("/")
    if normalized_repo.lower().endswith(".git"):
        normalized_repo = normalized_repo[:-4]
    return normalized_owner, normalized_repo


def get_oauth_url(state: str = "") -> str:
    """Return the GitHub OAuth authorize URL."""
    client_id = settings.github_client_id
    if not client_id:
        raise ValueError("GITHUB_CLIENT_ID is not configured")
    scope = "repo read:user"
    url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={client_id}"
        f"&scope={scope}"
        f"&state={state}"
    )
    return url


async def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange an OAuth authorization code for an access token."""
    client_id = settings.github_client_id
    client_secret = settings.github_client_secret
    if not client_id or not client_secret:
        raise ValueError("GitHub OAuth credentials not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")
        return data  # { access_token, token_type, scope }


async def get_github_user(token: str) -> Dict[str, Any]:
    """Get GitHub user info."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def list_repos(token: str, per_page: int = 30, page: int = 1) -> List[Dict[str, Any]]:
    """List repositories the authenticated user has access to."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/user/repos",
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
                "type": "all",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        repos = resp.json()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description"),
                "language": r.get("language"),
                "private": r["private"],
                "html_url": r["html_url"],
                "default_branch": r.get("default_branch", "main"),
                "updated_at": r.get("updated_at"),
                "stargazers_count": r.get("stargazers_count", 0),
            }
            for r in repos
        ]


async def get_repo_tree(
    token: Optional[str],
    owner: str,
    repo: str,
    branch: str = "main",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Get the full file tree of a repository (recursive)."""
    owner, repo = normalize_repo_identity(owner, repo)
    requested_branch = (branch or "main").strip() or "main"

    headers = _build_github_headers(
        "application/vnd.github+json",
        token=token,
        username=username,
        password=password,
    )

    async with httpx.AsyncClient() as client:
        tree_resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{requested_branch}",
            params={"recursive": "1"},
            headers=headers,
        )
        resolved_branch = requested_branch

        # If branch lookup fails (often default branch isn't "main"), retry with repo default branch.
        if tree_resp.status_code == 404:
            meta_resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
                headers=headers,
            )
            if meta_resp.status_code == 200:
                default_branch = (meta_resp.json() or {}).get("default_branch")
                if default_branch and default_branch != requested_branch:
                    fallback_resp = await client.get(
                        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{default_branch}",
                        params={"recursive": "1"},
                        headers=headers,
                    )
                    if fallback_resp.status_code == 200:
                        tree_resp = fallback_resp
                        resolved_branch = default_branch

        tree_resp.raise_for_status()
        tree = tree_resp.json().get("tree", [])
        normalized_tree = [
            {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
            for item in tree
        ]
        return normalized_tree, resolved_branch


async def get_file_content(
    token: Optional[str],
    owner: str,
    repo: str,
    path: str,
    branch: str = "main",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Optional[str]:
    """Fetch raw content of a single file from GitHub."""
    owner, repo = normalize_repo_identity(owner, repo)
    headers = _build_github_headers(
        "application/vnd.github.raw+json",
        token=token,
        username=username,
        password=password,
    )
        
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
            headers=headers,
        )
        if resp.status_code != 200:
            return None
        return resp.text


def _should_include_file(path: str, size: int) -> bool:
    """Decide whether a file is relevant source code we should fetch."""
    import os
    basename = os.path.basename(path)
    if basename in SKIP_FILES:
        return False
    # Skip hidden directories / files (except .env.example)
    parts = path.split("/")
    if any(p.startswith(".") and p not in {".env.example", ".github"} for p in parts):
        return False
    # Skip common non-essential dirs
    skip_dirs = {"node_modules", "vendor", "dist", "build", "__pycache__", ".git", "venv", ".venv"}
    if any(p in skip_dirs for p in parts):
        return False
    if size > MAX_FILE_SIZE_BYTES:
        return False
    _, ext = os.path.splitext(basename)
    return ext.lower() in CODE_EXTENSIONS


async def build_repo_context(
    token: Optional[str],
    owner: str,
    repo: str,
    branch: str = "main",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, str]:
    """
    Build a text summary of the repository to feed into the AI model.
    Returns a structured string with:
      - Repo metadata
      - File tree
      - Key file contents (capped)
    """
    owner, repo = normalize_repo_identity(owner, repo)

    # 1. File tree
    tree, resolved_branch = await get_repo_tree(
        token,
        owner,
        repo,
        branch,
        username=username,
        password=password,
    )

    # 2. Build tree listing
    tree_lines = [f"  {item['path']}" for item in tree if item["type"] == "blob"]
    tree_text = "\n".join(tree_lines[:200])  # cap listing

    # 3. Identify files to fetch
    files_to_fetch = [
        item for item in tree
        if item["type"] == "blob" and _should_include_file(item["path"], item.get("size", 0))
    ]

    # Prioritise important files
    priority_names = {
        "README.md", "readme.md", "README", "package.json", "requirements.txt",
        "Pipfile", "pyproject.toml", "Dockerfile", "docker-compose.yml",
        "docker-compose.yaml", ".env.example", "Makefile", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle",
    }
    files_to_fetch.sort(
        key=lambda f: (0 if f["path"].split("/")[-1] in priority_names else 1, f["path"])
    )
    files_to_fetch = files_to_fetch[:MAX_FILES_TO_FETCH]

    # 4. Fetch contents
    file_contents = []
    for f in files_to_fetch:
        content = await get_file_content(
            token,
            owner,
            repo,
            f["path"],
            resolved_branch,
            username=username,
            password=password,
        )
        if content:
            file_contents.append(f"--- FILE: {f['path']} ---\n{content}\n")

    contents_text = "\n".join(file_contents)

    # 5. Assemble context
    context = (
        f"GITHUB REPOSITORY CONTEXT\n"
        f"========================\n"
        f"Repository: {owner}/{repo} (branch: {resolved_branch})\n\n"
        f"FILE TREE:\n{tree_text}\n\n"
        f"KEY SOURCE FILES ({len(file_contents)} files):\n"
        f"{contents_text}\n"
    )
    return {
        "context": context,
        "owner": owner,
        "repo": repo,
        "branch": resolved_branch,
    }


async def is_repo_public(
    owner: str,
    repo: str,
    branch: str = "main",
) -> bool:
    """Check if a GitHub repository is accessible without authentication (public)."""
    owner, repo = normalize_repo_identity(owner, repo)
    headers = _build_github_headers("application/vnd.github+json", token=None)
    
    async with httpx.AsyncClient() as client:
        # Try to access the repo metadata without auth
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
            headers=headers,
        )
        # If we get 200, it's public. 404 or 401/403 means private or doesn't exist.
        return resp.status_code == 200


async def build_repo_context_from_zip(
    owner: str,
    repo: str,
    branch: str = "main",
) -> Dict[str, str]:
    """Build repo context by downloading public zip archive (no auth required)."""
    owner, repo = normalize_repo_identity(owner, repo)
    
    # First try to get the default branch if not provided
    branch_to_use = branch or "main"
    try:
        default_branch = await _get_default_branch_from_repo_page(owner, repo)
        if default_branch:
            branch_to_use = default_branch
    except Exception:
        pass  # Use provided branch as fallback
    
    try:
        zip_content = await _download_repo_zip(owner, repo, branch_to_use)
        return _build_repo_context_from_zip_bytes(zip_content, owner, repo, branch_to_use)
    except Exception as e:
        raise ValueError(f"Failed to fetch public repository: {e}")


async def _get_default_branch_from_repo_page(owner: str, repo: str) -> Optional[str]:
    """Fetch default branch from public GitHub repository page HTML."""
    owner, repo = normalize_repo_identity(owner, repo)
    page_url = f"https://github.com/{owner}/{repo}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(page_url)
        if resp.status_code != 200:
            return None
        html = resp.text or ""

    match = re.search(r'"defaultBranch":"([^"]+)"', html)
    if not match:
        return None

    branch = match.group(1)
    branch = branch.replace("\\u002F", "/").replace("\\/", "/").strip()
    return branch or None


def _build_repo_context_from_zip_bytes(
    zip_bytes: bytes,
    owner: str,
    repo: str,
    branch: str,
) -> Dict[str, str]:
    """Create the same context payload as API mode using an archive payload."""
    owner, repo = normalize_repo_identity(owner, repo)

    tree: List[Dict[str, Any]] = []
    rel_to_archive: Dict[str, str] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise ValueError("Repository archive is empty.")

        # GitHub zips include a root folder like "<repo>-<branch>/".
        root_prefix = names[0].split("/", 1)[0] + "/"

        for archive_name in names:
            rel_path = archive_name[len(root_prefix):] if archive_name.startswith(root_prefix) else archive_name
            rel_path = rel_path.strip("/")
            if not rel_path:
                continue
            info = archive.getinfo(archive_name)
            tree.append({"path": rel_path, "type": "blob", "size": info.file_size})
            rel_to_archive[rel_path] = archive_name

        tree_lines = [f"  {item['path']}" for item in tree]
        tree_text = "\n".join(tree_lines[:200])

        files_to_fetch = [
            item for item in tree
            if _should_include_file(item["path"], item.get("size", 0))
        ]

        priority_names = {
            "README.md", "readme.md", "README", "package.json", "requirements.txt",
            "Pipfile", "pyproject.toml", "Dockerfile", "docker-compose.yml",
            "docker-compose.yaml", ".env.example", "Makefile", "Cargo.toml",
            "go.mod", "pom.xml", "build.gradle",
        }
        files_to_fetch.sort(
            key=lambda f: (0 if posixpath.basename(f["path"]) in priority_names else 1, f["path"])
        )
        files_to_fetch = files_to_fetch[:MAX_FILES_TO_FETCH]

        file_contents: List[str] = []
        for item in files_to_fetch:
            archive_name = rel_to_archive.get(item["path"])
            if not archive_name:
                continue
            try:
                raw = archive.read(archive_name)
            except KeyError:
                continue
            text = raw.decode("utf-8", errors="ignore")
            if text.strip():
                file_contents.append(f"--- FILE: {item['path']} ---\n{text}\n")

    contents_text = "\n".join(file_contents)
    context = (
        f"GITHUB REPOSITORY CONTEXT\n"
        f"========================\n"
        f"Repository: {owner}/{repo} (branch: {branch})\n\n"
        f"FILE TREE:\n{tree_text}\n\n"
        f"KEY SOURCE FILES ({len(file_contents)} files):\n"
        f"{contents_text}\n"
    )
    return {
        "context": context,
        "owner": owner,
        "repo": repo,
        "branch": branch,
    }


async def build_repo_context_from_zip(
    owner: str,
    repo: str,
    branch: str = "main",
) -> Dict[str, str]:
    """
    Build repository context without using GitHub API.
    Useful fallback when API tokens are invalid or rate-limited.
    """
    owner, repo = normalize_repo_identity(owner, repo)
    requested = (branch or "main").strip() or "main"

    candidates: List[str] = []
    for candidate in [requested, "main", "master"]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # For public repos, HTML page is often still accessible even when API is rate-limited.
    try:
        html_default_branch = await _get_default_branch_from_repo_page(owner, repo)
        if html_default_branch and html_default_branch not in candidates:
            candidates.insert(1, html_default_branch)
    except Exception:
        pass

    last_error: Optional[Exception] = None
    for candidate_branch in candidates:
        try:
            archive_bytes = await _download_repo_zip(owner, repo, candidate_branch)
            return _build_repo_context_from_zip_bytes(
                archive_bytes,
                owner,
                repo,
                candidate_branch,
            )
        except httpx.HTTPStatusError as e:
            last_error = e
            # Try next branch for "not found" only.
            if e.response is not None and e.response.status_code == 404:
                continue
            raise

    if last_error:
        raise last_error
    raise ValueError("Unable to build repository context from zip archive.")
