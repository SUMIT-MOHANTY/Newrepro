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

    def register_task_start(
        self,
        agent_id: str,
        task_title: str,
        task_description: str,
        branch_name: Optional[str] = None,
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
                    lines.append(f"  • {r.agent_id}: \"{r.task_title}\"{branch_info}")
                    lines.append(f"    Description: {r.task_description[:200]}")

            # File conflicts (files being edited by others RIGHT NOW)
            conflict_files = {}
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
