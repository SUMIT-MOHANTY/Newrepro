"""
Context Manager — Four-Layer Just-in-Time Context Injection
Provides agents with precisely targeted context from the knowledge graph
and RAG system, structured in four layers:

Layer 1 — Global Context: Repo-wide summary (tech stack, conventions)
Layer 2 — Project Rules: BRD analysis, governance constraints, domain rules
Layer 3 — On-Demand Snippets: LightRAG hybrid retrieval per specific task
Layer 4 — Cross-Agent Awareness: Live shared memory of what other agents
           are doing, just did, and which files they touched
"""

import logging
import os
import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field

import rag_service
import knowledge_graph_service as kg_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  In-memory stores for project context layers
# ---------------------------------------------------------------------------

# project_token -> { graph, repo_path, global_context, project_rules }
_project_contexts: Dict[str, Dict[str, Any]] = {}

_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb",
    ".php", ".cs", ".swift", ".vue", ".svelte", ".css", ".scss", ".sass",
}
_FRONTEND_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".html",
}
_COMMON_SAFE_TOP_LEVEL_DIRS = {
    ".github", ".vscode", ".idea", "docs", "doc", "scripts", "tests", "test",
    "migrations", "alembic", "infra", "ops", "deploy", "k8s", "config", "configs",
    "public", "static", "assets", "examples", "fixtures",
}
_COMMON_MODULE_SAFE_DIRS = {
    "tests", "test", "docs", "scripts", "migrations", "alembic", "public", "static", "assets",
}
_MANIFEST_BASENAMES = {
    "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml", "yarn.lock", "package-lock.json",
    "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
    "webpack.config.js", "tsconfig.json", "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", "angular.json", "nx.json", "turbo.json",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "manage.py", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts", "composer.json",
}


def _normalize_contract_path(path: str) -> str:
    candidate = str(path or "").strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    candidate = candidate.strip("/")
    return candidate or "."


def _path_is_under(path: str, prefix: str) -> bool:
    norm_path = _normalize_contract_path(path)
    norm_prefix = _normalize_contract_path(prefix)
    if norm_prefix == ".":
        return True
    return norm_path == norm_prefix or norm_path.startswith(norm_prefix + "/")


def _relative_to_root(path: str, root: str) -> str:
    norm_path = _normalize_contract_path(path)
    norm_root = _normalize_contract_path(root)
    if norm_root == ".":
        return norm_path
    if norm_path == norm_root:
        return "."
    return norm_path[len(norm_root) + 1:]


def _join_contract_root(root: str, rel: str) -> str:
    norm_root = _normalize_contract_path(root)
    norm_rel = _normalize_contract_path(rel)
    if norm_rel == ".":
        return norm_root
    if norm_root == ".":
        return norm_rel
    return f"{norm_root}/{norm_rel}"


def _path_matches_pattern(path: str, pattern: str) -> bool:
    import fnmatch

    norm_path = _normalize_contract_path(path)
    norm_pattern = _normalize_contract_path(pattern)
    if fnmatch.fnmatch(norm_path, norm_pattern):
        return True
    if norm_pattern.startswith("**/"):
        return fnmatch.fnmatch(norm_path, norm_pattern[3:])
    return False


def _is_config_like_path(path: str) -> bool:
    base = os.path.basename(_normalize_contract_path(path))
    if base in _MANIFEST_BASENAMES:
        return True
    prefixes = (
        ".eslintrc", ".prettierrc", "vite.config", "webpack.config", "next.config",
        "nuxt.config", "tailwind.config", "postcss.config", "babel.config", "jest.config",
        "tsconfig", "jsconfig", "eslint.config", "docker-compose", "Dockerfile",
        "README", "LICENSE", ".gitignore", ".dockerignore", ".env",
    )
    return any(base.startswith(prefix) for prefix in prefixes)


def _is_source_like_path(path: str) -> bool:
    norm = _normalize_contract_path(path)
    if norm == ".":
        return False
    if _is_config_like_path(norm):
        return False
    _, ext = os.path.splitext(norm)
    return ext.lower() in _SOURCE_EXTENSIONS


def _is_frontend_like_path(path: str) -> bool:
    norm = _normalize_contract_path(path)
    if norm == ".":
        return False
    base = os.path.basename(norm)
    if base in {
        "package.json", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
        "webpack.config.js", "tsconfig.json", "eslint.config.js",
    }:
        return True
    _, ext = os.path.splitext(norm)
    return ext.lower() in _FRONTEND_EXTENSIONS


def _collect_repo_file_paths(repo_path: Optional[str]) -> List[str]:
    if not repo_path or not os.path.isdir(repo_path):
        return []

    ignored_dirs = {
        ".git", "node_modules", "dist", "build", ".next", ".turbo",
        "__pycache__", ".venv", "venv", ".pytest_cache",
    }
    paths: List[str] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for name in filenames:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, repo_path)
            paths.append(_normalize_contract_path(rel_path))
    return sorted(set(paths))


def _collect_graph_file_paths(graph: Optional[kg_service.CodeKnowledgeGraph]) -> List[str]:
    if not graph:
        return []
    paths = []
    for node in getattr(graph, "nodes", {}).values():
        if getattr(node, "node_type", None) != "file":
            continue
        file_path = _normalize_contract_path(getattr(node, "file_path", "") or "")
        if file_path and file_path != ".":
            paths.append(file_path)
    return sorted(set(paths))


def _discover_module_roots(file_paths: List[str]) -> List[str]:
    roots = set()
    for file_path in file_paths:
        norm = _normalize_contract_path(file_path)
        base = os.path.basename(norm)
        if base not in _MANIFEST_BASENAMES and not base.endswith((".csproj", ".sln")):
            continue
        dirname = os.path.dirname(norm).replace("\\", "/").strip("/")
        roots.add(dirname or ".")

    if not roots:
        for file_path in file_paths:
            norm = _normalize_contract_path(file_path)
            if not _is_source_like_path(norm):
                continue
            parts = norm.split("/")
            if len(parts) > 1:
                roots.add(parts[0])
            else:
                roots.add(".")

    return sorted(roots, key=lambda item: (item != ".", item))


def _infer_module_kind(module_root: str, file_paths: List[str]) -> str:
    manifests = {
        os.path.basename(path)
        for path in file_paths
        if _path_is_under(path, module_root) and _is_config_like_path(path)
    }
    if manifests & {
        "package.json", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
        "webpack.config.js", "tsconfig.json", "angular.json", "nx.json", "turbo.json",
    }:
        return "frontend"
    if manifests & {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "manage.py"}:
        return "backend"
    if manifests & {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
        return "java"
    if manifests & {"go.mod"}:
        return "go"
    if manifests & {"Cargo.toml"}:
        return "rust"

    frontend_count = 0
    backend_count = 0
    for path in file_paths:
        if not _path_is_under(path, module_root):
            continue
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext in _FRONTEND_EXTENSIONS:
            frontend_count += 1
        elif ext == ".py":
            backend_count += 1
    if frontend_count and frontend_count >= backend_count:
        return "frontend"
    if backend_count:
        return "backend"
    return "generic"


def _derive_source_roots_for_module(module_root: str, module_kind: str, file_paths: List[str]) -> List[str]:
    candidates = set()
    for path in file_paths:
        if not _path_is_under(path, module_root) or not _is_source_like_path(path):
            continue

        rel_path = _relative_to_root(path, module_root)
        parts = [p for p in rel_path.split("/") if p and p != "."]
        if not parts:
            candidates.add(_normalize_contract_path(module_root))
            continue

        if module_kind == "frontend":
            markers = ("src", "app")
        elif module_kind == "backend":
            markers = ("src", "app", "server", "api", "backend")
        else:
            markers = ("src", "app", "lib", "cmd", "internal", "pkg")

        chosen = "."
        for marker in markers:
            if marker in parts:
                idx = parts.index(marker)
                chosen = "/".join(parts[:idx + 1])
                break

        if chosen == "." and len(parts) > 1 and parts[0] in {
            "components", "pages", "hooks", "utils", "styles", "context",
            "routes", "models", "schemas", "controllers", "services",
        }:
            chosen = "."
        elif chosen == "." and len(parts) > 1:
            chosen = parts[0]

        candidates.add(_join_contract_root(module_root, chosen))

    if not candidates:
        candidates.add(_normalize_contract_path(module_root))

    return sorted(candidates)


def _build_workspace_contract_from_file_paths(
    project_token: str,
    file_paths: List[str],
    source: str = "detected",
) -> Dict[str, Any]:
    normalized_paths = sorted({
        _normalize_contract_path(path)
        for path in (file_paths or [])
        if _normalize_contract_path(path) != "."
    })

    top_level_dirs = set()
    root_files = set()
    for path in normalized_paths:
        parts = path.split("/")
        if len(parts) == 1:
            root_files.add(parts[0])
        elif parts[0]:
            top_level_dirs.add(parts[0])

    module_roots = _discover_module_roots(normalized_paths)
    modules = []
    allowed_source_roots = set()
    for root in module_roots:
        kind = _infer_module_kind(root, normalized_paths)
        source_roots = _derive_source_roots_for_module(root, kind, normalized_paths)
        manifests = [
            path for path in normalized_paths
            if _path_is_under(path, root) and _is_config_like_path(path)
        ][:15]
        modules.append({
            "root": root,
            "kind": kind,
            "source_roots": source_roots,
            "manifests": manifests,
        })
        allowed_source_roots.update(source_roots)

    canonical_frontend_roots = sorted({
        source_root
        for module in modules if module["kind"] == "frontend"
        for source_root in module["source_roots"]
    })
    canonical_backend_roots = sorted({
        source_root
        for module in modules if module["kind"] == "backend"
        for source_root in module["source_roots"]
    })

    has_source_or_modules = bool(modules) or any(_is_source_like_path(path) for path in normalized_paths)
    status = "ready" if has_source_or_modules else "insufficient"
    return {
        "project_token": project_token,
        "status": status,
        "source": source,
        "detected_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "modules": modules,
        "allowed_top_level_dirs": sorted(top_level_dirs),
        "root_files": sorted(root_files),
        "allowed_source_roots": sorted(allowed_source_roots),
        "canonical_frontend_roots": canonical_frontend_roots,
        "canonical_backend_roots": canonical_backend_roots,
    }


def get_workspace_contract(project_token: str, refresh: bool = False) -> Dict[str, Any]:
    token = (project_token or "").strip()
    project_ctx = _project_contexts.setdefault(token, {})
    cached = project_ctx.get("workspace_contract")
    if cached and not refresh:
        return cached

    file_paths: List[str] = []
    repo_path = project_ctx.get("repo_path")
    if repo_path:
        file_paths = _collect_repo_file_paths(repo_path)
    if not file_paths:
        file_paths = _collect_graph_file_paths(project_ctx.get("graph"))

    contract = _build_workspace_contract_from_file_paths(
        token,
        file_paths,
        source="repo_index" if file_paths else "insufficient",
    )
    project_ctx["workspace_contract"] = contract
    return contract


def update_workspace_contract_from_workspace_tree(project_token: str, workspace_tree: str) -> Dict[str, Any]:
    token = (project_token or "").strip()
    project_ctx = _project_contexts.setdefault(token, {})
    existing = project_ctx.get("workspace_contract") or {}
    if existing.get("status") == "ready":
        return existing

    file_paths = sorted(_parse_workspace_to_file_dict(workspace_tree).keys())
    contract = _build_workspace_contract_from_file_paths(
        token,
        file_paths,
        source="workspace_tree",
    )
    project_ctx["workspace_contract"] = contract
    return contract


def _extract_file_paths_from_canonical_tree(tree_text: str) -> List[str]:
    paths: List[str] = []
    stack: List[str] = []

    for raw_line in str(tree_text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip().strip("`")
        if stripped.lower() in {"text", "project/"}:
            continue

        content = line
        while content.startswith(("│", " ", "\t")):
            content = content[1:]
        if content.startswith(("├──", "└──")):
            content = content[3:].lstrip("─ ").strip()
        else:
            content = stripped

        if not content or content.startswith("#"):
            continue

        if " # " in content:
            content = content.split(" # ", 1)[0].rstrip()
        elif "  #" in content:
            content = content.split("  #", 1)[0].rstrip()

        if not content:
            continue

        indent_prefix = raw_line.split(content, 1)[0]
        depth = indent_prefix.count("│") + (indent_prefix.count("    ") if "    " in indent_prefix else 0)
        while len(stack) > depth:
            stack.pop()

        name = content.rstrip("/")
        if not name:
            continue

        if "." not in name and "/" not in name and name.lower() not in {
            "backend", "frontend", "shared", "infra", "src", "app", "api", "services",
            "components", "hooks", "pages", "styles", "tests", "public", "scripts",
            "workflows", "migrations", "models", "schemas", "repositories", "core",
            "db", "tasks", "store", "types", "lib", "utils", "constants", ".github",
        } and not raw_line.strip().endswith("/"):
            continue

        current_path = "/".join(stack + [name]) if stack else name

        if raw_line.strip().endswith("/"):
            stack.append(name)
            continue

        if "/" in name and raw_line.strip() == content:
            current_path = name
        paths.append(current_path)

    return sorted({path for path in paths if path and not path.endswith("/")})


def update_workspace_contract_from_canonical_tree(project_token: str, workspace_tree: str) -> Dict[str, Any]:
    token = (project_token or "").strip()
    project_ctx = _project_contexts.setdefault(token, {})
    existing = project_ctx.get("workspace_contract") or {}
    if existing.get("status") == "ready":
        return existing

    file_paths = _extract_file_paths_from_canonical_tree(workspace_tree)
    contract = _build_workspace_contract_from_file_paths(
        token,
        file_paths,
        source="master_tree",
    )
    project_ctx["workspace_contract"] = contract
    return contract


def build_workspace_contract_context(project_token: str) -> str:
    contract = get_workspace_contract(project_token)
    if contract.get("status") != "ready":
        return (
            "=== WORKSPACE CONTRACT ===\n"
            "Contract status: bootstrap mode.\n"
            "Do not create new top-level application roots unless the repo already contains them.\n"
            "Prefer extending the current integration branch structure instead of introducing alternate layouts.\n"
            "=== END WORKSPACE CONTRACT ==="
        )

    lines = ["=== WORKSPACE CONTRACT ==="]
    lines.append(
        "Existing top-level directories: "
        + ", ".join(contract.get("allowed_top_level_dirs") or ["(none)"])
    )

    modules = contract.get("modules") or []
    if modules:
        lines.append("Allowed module/source roots:")
        for module in modules[:8]:
            root = module.get("root") or "."
            kind = module.get("kind") or "generic"
            source_roots = module.get("source_roots") or [root]
            lines.append(
                f"  - {root} [{kind}] -> {', '.join(source_roots[:6])}"
            )

    lines.append(
        "Rules: do not create new top-level code roots or parallel source trees outside these paths."
    )
    lines.append("If a matching file already exists in an allowed source root, extend it instead of recreating it elsewhere.")
    lines.append("=== END WORKSPACE CONTRACT ===")
    return "\n".join(lines)


def validate_paths_against_workspace_contract(
    project_token: str,
    file_paths: List[str],
    task_domain: Optional[str] = None,
) -> Dict[str, Any]:
    contract = get_workspace_contract(project_token)
    normalized_paths = [
        _remap_path_to_workspace_contract(path, contract, task_domain=task_domain)
        for path in (file_paths or [])
        if _normalize_contract_path(path) not in {"", "."}
    ]
    if contract.get("status") != "ready" or not normalized_paths:
        return {"allowed": True, "violations": [], "contract_ready": contract.get("status") == "ready"}

    allowed_top_level_dirs = set(contract.get("allowed_top_level_dirs") or [])
    modules = contract.get("modules") or []
    violations = []

    for path in normalized_paths:
        parts = path.split("/")
        top_level = parts[0]
        if len(parts) > 1 and top_level not in allowed_top_level_dirs and top_level not in _COMMON_SAFE_TOP_LEVEL_DIRS:
            violations.append(
                f"{path}: creates new top-level directory '{top_level}' outside the workspace contract"
            )
            continue

        if _is_config_like_path(path):
            continue

        if not _is_source_like_path(path):
            continue

        matching_modules = [m for m in modules if _path_is_under(path, m.get("root") or ".")]
        if not matching_modules:
            if len(parts) > 1 and top_level in _COMMON_SAFE_TOP_LEVEL_DIRS:
                continue
            if len(parts) > 1 and top_level not in allowed_top_level_dirs:
                violations.append(f"{path}: not under any known module root")
            continue

        module = max(matching_modules, key=lambda item: len(_normalize_contract_path(item.get("root") or ".")))
        rel_path = _relative_to_root(path, module.get("root") or ".")
        rel_first = rel_path.split("/")[0] if rel_path and rel_path != "." else "."
        if rel_first in _COMMON_MODULE_SAFE_DIRS:
            continue

        source_roots = module.get("source_roots") or [module.get("root") or "."]
        if any(_path_is_under(path, source_root) for source_root in source_roots):
            continue

        module_kind = module.get("kind") or "generic"
        if task_domain == "frontend" or (task_domain is None and _is_frontend_like_path(path)):
            violations.append(
                f"{path}: frontend-like file is outside allowed source roots for module "
                f"'{module.get('root') or '.'}' ({', '.join(source_roots[:6])})"
            )
            continue

        violations.append(
            f"{path}: outside allowed source roots for module "
            f"'{module.get('root') or '.'}' ({', '.join(source_roots[:6])})"
        )

    return {
        "allowed": len(violations) == 0,
        "violations": violations[:20],
        "contract_ready": True,
        "contract": contract,
    }


def _remap_path_to_workspace_contract(
    path: str,
    contract: Dict[str, Any],
    task_domain: Optional[str] = None,
) -> str:
    normalized = _normalize_contract_path(path)
    parts = normalized.split("/")
    if len(parts) <= 1:
        return normalized

    top_level = parts[0]
    if top_level in set(contract.get("allowed_top_level_dirs") or []):
        return normalized
    if top_level in _COMMON_SAFE_TOP_LEVEL_DIRS:
        return normalized

    modules = contract.get("modules") or []
    preferred_kinds = {task_domain} if task_domain in {"backend", "frontend"} else set()
    preferred_roots: Set[str] = set()
    candidate_roots: Set[str] = set()
    backend_candidate_roots: Set[str] = set()
    frontend_candidate_roots: Set[str] = set()
    next_segment = parts[1].lower() if len(parts) > 1 else ""

    for module in modules:
        if not isinstance(module, dict):
            continue
        kind = str(module.get("kind") or "").strip().lower()
        source_roots = module.get("source_roots") or [module.get("root") or "."]
        for source_root in source_roots:
            normalized_root = _normalize_contract_path(str(source_root or ""))
            if normalized_root == ".":
                continue
            if os.path.basename(normalized_root) != top_level:
                continue
            candidate_roots.add(normalized_root)
            if preferred_kinds and kind in preferred_kinds:
                preferred_roots.add(normalized_root)
            if kind == "backend":
                backend_candidate_roots.add(normalized_root)
            elif kind == "frontend":
                frontend_candidate_roots.add(normalized_root)

    selected_root = ""
    if len(preferred_roots) == 1:
        selected_root = next(iter(preferred_roots))
    elif next_segment in {"components", "pages", "hooks", "styles", "contexts", "context", "providers", "layouts", "assets"} and len(frontend_candidate_roots) == 1:
        selected_root = next(iter(frontend_candidate_roots))
    elif next_segment in {"routes", "controllers", "services", "models", "schemas", "middleware", "repositories", "db"} and len(backend_candidate_roots) == 1:
        selected_root = next(iter(backend_candidate_roots))
    elif len(candidate_roots) == 1:
        selected_root = next(iter(candidate_roots))

    if not selected_root:
        return normalized

    suffix = "/".join(parts[1:]) if len(parts) > 1 else "."
    return _join_contract_root(selected_root, suffix or ".")


def normalize_paths_for_workspace_contract(
    project_token: str,
    file_paths: List[str],
    task_domain: Optional[str] = None,
) -> List[str]:
    contract = get_workspace_contract(project_token)
    if contract.get("status") != "ready":
        return [
            _normalize_contract_path(path)
            for path in (file_paths or [])
            if _normalize_contract_path(path) not in {"", "."}
        ]

    normalized_paths: List[str] = []
    seen = set()
    for raw_path in file_paths or []:
        candidate = _remap_path_to_workspace_contract(
            raw_path,
            contract,
            task_domain=task_domain,
        )
        if candidate in {"", "."} or candidate in seen:
            continue
        seen.add(candidate)
        normalized_paths.append(candidate)
    return normalized_paths


# ---------------------------------------------------------------------------
#  Layer 4 — Cross-Agent Shared Memory
# ---------------------------------------------------------------------------

@dataclass
class AgentTaskRecord:
    """
    A snapshot of what one agent is doing or just finished.
    Lives in shared memory so other agents can see it.
    """
    agent_id: str
    task_title: str
    task_description: str
    status: str  # "in_progress", "completed", "failed"
    task_id: Optional[str] = None
    task_phase: Optional[str] = None
    task_domain: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    files_touched: List[str] = field(default_factory=list)
    symbols_created: List[str] = field(default_factory=list)
    symbols_modified: List[str] = field(default_factory=list)
    branch_name: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    exit_code: Optional[int] = None
    summary: str = ""


class ProjectLiveMemory:
    """
    Shared memory for all agents working on the same project.
    Thread-safe via a simple lock since agents run as async tasks
    in the same process.
    """

    def __init__(self, project_token: Optional[str] = None):
        self._lock = threading.Lock()
        self._project_token = str(project_token or "").strip()
        # agent_id -> AgentTaskRecord (current or most recent task)
        self.active_tasks: Dict[str, AgentTaskRecord] = {}
        # Ordered history of completed records (newest first, capped)
        self.completed_history: List[AgentTaskRecord] = []
        # file_path -> set of agent_ids currently editing it
        self.file_locks: Dict[str, Set[str]] = {}
        self._max_history = 50
        # task_id -> Set[task_id] (dependencies)
        self._task_dependencies: Dict[str, Set[str]] = {}
        # Set of completed task IDs
        self._completed_task_ids: Set[str] = set()
        # Current active phase
        self._current_phase: Optional[str] = None
        # Integration validation status
        self._integration_blocked: bool = False
        # File ownership tracking: file_path -> agent_id (primary owner)
        self._file_ownership: Dict[str, str] = {}
        # Shared files that require coordination
        self._shared_files: Set[str] = set()
        # Domain roots inferred from workspace contract
        self._contract_backend_roots: Set[str] = set()
        self._contract_frontend_roots: Set[str] = set()
        self._contract_partition_signature: str = ""
        # Initialize file partitioning rules
        self._init_file_partitioning_rules()

    def _init_file_partitioning_rules(self):
        """Define clear ownership rules for files based on domain."""
        # Backend-owned files (exclusive)
        self._backend_files = {
            # Python backend files
            "**/app.py", "**/models.py", "**/database.py", "**/config.py",
            "**/schemas.py", "**/auth.py", "**/api/**/*.py",
            "**/backend/**/*.py", "**/routes/**/*.py", "**/services/**/*.py",
            # Backend config
            "**/requirements.txt", "**/Pipfile", "**/pyproject.toml",
            "**/.env*", "**/docker-compose*.yml", "**/Dockerfile",
            # Database & migration
            "**/migrations/**", "**/alembic/**", "**/*.sql",
        }

        # Frontend-owned files (exclusive)
        self._frontend_files = {
            # React/Vue/Angular files
            "**/frontend/src/**", "**/client/src/**", "src/**",
            "**/public/**", "**/static/**",
            # Frontend config
            "**/package.json", "**/yarn.lock", "**/pnpm-lock.yaml",
            "**/tsconfig*.json", "**/vite.config.*", "**/webpack.config.*",
            "**/.eslintrc*", "**/.prettierrc*",
        }

        # Shared files (require coordination)
        self._shared_files = {
            "**/README.md", "**/CONTRIBUTING.md", "**/LICENSE",
            "**/.gitignore", "**/.dockerignore",
            "**/docker-compose*.yml",  # Both backend and frontend might need to edit
            "**/.env.example",  # Both backend and frontend env vars
        }

    def _refresh_contract_domain_roots(self) -> None:
        token = self._project_token
        if not token:
            return
        try:
            contract = get_workspace_contract(token)
        except Exception:
            return
        if not isinstance(contract, dict):
            return

        backend_roots: Set[str] = set()
        frontend_roots: Set[str] = set()

        for root in (contract.get("canonical_backend_roots") or []):
            normalized = _normalize_contract_path(str(root or ""))
            if normalized != ".":
                backend_roots.add(normalized)
        for root in (contract.get("canonical_frontend_roots") or []):
            normalized = _normalize_contract_path(str(root or ""))
            if normalized != ".":
                frontend_roots.add(normalized)

        for module in (contract.get("modules") or []):
            if not isinstance(module, dict):
                continue
            kind = str(module.get("kind") or "").strip().lower()
            if kind not in {"backend", "frontend"}:
                continue
            roots = module.get("source_roots") or [module.get("root") or "."]
            for root in roots:
                normalized = _normalize_contract_path(str(root or ""))
                if normalized == ".":
                    continue
                if kind == "backend":
                    backend_roots.add(normalized)
                else:
                    frontend_roots.add(normalized)

        signature = json.dumps(
            {
                "status": contract.get("status"),
                "detected_at": contract.get("detected_at"),
                "source": contract.get("source"),
                "backend_roots": sorted(backend_roots),
                "frontend_roots": sorted(frontend_roots),
            },
            sort_keys=True,
        )
        if signature == self._contract_partition_signature:
            return

        with self._lock:
            self._contract_backend_roots = backend_roots
            self._contract_frontend_roots = frontend_roots
            self._contract_partition_signature = signature

    def is_shared_file(self, file_path: str) -> bool:
        normalized_path = _normalize_contract_path(file_path)
        for pattern in self._shared_files:
            if _path_matches_pattern(normalized_path, pattern):
                return True
        return False

    def _resolve_domain_owner_from_contract(self, file_path: str) -> Optional[str]:
        self._refresh_contract_domain_roots()
        normalized = _normalize_contract_path(file_path)
        if normalized == ".":
            return None

        backend_matches = [
            root for root in self._contract_backend_roots
            if _path_is_under(normalized, root)
        ]
        frontend_matches = [
            root for root in self._contract_frontend_roots
            if _path_is_under(normalized, root)
        ]

        if backend_matches and not frontend_matches:
            return "backend"
        if frontend_matches and not backend_matches:
            return "frontend"
        if backend_matches and frontend_matches:
            backend_depth = max(len(root) for root in backend_matches)
            frontend_depth = max(len(root) for root in frontend_matches)
            if backend_depth > frontend_depth:
                return "backend"
            if frontend_depth > backend_depth:
                return "frontend"
        return None

    def get_file_owner(self, file_path: str) -> Optional[str]:
        """Determine which domain should own a file based on its path."""
        normalized_path = _normalize_contract_path(file_path)
        contract_owner = self._resolve_domain_owner_from_contract(normalized_path)
        if contract_owner:
            return contract_owner

        # Check backend ownership
        for pattern in self._backend_files:
            if _path_matches_pattern(normalized_path, pattern):
                return "backend"

        # Check frontend ownership
        for pattern in self._frontend_files:
            if _path_matches_pattern(normalized_path, pattern):
                return "frontend"

        # Default to shared (requires coordination)
        return None

    def can_agent_edit_file(self, agent_domain: str, file_path: str) -> tuple[bool, str]:
        """
        Check if an agent can edit a file based on domain ownership.
        Returns (allowed, reason).
        """
        normalized_path = _normalize_contract_path(file_path)

        # Check if it's a shared file
        if self.is_shared_file(normalized_path):
            return True, "Shared file - coordination required"

        owner = self.get_file_owner(normalized_path)
        if owner == "backend":
            if agent_domain == "backend":
                return True, "Backend-owned file"
            return False, f"File '{normalized_path}' is owned by backend domain"
        if owner == "frontend":
            if agent_domain == "frontend":
                return True, "Frontend-owned file"
            return False, f"File '{normalized_path}' is owned by frontend domain"

        # Unknown file - allow but log warning
        return True, "Unknown file type - allowing edit"

    def infer_domain_for_files(self, file_paths: List[str]) -> Optional[str]:
        owners: Set[str] = set()
        for file_path in file_paths or []:
            owner = self.get_file_owner(file_path)
            if owner in {"backend", "frontend"}:
                owners.add(owner)
        if owners == {"backend"}:
            return "backend"
        if owners == {"frontend"}:
            return "frontend"
        if len(owners) > 1:
            return "integration"
        return None

    def register_task_start(
        self,
        agent_id: str,
        task_title: str,
        task_description: str,
        branch_name: Optional[str] = None,
        task_id: Optional[str] = None,
        task_phase: Optional[str] = None,
        task_domain: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
    ):
        """Called when an agent picks up a task."""
        with self._lock:
            record = AgentTaskRecord(
                agent_id=agent_id,
                task_title=task_title,
                task_description=task_description,
                status="in_progress",
                branch_name=branch_name,
                started_at=datetime.utcnow().isoformat(),
                task_id=task_id,
                task_phase=task_phase,
                task_domain=task_domain,
                dependencies=dependencies or [],
            )
            self.active_tasks[agent_id] = record

    def register_task_complete(
        self,
        agent_id: str,
        files_touched: Optional[List[str]] = None,
        symbols_created: Optional[List[str]] = None,
        symbols_modified: Optional[List[str]] = None,
        exit_code: int = 0,
        summary: str = "",
    ):
        """Called when an agent finishes a task."""
        with self._lock:
            record = self.active_tasks.get(agent_id)
            if not record:
                return

            record.status = "completed" if exit_code == 0 else "failed"
            record.completed_at = datetime.utcnow().isoformat()
            record.exit_code = exit_code
            record.summary = summary
            record.files_touched = files_touched or []
            record.symbols_created = symbols_created or []
            record.symbols_modified = symbols_modified or []

            # Release file locks held by this agent
            for fpath in list(self.file_locks.keys()):
                self.file_locks[fpath].discard(agent_id)
                if not self.file_locks[fpath]:
                    del self.file_locks[fpath]

            # Move to history
            self.completed_history.insert(0, record)
            if len(self.completed_history) > self._max_history:
                self.completed_history = self.completed_history[:self._max_history]
            del self.active_tasks[agent_id]

    def register_file_intent(self, agent_id: str, file_paths: List[str]):
        """Register that an agent intends to touch certain files."""
        normalized_paths = []
        seen = set()
        for file_path in file_paths or []:
            candidate = _normalize_contract_path(file_path)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized_paths.append(candidate)

        if not normalized_paths:
            return

        with self._lock:
            for fp in normalized_paths:
                if fp not in self.file_locks:
                    self.file_locks[fp] = set()
                self.file_locks[fp].add(agent_id)

            record = self.active_tasks.get(agent_id)
            if record:
                current = list(record.files_touched or [])
                for fp in normalized_paths:
                    if fp not in current:
                        current.append(fp)
                record.files_touched = current[:50]

    def release_file_intent(self, agent_id: str, file_paths: Optional[List[str]] = None):
        """Release file intent locks for a specific agent."""
        with self._lock:
            targets = [
                _normalize_contract_path(path)
                for path in (file_paths or self.file_locks.keys())
            ]
            for fp in list(targets):
                editors = self.file_locks.get(fp)
                if not editors:
                    continue
                editors.discard(agent_id)
                if not editors:
                    del self.file_locks[fp]

    def get_file_conflicts(self, agent_id: str, target_files: List[str]) -> Dict[str, List[str]]:
        """
        Check if any of the target files are being edited by other agents.
        Returns {file_path: [other_agent_ids]} for conflicts.
        """
        with self._lock:
            conflicts = {}
            for fp in target_files:
                normalized = _normalize_contract_path(fp)
                if self.is_shared_file(normalized):
                    continue
                others = self.file_locks.get(normalized, set()) - {agent_id}
                if others:
                    conflicts[normalized] = list(others)
            return conflicts

    def get_agent_domain(self, agent_id: str) -> Optional[str]:
        """Get the domain (backend/frontend) of an agent from their current or recent tasks."""
        with self._lock:
            # Check active tasks
            record = self.active_tasks.get(agent_id)
            if record and record.task_domain:
                return record.task_domain
            
            # Check history
            for record in self.completed_history:
                if record.agent_id == agent_id and record.task_domain:
                    return record.task_domain
            
            return None

    def validate_file_access(self, agent_id: str, file_paths: List[str]) -> tuple[bool, List[str]]:
        """
        Validate that an agent can edit the given files based on domain ownership.
        Returns (allowed, list_of_blocked_files_with_reasons).
        """
        agent_domain = self.get_agent_domain(agent_id)
        if not agent_domain:
            # If agent domain unknown, allow but warn
            return True, []
        
        blocked = []
        for file_path in file_paths:
            allowed, reason = self.can_agent_edit_file(agent_domain, file_path)
            if not allowed:
                blocked.append(f"{file_path}: {reason}")
        
        return len(blocked) == 0, blocked

    def build_cross_agent_context(self, requesting_agent_id: str) -> str:
        """
        Build a concise text summary of what all OTHER agents are doing
        or have recently done. This is injected into the requesting agent's
        prompt so it is aware of parallel work.
        """
        with self._lock:
            lines = ["=== CROSS-AGENT AWARENESS (Layer 4) ==="]
            has_content = False

            # Currently active agents
            active = [
                r for aid, r in self.active_tasks.items()
                if aid != requesting_agent_id
            ]
            if active:
                has_content = True
                lines.append("\n⚡ AGENTS CURRENTLY WORKING:")
                for r in active:
                    branch_info = f" on branch '{r.branch_name}'" if r.branch_name else ""
                    domain_info = f" [{r.task_domain}]" if r.task_domain else ""
                    lines.append(f"  • {r.agent_id}: \"{r.task_title}\"{domain_info}{branch_info}")
                    lines.append(f"    Description: {r.task_description[:200]}")
                    if r.files_touched:
                        lines.append(f"    Files they're editing: {', '.join(r.files_touched[:5])}")

            # File conflicts (files being edited by others RIGHT NOW)
            conflict_files = {}
            requesting_domain = self.get_agent_domain(requesting_agent_id)
            for fpath, agents in self.file_locks.items():
                others = agents - {requesting_agent_id}
                if others:
                    conflict_files[fpath] = list(others)
            if conflict_files:
                has_content = True
                lines.append("\n⚠️ FILES CURRENTLY BEING EDITED BY OTHER AGENTS:")
                for fpath, agents in conflict_files.items():
                    lines.append(f"  • {fpath} — being edited by {', '.join(agents)}")
                lines.append(
                    "  → If you need to modify these files, ONLY APPEND new code. "
                    "Do NOT overwrite or restructure existing code in these files."
                )
            
            # File ownership rules reminder
            if requesting_domain:
                has_content = True
                lines.append(f"\n📋 FILE OWNERSHIP RULES (Your domain: {requesting_domain}):")
                if requesting_domain == "backend":
                    lines.append("  • You OWN: backend/**/*.py, requirements.txt, Dockerfile, migrations/**")
                    lines.append("  • You CANNOT edit: frontend/src/**, package.json, frontend config files")
                    lines.append("  • SHARED files (README.md, .gitignore): coordinate with others")
                elif requesting_domain == "frontend":
                    lines.append("  • You OWN: frontend/src/**, package.json, frontend config files")
                    lines.append("  • You CANNOT edit: backend/**/*.py, requirements.txt, backend config files")
                    lines.append("  • SHARED files (README.md, .gitignore): coordinate with others")
                lines.append("  → Violating ownership rules will cause merge conflicts!")

            # Recently completed tasks (last 10)
            recent = self.completed_history[:10]
            if recent:
                has_content = True
                lines.append("\n✅ RECENTLY COMPLETED BY OTHER AGENTS:")
                for r in recent:
                    status_icon = "✓" if r.exit_code == 0 else "✗"
                    lines.append(
                        f"  {status_icon} {r.agent_id}: \"{r.task_title}\" "
                        f"(exit={r.exit_code})"
                    )
                    if r.files_touched:
                        lines.append(
                            f"    Files touched: {', '.join(r.files_touched[:10])}"
                        )
                    if r.symbols_created:
                        lines.append(
                            f"    New symbols: {', '.join(r.symbols_created[:10])}"
                        )
                    if r.summary:
                        lines.append(f"    Summary: {r.summary[:200]}")

            if not has_content:
                lines.append("  (No other agents have run yet in this project.)")

            lines.append("\n=== END CROSS-AGENT AWARENESS ===")
            return "\n".join(lines)

    def register_task_dependencies(self, task_id: str, dependencies: List[str]):
        """Register dependencies for a task."""
        with self._lock:
            self._task_dependencies[task_id] = set(str(d) for d in dependencies)

    def mark_task_completed(self, task_id: str):
        """Mark a task as completed."""
        with self._lock:
            self._completed_task_ids.add(str(task_id))

    def check_task_dependencies(self, task_id: str) -> bool:
        """Check if all dependencies for a task are completed."""
        with self._lock:
            deps = self._task_dependencies.get(str(task_id), set())
            if not deps:
                return True  # No dependencies, can proceed
            return deps.issubset(self._completed_task_ids)

    def get_blocking_tasks(self, task_id: str) -> List[str]:
        """Get list of task IDs that are blocking this task."""
        with self._lock:
            deps = self._task_dependencies.get(str(task_id), set())
            return list(deps - self._completed_task_ids)

    def set_current_phase(self, phase: Optional[str]):
        """Set the current active phase."""
        with self._lock:
            self._current_phase = phase

    def get_current_phase(self) -> Optional[str]:
        """Get the current active phase."""
        with self._lock:
            return self._current_phase

    def set_integration_blocked(self, blocked: bool):
        """Set integration blocked status (blocks new tasks if validation failed)."""
        with self._lock:
            self._integration_blocked = blocked

    def is_integration_blocked(self) -> bool:
        """Check if integration is blocked (validation failed)."""
        with self._lock:
            return self._integration_blocked


# project_token -> ProjectLiveMemory
_project_live_memories: Dict[str, ProjectLiveMemory] = {}


def get_live_memory(project_token: str) -> ProjectLiveMemory:
    """Get or create the shared live memory for a project."""
    if project_token not in _project_live_memories:
        _project_live_memories[project_token] = ProjectLiveMemory(project_token=project_token)
    return _project_live_memories[project_token]


def clear_project_runtime_context(project_token: Optional[str]) -> None:
    """Drop in-memory context and live memory for a project token."""
    token = (project_token or "").strip()
    if not token:
        return
    _project_contexts.pop(token, None)
    _project_live_memories.pop(token, None)


def extract_files_from_workspace_tree(workspace_tree: str) -> List[str]:
    """
    Extract file paths from the workspace tree string captured by the
    agent after execution. Parses the 'FILE: <path>' lines.
    """
    files = []
    for line in workspace_tree.split("\n"):
        stripped = line.strip()
        if stripped.startswith("FILE: "):
            files.append(stripped[6:].strip())
    return files


def extract_symbols_from_code(generated_code: str) -> Dict[str, List[str]]:
    """
    Quick extraction of newly created/modified symbols from generated
    builder code. Looks for common patterns like class/def/function declarations.
    """
    created = []
    modified = []
    for line in generated_code.split("\n"):
        stripped = line.strip()
        # Python patterns
        if stripped.startswith("class ") and ":" in stripped:
            name = stripped.split("(")[0].split(":")[0].replace("class ", "").strip()
            if name:
                created.append(f"class {name}")
        elif stripped.startswith("def ") and "(" in stripped:
            name = stripped.split("(")[0].replace("def ", "").strip()
            if name:
                created.append(f"def {name}()")
        # JS/TS patterns
        elif stripped.startswith("function ") and "(" in stripped:
            name = stripped.split("(")[0].replace("function ", "").strip()
            if name:
                created.append(f"function {name}()")
        elif stripped.startswith("export ") and ("class" in stripped or "function" in stripped):
            parts = stripped.split()
            if len(parts) >= 3:
                created.append(f"{parts[1]} {parts[2].split('(')[0]}")
    return {"created": created[:20], "modified": modified[:20]}



# ---------------------------------------------------------------------------
#  Layer 1 — Global Context (Repo-Wide Summary)
# ---------------------------------------------------------------------------

def build_global_context(graph: kg_service.CodeKnowledgeGraph) -> str:
    """
    Build a concise global context string from the knowledge graph.
    This provides universal codebase preferences to every agent.
    """
    lines = ["=== CODEBASE GLOBAL CONTEXT ==="]

    summary = graph.repo_summary
    stats = graph.stats()

    # Project identity
    if summary.get("project_name"):
        lines.append(f"Project: {summary['project_name']} v{summary.get('project_version', '')}")
    if summary.get("repo_url"):
        lines.append(f"Repository: {summary['repo_url']}")

    # Tech stack
    lines.append(f"\nLanguages: {', '.join(stats['languages'])}")
    lines.append(f"Source Files: {stats['total_files']}")
    lines.append(f"Total Code Entities: {stats['total_nodes']} nodes, {stats['total_edges']} edges")

    # Dependencies give a strong signal about the tech stack
    if summary.get("npm_dependencies"):
        deps = summary["npm_dependencies"]
        frameworks = []
        for d in deps:
            if d in ("react", "vue", "angular", "next", "nuxt", "express", "fastify", "koa", "nestjs"):
                frameworks.append(d)
        if frameworks:
            lines.append(f"Frameworks: {', '.join(frameworks)}")
        lines.append(f"NPM Dependencies: {', '.join(deps[:15])}")
        if len(deps) > 15:
            lines.append(f"  ... and {len(deps) - 15} more")

    if summary.get("python_requirements"):
        reqs = summary["python_requirements"]
        lines.append(f"Python Requirements: {', '.join(reqs[:15])}")

    # File structure overview (top-level dirs)
    file_nodes = [n for n in graph.nodes.values() if n.node_type == "file"]
    top_dirs = set()
    for fn in file_nodes:
        parts = fn.file_path.split("/")
        if len(parts) > 1:
            top_dirs.add(parts[0])
    if top_dirs:
        lines.append(f"\nProject Structure (top-level dirs): {', '.join(sorted(top_dirs))}")

    # Key classes and their relationships
    classes = [n for n in graph.nodes.values() if n.node_type == "class"]
    if classes:
        lines.append(f"\nKey Classes ({len(classes)} total):")
        for cls in classes[:20]:
            sc = cls.metadata.get("superclasses") or cls.metadata.get("superclass")
            inherit = f" extends {sc}" if sc else ""
            methods = [e for e in graph.get_edges_from(cls.node_id)
                       if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type == "method"]
            lines.append(f"  - {cls.name}{inherit} ({len(methods)} methods) [{cls.file_path}]")

    # Key functions (top-level, likely API endpoints or utilities)
    functions = [n for n in graph.nodes.values() if n.node_type == "function"]
    api_functions = [f for f in functions if any(
        d for d in (f.metadata.get("decorators") or [])
        if any(kw in d for kw in ("app.", "router.", "route", "get", "post", "put", "delete", "api"))
    )]
    if api_functions:
        lines.append(f"\nAPI Endpoints ({len(api_functions)} found):")
        for fn in api_functions[:15]:
            decs = fn.metadata.get("decorators", [])
            dec_str = f" @{decs[0]}" if decs else ""
            lines.append(f"  - {fn.name}{dec_str} [{fn.file_path}:L{fn.start_line}]")

    # README excerpt
    if summary.get("readme_excerpt"):
        readme = summary["readme_excerpt"][:1000]
        lines.append(f"\nREADME Excerpt:\n{readme}")

    lines.append("\n=== END GLOBAL CONTEXT ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Layer 2 — Project Rules (BRD + Governance + Domain)
# ---------------------------------------------------------------------------

def build_project_rules(
    brd_analysis: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
    custom_rules: Optional[str] = None,
) -> str:
    """
    Build project-specific rules from BRD analysis and governance data.
    """
    lines = ["=== PROJECT-SPECIFIC RULES ==="]

    if governance_context:
        classification = governance_context.get("classification", "")
        score = governance_context.get("weighted_score", "")
        lines.append(f"\nGovernance Classification: {classification}")
        lines.append(f"Governance Score: {score}/10")

        hard_stops = governance_context.get("hard_stops", [])
        if hard_stops:
            lines.append("HARD STOP CONSTRAINTS:")
            for hs in hard_stops:
                lines.append(f"  ⚠️ {hs}")

        answers = governance_context.get("answers", [])
        if answers:
            lines.append("\nGovernance Requirements:")
            for a in answers:
                if isinstance(a, dict):
                    q = a.get("question", f"Q{a.get('question_id', '')}")
                    opt = a.get("selected_option", "")
                    lines.append(f"  - {q}: {opt}")

    if brd_analysis:
        # Truncate very long analyses
        analysis_text = brd_analysis[:3000]
        lines.append(f"\nBRD ANALYSIS SUMMARY:\n{analysis_text}")

    if custom_rules:
        lines.append(f"\nCUSTOM RULES:\n{custom_rules}")

    lines.append("\n=== END PROJECT RULES ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Layer 3 — On-Demand Snippets (LightRAG Query)
# ---------------------------------------------------------------------------

async def get_task_context(
    project_token: str,
    task_description: str,
    task_type: Optional[str] = None,
) -> str:
    """
    Retrieve just-in-time context for a specific agent task
    using LightRAG's hybrid search (semantic + graph traversal).
    """
    # Build focused queries from the task
    queries = [task_description]

    # Add supplementary queries based on task type
    if task_type:
        type_queries = {
            "EPIC": f"What is the overall architecture and high-level design for: {task_description}",
            "FEATURE": f"What existing code, APIs, and components are related to: {task_description}",
            "STORY": f"What specific functions, classes, and files need to be modified for: {task_description}",
            "TASK": f"What implementation details, utilities, and helpers are relevant for: {task_description}",
            "BUG": f"What code paths, error handling, and edge cases are related to: {task_description}",
        }
        extra = type_queries.get(task_type)
        if extra:
            queries.append(extra)

    context = await rag_service.get_multiple_contexts(
        project_token, queries, mode="hybrid"
    )

    if not context:
        return ""

    return f"=== RELEVANT CODE CONTEXT (retrieved just-in-time) ===\n{context}\n=== END CODE CONTEXT ==="


def _note_scope_key(project_token: str) -> str:
    return (project_token or "").strip() or "__default__"


def _note_title_for_prefix(prefix: str, project_token: str) -> str:
    return f"{prefix}::{_note_scope_key(project_token)}::"


def _parse_note_payload(raw_content: Any) -> Dict[str, Any]:
    text = str(raw_content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    payload_match = re.search(
        r"<!--\s*AGENT_NOTE_PAYLOAD\s*(?P<payload>[\s\S]*?)-->",
        text,
        flags=re.DOTALL,
    )
    if payload_match:
        candidate = str(payload_match.group("payload") or "").strip()
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return {"summary": text}


def _coerce_note_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = payload.get("entries")
    if isinstance(entries, list):
        normalized = []
        for entry in entries:
            if isinstance(entry, dict):
                normalized.append(entry)
        if normalized:
            return normalized

    legacy_entry = {}
    for key in (
        "task_id",
        "task_title",
        "status",
        "branch",
        "planned_files",
        "completed_files",
        "symbols_created",
        "symbols_modified",
        "next_agent_should",
        "summary",
        "started_at",
        "updated_at",
        "completed_at",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            legacy_entry[key] = value
    return [legacy_entry] if legacy_entry else []


async def get_agent_notes_context(
    project_token: str,
    agent_id: Optional[str] = None,
    task_token: Optional[str] = None,
    max_notes: int = 8,
) -> str:
    """
    Retrieve the master project-plan note plus shared agent status notes
    and convert them into prompt-friendly coordination context.
    """
    effective_token = str(task_token or "").strip()
    if not effective_token:
        return ""

    try:
        from task_service import task_service
    except Exception:
        return ""

    try:
        notes = await task_service.list_notes(task_token=effective_token)
    except Exception as e:
        logger.warning(f"[{project_token}] Failed to list agent notes: {e}")
        return ""

    if not isinstance(notes, list):
        return ""

    master_prefix = _note_title_for_prefix("MASTER_PLAN", project_token)
    status_prefix = _note_title_for_prefix("STATUS", project_token)

    master_candidates = []
    relevant = []
    for note in notes:
        title = str((note or {}).get("title") or "").strip()
        if title.startswith(master_prefix):
            master_candidates.append(note)
        if title.startswith(status_prefix):
            relevant.append(note)
        if len(relevant) >= max_notes * 2:
            if len(master_candidates) >= 1:
                break

    live_entries = []
    history_entries = []
    lines = []
    has_content = False

    def _note_sort_key(note: Dict[str, Any]) -> int:
        value = note.get("id") or note.get("note_id") or 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    if master_candidates:
        master_candidates.sort(key=_note_sort_key, reverse=True)
        master_note = master_candidates[0]
        master_note_id = master_note.get("id") or master_note.get("note_id")
        if master_note_id:
            try:
                detail = await task_service.get_note_detail(int(master_note_id), task_token=effective_token)
                raw_content = str(detail.get("content") or "").strip()
                payload = _parse_note_payload(raw_content)
                title = str(detail.get("title") or master_note.get("title") or "").strip()
                structured_master_note = any(
                    key in payload
                    for key in (
                        "workspace_tree",
                        "tasks_considered",
                        "validation",
                        "stack_profile",
                    )
                )
                if not structured_master_note and raw_content:
                    has_content = True
                    lines.append("=== MASTER PROJECT PLAN NOTE ===")
                    lines.append(raw_content[:7000])
                    lines.append("=== END MASTER PROJECT PLAN NOTE ===")
                    payload = {}
                summary = str(payload.get("summary") or "").strip()
                workspace_tree = str(payload.get("workspace_tree") or "").strip()
                architecture_overview = str(payload.get("architecture_overview") or "").strip()
                dependencies = str(payload.get("dependencies") or "").strip()
                instructions = payload.get("instructions") if isinstance(payload.get("instructions"), list) else []
                tasks_considered = payload.get("tasks_considered") if isinstance(payload.get("tasks_considered"), list) else []
                recommended_assignments = payload.get("recommended_assignments") if isinstance(payload.get("recommended_assignments"), list) else []
                workspace_contract = payload.get("workspace_contract") if isinstance(payload.get("workspace_contract"), dict) else {}
                validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
                stack_profile = payload.get("stack_profile") if isinstance(payload.get("stack_profile"), dict) else {}
                allowed_roots = [
                    str(path or "").strip()
                    for path in (workspace_contract.get("allowed_source_roots") or [])
                    if str(path or "").strip()
                ]

                if structured_master_note:
                    lines.append("=== MASTER PROJECT PLAN NOTE ===")
                    lines.append(f"Title: {title}")
                    if summary:
                        has_content = True
                        lines.append(summary)
                    if stack_profile:
                        has_content = True
                        lines.append("\nSTACK DECISION:")
                        lines.append(
                            f"  - frontend={stack_profile.get('frontend')}"
                            + (f" | backend={stack_profile.get('backend')}" if stack_profile.get("backend") else "")
                            + (f" | confidence={stack_profile.get('confidence')}" if stack_profile.get("confidence") else "")
                        )
                    if tasks_considered:
                        has_content = True
                        lines.append("\nTASKS CONSIDERED BY MASTER AGENT:")
                        for task in tasks_considered[:20]:
                            if not isinstance(task, dict):
                                continue
                            task_title = str(task.get("title") or task.get("task_title") or "Untitled task")
                            task_phase = str(task.get("phase") or "").strip()
                            task_priority = str(task.get("priority") or "").strip()
                            lines.append(
                                f"  - {task_title}"
                                + (f" | phase={task_phase}" if task_phase else "")
                                + (f" | priority={task_priority}" if task_priority else "")
                            )
                            planned_files = [
                                str(path or "").strip()
                                for path in (task.get("planned_files") or [])
                                if str(path or "").strip()
                            ]
                            if planned_files:
                                lines.append(f"    Planned files: {', '.join(planned_files[:6])}")
                            assignee = str(task.get("assignee") or "").strip()
                            opt_in_username = str(task.get("opt_in_username") or "").strip()
                            assignment_reason = str(task.get("assignment_reason") or "").strip()
                            if assignee or opt_in_username:
                                lines.append(
                                    "    Recommended owner: "
                                    + " | ".join(
                                        item
                                        for item in [
                                            assignee,
                                            f"opt-in={opt_in_username}" if opt_in_username else "",
                                        ]
                                        if item
                                    )
                                )
                            if assignment_reason:
                                lines.append(f"    Master reason: {assignment_reason[:220]}")
                    if recommended_assignments:
                        has_content = True
                        lines.append("\nMASTER RECOMMENDED TASK OWNERSHIP:")
                        for entry in recommended_assignments[:20]:
                            if not isinstance(entry, dict):
                                continue
                            title_text = str(entry.get("title") or "Untitled task").strip()
                            recommended_agent_id = str(entry.get("recommended_agent_id") or "").strip()
                            opt_in_username = str(entry.get("opt_in_username") or "").strip()
                            lines.append(
                                f"  - {title_text}"
                                + (
                                    " -> "
                                    + " | ".join(
                                        item
                                        for item in [
                                            recommended_agent_id,
                                            f"opt-in={opt_in_username}" if opt_in_username else "",
                                        ]
                                        if item
                                    )
                                    if recommended_agent_id or opt_in_username
                                    else ""
                                )
                            )
                            reason = str(entry.get("reason") or "").strip()
                            if reason:
                                lines.append(f"    Reason: {reason[:220]}")
                    if workspace_tree:
                        has_content = True
                        lines.append("\nCANONICAL PROJECT TREE:")
                        lines.append(workspace_tree[:4500])
                    if architecture_overview:
                        has_content = True
                        lines.append("\nARCHITECTURE OVERVIEW:")
                        lines.append(architecture_overview[:1500])
                    if allowed_roots:
                        has_content = True
                        lines.append("\nCANONICAL SOURCE ROOTS:")
                        for root in allowed_roots[:12]:
                            lines.append(f"  - {root}")
                    if dependencies:
                        has_content = True
                        lines.append("\nKEY DEPENDENCIES:")
                        lines.append(dependencies[:900])
                    if validation:
                        has_content = True
                        validator_agent_id = str(validation.get("validator_agent_id") or "structure_validator").strip()
                        mode = str(validation.get("mode") or "").strip()
                        confidence = validation.get("confidence")
                        lines.append("\nVALIDATION:")
                        lines.append(
                            f"  - approved={bool(validation.get('approved'))}"
                            + (f" | validator={validator_agent_id}" if validator_agent_id else "")
                            + (f" | mode={mode}" if mode else "")
                            + (f" | confidence={confidence}" if confidence not in (None, "") else "")
                        )
                        for issue in (validation.get("issues_missing_files") or [])[:6]:
                            lines.append(f"  - missing/coverage: {str(issue)[:220]}")
                        for issue in (validation.get("issues_conflicts") or [])[:6]:
                            lines.append(f"  - conflict: {str(issue)[:220]}")
                        for recommendation in (validation.get("recommendations") or [])[:6]:
                            lines.append(f"  - recommendation: {str(recommendation)[:220]}")
                    if instructions:
                        has_content = True
                        lines.append("\nMASTER INSTRUCTIONS:")
                        for instruction in instructions[:8]:
                            lines.append(f"  - {str(instruction)[:240]}")
                    lines.append("=== END MASTER PROJECT PLAN NOTE ===")
            except Exception as e:
                logger.warning(f"[{project_token}] Failed to read master note: {e}")

    for note in relevant:
        note_id = (note or {}).get("id") or (note or {}).get("note_id")
        if not note_id:
            continue
        try:
            detail = await task_service.get_note_detail(int(note_id), task_token=effective_token)
        except Exception:
            continue
        title = str(detail.get("title") or note.get("title") or "").strip()
        payload = _parse_note_payload(detail.get("content"))
        payload["title"] = title
        note_agent_id = str(payload.get("agent_id") or "").strip()
        if note_agent_id and note_agent_id == agent_id:
            continue

        entries = _coerce_note_entries(payload)
        if not entries:
            continue

        for entry in entries:
            entry["agent_id"] = entry.get("agent_id") or note_agent_id or "unknown"

        active_entry = None
        for entry in reversed(entries):
            if str(entry.get("status") or "").lower() in {"in_progress", "running", "started"}:
                active_entry = entry
                break
        if active_entry:
            live_entries.append(active_entry)

        for entry in reversed(entries):
            status_value = str(entry.get("status") or "").lower()
            if status_value not in {"completed", "failed"}:
                continue
            history_entries.append(entry)
            if len(history_entries) >= max_notes * 3:
                break

    live_entries.sort(key=lambda entry: str(entry.get("updated_at") or ""), reverse=True)
    history_entries.sort(key=lambda entry: str(entry.get("updated_at") or ""), reverse=True)

    if live_entries:
        has_content = True
        lines.append("\n=== SHARED AGENT STATUS NOTES ===")
        lines.append("LIVE STATUS NOTES:")
        for entry in live_entries[:max_notes]:
            lines.append(
                f"  - {entry.get('agent_id', 'unknown')} | "
                f"{entry.get('status', 'unknown')} | "
                f"{entry.get('task_title', entry.get('task_id', 'unknown task'))}"
            )
            planned = entry.get("planned_files") or []
            if planned:
                lines.append(f"    Planned files: {', '.join(planned[:6])}")
            next_step = entry.get("next_agent_should") or entry.get("summary")
            if next_step:
                lines.append(f"    Context: {str(next_step)[:220]}")

    if history_entries:
        has_content = True
        lines.append("\nRECENT TASK HISTORY:")
        for entry in history_entries[:max_notes]:
            lines.append(
                f"  - {entry.get('agent_id', 'unknown')} | "
                f"{entry.get('status', 'unknown')} | "
                f"{entry.get('task_title', entry.get('task_id', 'Untitled'))}"
            )
            completed = entry.get("completed_files") or []
            if completed:
                lines.append(f"    Completed files: {', '.join(completed[:6])}")
            symbols = entry.get("symbols_created") or []
            if symbols:
                lines.append(f"    Symbols created: {', '.join(symbols[:8])}")
            next_step = entry.get("next_agent_should") or entry.get("summary")
            if next_step:
                lines.append(f"    Next step: {str(next_step)[:260]}")

    if not has_content:
        return ""

    if live_entries or history_entries:
        lines.append("\n=== END SHARED AGENT STATUS NOTES ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Combined Context Assembly
# ---------------------------------------------------------------------------

async def get_full_agent_context(
    project_token: str,
    task_description: str,
    task_type: Optional[str] = None,
    brd_analysis: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
    task_token: Optional[str] = None,
    max_context_length: int = 18000,
) -> str:
    """
    Assemble the complete four-layer context for an agent.

    This is the main entry point — call this before an agent starts
    working on a task to get precisely targeted context.
    """
    parts = []

    # Layer 1 — Global Context
    project_ctx = _project_contexts.get(project_token, {})
    global_context = project_ctx.get("global_context", "")
    if global_context:
        parts.append(global_context)

    # Layer 2 — Project Rules
    project_rules = build_project_rules(
        brd_analysis=brd_analysis,
        governance_context=governance_context,
    )
    parts.append(project_rules)

    workspace_contract_ctx = build_workspace_contract_context(project_token)
    if workspace_contract_ctx:
        parts.append(workspace_contract_ctx)

    # Layer 3 — On-Demand Snippets (JIT from LightRAG)
    rag_status = rag_service.get_indexing_status(project_token)
    if rag_status.get("status") == "ready":
        task_context = await get_task_context(
            project_token, task_description, task_type
        )
        if task_context:
            parts.append(task_context)
    else:
        parts.append(
            f"[Knowledge Graph not indexed for this project. "
            f"Status: {rag_status.get('status', 'unknown')}]"
        )

    # Layer 4 — Cross-Agent Awareness
    memory = get_live_memory(project_token)
    cross_agent_ctx = memory.build_cross_agent_context(
        requesting_agent_id=agent_id or "unknown"
    )
    parts.append(cross_agent_ctx)

    notes_ctx = await get_agent_notes_context(
        project_token=project_token,
        agent_id=agent_id,
        task_token=task_token,
    )
    if notes_ctx:
        parts.append(notes_ctx)

    full_context = "\n\n".join(parts)

    # Truncate if too long
    if len(full_context) > max_context_length:
        full_context = full_context[:max_context_length] + "\n\n... [context truncated]"

    return full_context


# ---------------------------------------------------------------------------
#  Full Indexing Pipeline
# ---------------------------------------------------------------------------

async def index_project_repository(
    project_token: str,
    repo_url: str,
    token: Optional[str] = None,
    branch: str = "main",
    brd_analysis: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: Clone repo → Build KG → Index into LightRAG → Store context.

    This is the main entry point for indexing a project's codebase.
    """
    logger.info(f"[{project_token}] Starting full repository indexing pipeline")

    result = {
        "project_token": project_token,
        "status": "indexing",
        "steps": {},
    }

    try:
        # Step 1: Clone and parse with Tree-sitter
        logger.info(f"[{project_token}] Step 1: Cloning and parsing repository")
        graph, repo_path = await kg_service.index_repository(
            repo_url, token=token, branch=branch
        )
        result["steps"]["clone_and_parse"] = {
            "status": "done",
            "stats": graph.stats(),
        }

        # Step 2: Build global context from KG
        logger.info(f"[{project_token}] Step 2: Building global context")
        global_context = build_global_context(graph)
        result["steps"]["global_context"] = {
            "status": "done",
            "length": len(global_context),
        }

        # Step 3: Generate text chunks for LightRAG
        logger.info(f"[{project_token}] Step 3: Generating text chunks for RAG")
        text_chunks = kg_service.generate_graph_text_for_rag(graph)
        result["steps"]["chunking"] = {
            "status": "done",
            "total_chunks": len(text_chunks),
        }

        # Step 4: Index into LightRAG
        logger.info(f"[{project_token}] Step 4: Indexing into LightRAG")
        rag_result = await rag_service.index_codebase(
            project_token,
            text_chunks,
            metadata={
                "repo_url": repo_url,
                "graph_stats": graph.stats(),
            },
        )
        result["steps"]["rag_indexing"] = rag_result

        # Step 5: Store project context
        workspace_contract = _build_workspace_contract_from_file_paths(
            project_token,
            _collect_repo_file_paths(repo_path),
            source="repo_index",
        )
        _project_contexts[project_token] = {
            "graph": graph,
            "repo_path": repo_path,
            "global_context": global_context,
            "project_rules": build_project_rules(
                brd_analysis=brd_analysis,
                governance_context=governance_context,
            ),
            "workspace_contract": workspace_contract,
        }
        result["steps"]["context_store"] = {"status": "done"}

        result["status"] = "ready"
        result["graph_stats"] = graph.stats()
        logger.info(f"[{project_token}] Indexing pipeline complete!")

    except Exception as e:
        logger.error(f"[{project_token}] Indexing pipeline failed: {e}")
        result["status"] = "error"
        result["error"] = str(e)

    return result


def get_project_graph_stats(project_token: str) -> Optional[Dict[str, Any]]:
    """Get knowledge graph statistics for a project."""
    ctx = _project_contexts.get(project_token)
    if ctx and ctx.get("graph"):
        return ctx["graph"].stats()
    return None


def is_project_indexed(project_token: str) -> bool:
    """Check if a project has been indexed."""
    status = rag_service.get_indexing_status(project_token)
    return status.get("status") == "ready"


# ---------------------------------------------------------------------------
#  Living KG — Agent Output Feedback Loop (Blitzy Pattern)
# ---------------------------------------------------------------------------
#
# When an agent completes a task, its generated code is:
#   1. Parsed with Tree-sitter to extract new nodes/edges
#   2. Added to the existing KG (same graph, new nodes)
#   3. Converted to text chunks and incrementally indexed into LightRAG
#
# This makes the KG a *living* document. When Agent B queries for
# "authentication", it finds both the original codebase AND the new
# auth code Agent A just created — via normal semantic search (Layer 3).
# No broadcasting needed.
# ---------------------------------------------------------------------------


def _parse_code_string_to_chunks(
    code_content: str,
    file_path: str,
    language: str = "python",
    agent_id: str = "unknown_agent",
) -> List[str]:
    """
    Parse a code string (generated by an agent) into structured RAG chunks.
    Uses Tree-sitter if available for the language, otherwise falls back
    to a simpler line-based approach.
    """
    chunks = []

    # Build a structured overview chunk
    lines = code_content.split("\n")
    overview_parts = [
        f"AGENT-GENERATED CODE ({agent_id})",
        f"File: {file_path}",
        f"Language: {language}",
        f"Lines: {len(lines)}",
    ]

    # Extract key symbols for the overview
    classes = []
    functions = []
    imports = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("class ") and (":" in stripped or "{" in stripped):
            name = stripped.split("(")[0].split(":")[0].split("{")[0].replace("class ", "").strip()
            if name:
                classes.append(name)
        elif stripped.startswith("def ") and "(" in stripped:
            name = stripped.split("(")[0].replace("def ", "").strip()
            if name:
                functions.append(name)
        elif stripped.startswith("async def ") and "(" in stripped:
            name = stripped.split("(")[0].replace("async def ", "").strip()
            if name:
                functions.append(f"async {name}")
        elif stripped.startswith("function ") and "(" in stripped:
            name = stripped.split("(")[0].replace("function ", "").strip()
            if name:
                functions.append(name)
        elif stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped[:100])
        elif stripped.startswith("export "):
            if "class" in stripped or "function" in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    functions.append(f"export {parts[2].split('(')[0]}")

    if imports:
        overview_parts.append(f"\nImports: {len(imports)}")
        for imp in imports[:10]:
            overview_parts.append(f"  - {imp}")
    if classes:
        overview_parts.append(f"\nClasses: {', '.join(classes)}")
    if functions:
        overview_parts.append(f"\nFunctions: {', '.join(functions[:20])}")

    overview_parts.append(f"\nSOURCE CODE:\n```\n{code_content[:8000]}\n```")
    chunks.append("\n".join(overview_parts))

    return chunks


def _parse_workspace_to_file_dict(workspace_tree: str) -> Dict[str, str]:
    """
    Parse the workspace tree output (from Docker container capture)
    into a dict of {file_path: file_content}.
    """
    files: Dict[str, str] = {}
    current_file = None
    current_lines: List[str] = []

    for line in workspace_tree.split("\n"):
        stripped = line.strip()
        if stripped.startswith("FILE: "):
            # Save previous file
            if current_file:
                files[current_file] = "\n".join(current_lines)
            current_file = stripped[6:].strip()
            current_lines = []
        elif current_file and not stripped.startswith(("=" * 10, "-" * 10, "File Tree:", "Total:", "PROJECT STRUCTURE")):
            current_lines.append(line)

    # Save last file
    if current_file:
        files[current_file] = "\n".join(current_lines)

    return files


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return {
        "py": "python", "js": "javascript", "jsx": "javascript",
        "ts": "typescript", "tsx": "typescript", "java": "java",
        "go": "go", "rs": "rust", "rb": "ruby", "php": "php",
        "html": "html", "css": "css", "json": "json", "yaml": "yaml",
        "yml": "yaml", "md": "markdown", "sql": "sql",
    }.get(ext, "unknown")


async def update_kg_with_agent_output(
    project_token: str,
    agent_id: str,
    task_title: str,
    workspace_tree: str,
    generated_code: str,
) -> Dict[str, Any]:
    """
    Feed agent-generated code back into the Knowledge Graph + RAG.

    This is the core of the Blitzy pattern: the KG is a LIVING DOCUMENT.
    When Agent A creates new code, it's parsed and inserted into the KG
    so that Agent B can discover it via normal semantic search.

    Pipeline:
      1. Parse workspace_tree to extract individual files
      2. For each code file: extract structure, create RAG chunks
      3. Add new nodes/edges to the existing KG graph
      4. Incrementally insert new chunks into LightRAG

    Returns:
      Dict with stats about what was added
    """
    result = {
        "agent_id": agent_id,
        "task_title": task_title,
        "files_processed": 0,
        "chunks_created": 0,
        "chunks_inserted": 0,
        "nodes_added": 0,
        "edges_added": 0,
        "status": "pending",
    }

    try:
        project_ctx = _project_contexts.get(project_token)

        # ── Blitzy Pattern: Bootstrap KG from first agent output ──────────
        # For new projects, there is no prior full indexing. Instead of
        # skipping, we bootstrap a minimal project context using this
        # agent's output. This makes the KG a "living document" from
        # moment one, so subsequent agents can discover the code the
        # first agent created.
        bootstrapped = False
        if not project_ctx:
            logger.info(
                f"[{project_token}] No existing KG — bootstrapping from "
                f"agent {agent_id} output (Blitzy living-KG pattern)"
            )
            graph = kg_service.CodeKnowledgeGraph()
            graph.repo_summary = {
                "project_name": f"project_{project_token[:8]}",
                "bootstrapped_by": agent_id,
                "bootstrap_task": task_title,
            }
            project_ctx = {
                "graph": graph,
                "repo_path": None,
                "global_context": "",
                "project_rules": "",
                "workspace_contract": _build_workspace_contract_from_file_paths(
                    project_token,
                    list(file_dict.keys()) if 'file_dict' in locals() else [],
                    source="workspace_tree",
                ),
            }
            _project_contexts[project_token] = project_ctx
            bootstrapped = True

        graph = project_ctx.get("graph")

        # 1. Parse workspace tree into file dict
        file_dict = _parse_workspace_to_file_dict(workspace_tree)
        update_workspace_contract_from_workspace_tree(project_token, workspace_tree)

        # Filter to actual code files (skip binaries, configs, etc.)
        code_extensions = {
            "py", "js", "jsx", "ts", "tsx", "java", "go", "rs", "rb",
            "php", "html", "css", "sql", "sh",
        }
        code_files = {}
        for fpath, content in file_dict.items():
            ext = fpath.rsplit(".", 1)[-1].lower() if "." in fpath else ""
            if ext in code_extensions and len(content.strip()) > 10:
                code_files[fpath] = content

        if not code_files:
            result["status"] = "skipped"
            result["reason"] = "no_code_files_in_workspace"
            return result

        # 2. Generate RAG chunks for each file
        all_chunks: List[str] = []

        # Create a summary chunk for this agent's entire output
        summary_lines = [
            f"AGENT OUTPUT SUMMARY",
            f"Agent: {agent_id}",
            f"Task: {task_title}",
            f"Files created/modified: {len(code_files)}",
            f"Files: {', '.join(list(code_files.keys())[:20])}",
        ]
        all_chunks.append("\n".join(summary_lines))

        for fpath, content in code_files.items():
            lang = _detect_language(fpath)
            file_chunks = _parse_code_string_to_chunks(
                code_content=content,
                file_path=fpath,
                language=lang,
                agent_id=agent_id,
            )
            all_chunks.extend(file_chunks)

            # 3. Update the existing KG with new nodes
            if graph:
                try:
                    # Create a file node for the agent-generated file
                    file_id = f"agent_{agent_id}_{fpath}"
                    file_node = kg_service.GraphNode(
                        node_id=file_id,
                        node_type="file",
                        name=fpath.split("/")[-1],
                        file_path=fpath,
                        language=lang,
                        start_line=1,
                        end_line=len(content.split("\n")),
                        metadata={"source": "agent_output", "agent_id": agent_id},
                    )
                    graph.add_node(file_node)
                    graph.file_contents[fpath] = content
                    result["nodes_added"] += 1

                    # Parse symbols from the code and add as child nodes
                    symbols = extract_symbols_from_code(content)
                    for sym_name in symbols.get("created", []):
                        sym_type = "function"
                        if sym_name.startswith("class "):
                            sym_type = "class"
                            sym_name = sym_name.replace("class ", "")
                        elif sym_name.startswith("def "):
                            sym_name = sym_name.replace("def ", "").replace("()", "")
                        elif sym_name.startswith("function "):
                            sym_name = sym_name.replace("function ", "").replace("()", "")

                        sym_id = f"agent_{agent_id}_{fpath}_{sym_name}"
                        sym_node = kg_service.GraphNode(
                            node_id=sym_id,
                            node_type=sym_type,
                            name=sym_name,
                            file_path=fpath,
                            language=lang,
                            start_line=0,
                            end_line=0,
                            metadata={"source": "agent_output", "agent_id": agent_id},
                        )
                        graph.add_node(sym_node)
                        result["nodes_added"] += 1

                        # Edge: file contains symbol
                        edge = kg_service.GraphEdge(
                            source_id=file_id,
                            target_id=sym_id,
                            edge_type="contains",
                            metadata={"source": "agent_output"},
                        )
                        graph.add_edge(edge)
                        result["edges_added"] += 1

                except Exception as kg_err:
                    logger.warning(
                        f"[{project_token}] KG node update for {fpath} failed: {kg_err}"
                    )

        result["files_processed"] = len(code_files)
        result["chunks_created"] = len(all_chunks)

        # 4. Insert into LightRAG
        #    If this project was just bootstrapped, use index_codebase() which
        #    sets the RAG status to "ready". Otherwise use incremental_insert()
        #    which appends to the existing index.
        if bootstrapped:
            logger.info(
                f"[{project_token}] First-time RAG indexing (bootstrap) "
                f"with {len(all_chunks)} chunks"
            )
            rag_result = await rag_service.index_codebase(
                project_token=project_token,
                text_chunks=all_chunks,
                metadata={
                    "source": "agent_bootstrap",
                    "agent_id": agent_id,
                    "task_title": task_title,
                },
            )
            result["chunks_inserted"] = rag_result.get("indexed_chunks", 0)
        else:
            rag_result = await rag_service.incremental_insert(
                project_token=project_token,
                text_chunks=all_chunks,
                source_label=f"agent_{agent_id}_{task_title[:50]}",
            )
            result["chunks_inserted"] = rag_result.get("inserted_chunks", 0)

        # Update global context with new stats
        if graph:
            project_ctx["global_context"] = build_global_context(graph)

        result["status"] = "success"
        logger.info(
            f"[{project_token}] KG updated with agent {agent_id} output: "
            f"{result['files_processed']} files, {result['nodes_added']} nodes, "
            f"{result['chunks_inserted']} RAG chunks"
        )

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(
            f"[{project_token}] update_kg_with_agent_output failed: {e}"
        )

    return result
