"""
GitHub Integration Service for BRD Analysis
Handles OAuth flow & fetching repository data for AI context.
"""
import httpx
from typing import Optional, Dict, Any, List
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
    token: str, owner: str, repo: str, branch: str = "main"
) -> List[Dict[str, Any]]:
    """Get the full file tree of a repository (recursive)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        return [
            {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
            for item in tree
        ]


async def get_file_content(
    token: str, owner: str, repo: str, path: str, branch: str = "main"
) -> Optional[str]:
    """Fetch raw content of a single file from GitHub."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.raw+json",
            },
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
    token: str, owner: str, repo: str, branch: str = "main"
) -> str:
    """
    Build a text summary of the repository to feed into the AI model.
    Returns a structured string with:
      - Repo metadata
      - File tree
      - Key file contents (capped)
    """
    # 1. File tree
    tree = await get_repo_tree(token, owner, repo, branch)

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
        content = await get_file_content(token, owner, repo, f["path"], branch)
        if content:
            file_contents.append(f"--- FILE: {f['path']} ---\n{content}\n")

    contents_text = "\n".join(file_contents)

    # 5. Assemble context
    context = (
        f"GITHUB REPOSITORY CONTEXT\n"
        f"========================\n"
        f"Repository: {owner}/{repo} (branch: {branch})\n\n"
        f"FILE TREE:\n{tree_text}\n\n"
        f"KEY SOURCE FILES ({len(file_contents)} files):\n"
        f"{contents_text}\n"
    )
    return context
