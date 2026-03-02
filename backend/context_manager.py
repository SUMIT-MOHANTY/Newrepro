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
import threading
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

    def __init__(self):
        self._lock = threading.Lock()
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
            "**/frontend/src/**", "**/client/src/**", "**/src/**",
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

    def get_file_owner(self, file_path: str) -> Optional[str]:
        """Determine which domain should own a file based on its path."""
        import fnmatch

        # Check backend ownership
        for pattern in self._backend_files:
            if fnmatch.fnmatch(file_path, pattern):
                return "backend"

        # Check frontend ownership
        for pattern in self._frontend_files:
            if fnmatch.fnmatch(file_path, pattern):
                return "frontend"

        # Default to shared (requires coordination)
        return None

    def can_agent_edit_file(self, agent_domain: str, file_path: str) -> tuple[bool, str]:
        """
        Check if an agent can edit a file based on domain ownership.
        Returns (allowed, reason).
        """
        import fnmatch

        # Check if it's a shared file
        for pattern in self._shared_files:
            if fnmatch.fnmatch(file_path, pattern):
                # Shared files need coordination - check if anyone else is editing
                editors = self.file_locks.get(file_path, set())
                if editors:
                    return False, f"Shared file '{file_path}' currently being edited by: {editors}"
                return True, "Shared file - coordination required"

        # Check backend ownership
        for pattern in self._backend_files:
            if fnmatch.fnmatch(file_path, pattern):
                if agent_domain == "backend":
                    return True, "Backend-owned file"
                else:
                    return False, f"File '{file_path}' is owned by backend domain"

        # Check frontend ownership
        for pattern in self._frontend_files:
            if fnmatch.fnmatch(file_path, pattern):
                if agent_domain == "frontend":
                    return True, "Frontend-owned file"
                else:
                    return False, f"File '{file_path}' is owned by frontend domain"

        # Unknown file - allow but log warning
        return True, "Unknown file type - allowing edit"

    def register_file_intent(self, agent_id: str, file_paths: List[str]):
        """Register that an agent intends to touch certain files."""
        with self._lock:
            for fp in file_paths:
                if fp not in self.file_locks:
                    self.file_locks[fp] = set()
                self.file_locks[fp].add(agent_id)

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
        with self._lock:
            for fp in file_paths:
                if fp not in self.file_locks:
                    self.file_locks[fp] = set()
                self.file_locks[fp].add(agent_id)

    def get_file_conflicts(self, agent_id: str, target_files: List[str]) -> Dict[str, List[str]]:
        """
        Check if any of the target files are being edited by other agents.
        Returns {file_path: [other_agent_ids]} for conflicts.
        """
        with self._lock:
            conflicts = {}
            for fp in target_files:
                others = self.file_locks.get(fp, set()) - {agent_id}
                if others:
                    conflicts[fp] = list(others)
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
        _project_live_memories[project_token] = ProjectLiveMemory()
    return _project_live_memories[project_token]


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
        _project_contexts[project_token] = {
            "graph": graph,
            "repo_path": repo_path,
            "global_context": global_context,
            "project_rules": build_project_rules(
                brd_analysis=brd_analysis,
                governance_context=governance_context,
            ),
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
            }
            _project_contexts[project_token] = project_ctx
            bootstrapped = True

        graph = project_ctx.get("graph")

        # 1. Parse workspace tree into file dict
        file_dict = _parse_workspace_to_file_dict(workspace_tree)

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
