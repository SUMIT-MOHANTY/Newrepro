"""
Knowledge Graph Service — Codebase Structural Analysis
Uses Tree-sitter to parse source code into AST and build a relational
knowledge graph of files, classes, functions, imports, and dependencies.
"""

import os
import re
import json
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import tree_sitter
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript

try:
    import tree_sitter_typescript as tstypescript
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

try:
    import git as gitpython
except ImportError:
    gitpython = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Language Setup
# ---------------------------------------------------------------------------

PYTHON_LANGUAGE = tree_sitter.Language(tspython.language())
JS_LANGUAGE = tree_sitter.Language(tsjavascript.language())

if _TS_AVAILABLE:
    TS_LANGUAGE = tree_sitter.Language(tstypescript.language_typescript())
    TSX_LANGUAGE = tree_sitter.Language(tstypescript.language_tsx())
else:
    TS_LANGUAGE = None
    TSX_LANGUAGE = None

EXTENSION_LANGUAGE_MAP: Dict[str, tree_sitter.Language] = {
    ".py": PYTHON_LANGUAGE,
    ".js": JS_LANGUAGE,
    ".jsx": JS_LANGUAGE,      # JSX is a superset handled by JS grammar
    ".mjs": JS_LANGUAGE,
    ".cjs": JS_LANGUAGE,
}

if _TS_AVAILABLE:
    EXTENSION_LANGUAGE_MAP.update({
        ".ts": TS_LANGUAGE,
        ".tsx": TSX_LANGUAGE,
    })

# Directories to always skip
SKIP_DIRS = {
    "node_modules", "vendor", "dist", "build", "__pycache__", ".git",
    "venv", ".venv", "env", ".env", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".next", ".nuxt", "out", "target", "bin", "obj",
    ".idea", ".vscode", ".eclipse",
}

# Max file size to parse (500 KB)
MAX_FILE_SIZE = 500_000

# ---------------------------------------------------------------------------
#  Data Structures
# ---------------------------------------------------------------------------

class GraphNode:
    """Represents a node in the code knowledge graph."""
    def __init__(
        self,
        node_id: str,
        node_type: str,     # file, class, function, method, import, variable
        name: str,
        file_path: str,
        start_line: int = 0,
        end_line: int = 0,
        language: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.name = name
        self.file_path = file_path
        self.start_line = start_line
        self.end_line = end_line
        self.language = language
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "metadata": self.metadata,
        }


class GraphEdge:
    """Represents a directed edge in the code knowledge graph."""
    def __init__(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,     # contains, imports, calls, inherits, decorates
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.source_id = source_id
        self.target_id = target_id
        self.edge_type = edge_type
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "metadata": self.metadata,
        }


class CodeKnowledgeGraph:
    """In-memory code knowledge graph with nodes and edges."""
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.file_contents: Dict[str, str] = {}  # path -> content
        self.repo_summary: Dict[str, Any] = {}

    def add_node(self, node: GraphNode):
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge):
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.target_id == node_id]

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[str]:
        """BFS to get all neighbor node IDs up to given depth."""
        visited = set()
        queue = [(node_id, 0)]
        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            for edge in self.edges:
                if edge.source_id == current and edge.target_id not in visited:
                    queue.append((edge.target_id, d + 1))
                if edge.target_id == current and edge.source_id not in visited:
                    queue.append((edge.source_id, d + 1))
        visited.discard(node_id)
        return list(visited)

    def stats(self) -> Dict[str, Any]:
        type_counts = {}
        for n in self.nodes.values():
            type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1
        edge_type_counts = {}
        for e in self.edges:
            edge_type_counts[e.edge_type] = edge_type_counts.get(e.edge_type, 0) + 1
        languages = set(n.language for n in self.nodes.values() if n.language)
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
            "languages": list(languages),
            "total_files": type_counts.get("file", 0),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stats": self.stats(),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "repo_summary": self.repo_summary,
        }

    def get_code_snippet(self, node_id: str) -> Optional[str]:
        """Get the source code for a specific node."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        content = self.file_contents.get(node.file_path)
        if not content:
            return None
        lines = content.split("\n")
        start = max(0, node.start_line - 1)
        end = min(len(lines), node.end_line)
        return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
#  Repository Cloning
# ---------------------------------------------------------------------------

def clone_repository(
    repo_url: str,
    token: Optional[str] = None,
    branch: str = "main",
    target_dir: Optional[str] = None,
) -> str:
    """Clone a git repository and return the local path."""
    if target_dir is None:
        target_dir = tempfile.mkdtemp(prefix="kg_repo_")

    # Inject token into URL for private repos
    clone_url = repo_url
    if token and "github.com" in repo_url:
        clone_url = repo_url.replace("https://", f"https://{token}@")

    logger.info(f"Cloning {repo_url} (branch={branch}) into {target_dir}")
    if gitpython is not None:
        try:
            gitpython.Repo.clone_from(
                clone_url,
                target_dir,
                branch=branch,
                depth=1,  # shallow clone for speed
            )
        except gitpython.exc.GitCommandError as e:
            # Try without branch specification (some repos use 'master')
            logger.warning(f"Clone with branch={branch} failed, trying default: {e}")
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
            gitpython.Repo.clone_from(clone_url, target_dir, depth=1)
    else:
        logger.warning("GitPython is not installed; falling back to git CLI clone.")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, clone_url, target_dir],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Clone with branch={branch} failed, trying default: {e.stderr or e}")
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, target_dir],
                check=True,
                capture_output=True,
                text=True,
            )

    logger.info(f"Repository cloned to {target_dir}")
    return target_dir


def cleanup_repo(repo_path: str):
    """Remove a cloned repository."""
    if repo_path and os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
        logger.info(f"Cleaned up repository at {repo_path}")


# ---------------------------------------------------------------------------
#  File Discovery
# ---------------------------------------------------------------------------

def discover_files(repo_path: str) -> List[Dict[str, Any]]:
    """
    Walk the repository and find all parseable source files.
    Returns list of {path, relative_path, language, size}.
    """
    files = []
    repo_path = os.path.abspath(repo_path)

    for root, dirs, filenames in os.walk(repo_path):
        # Prune skip directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in filenames:
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, repo_path)
            _, ext = os.path.splitext(fname)
            ext_lower = ext.lower()

            if ext_lower not in EXTENSION_LANGUAGE_MAP:
                continue

            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            if size > MAX_FILE_SIZE or size == 0:
                continue

            files.append({
                "path": full_path,
                "relative_path": rel_path,
                "extension": ext_lower,
                "language": _ext_to_language_name(ext_lower),
                "size": size,
            })

    return files


def _ext_to_language_name(ext: str) -> str:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }
    return mapping.get(ext, "unknown")


# ---------------------------------------------------------------------------
#  AST Parsing with Tree-sitter
# ---------------------------------------------------------------------------

def _get_node_text(node: tree_sitter.Node, source_bytes: bytes) -> str:
    """Extract UTF-8 text from a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def parse_python_file(
    file_path: str,
    relative_path: str,
    source: bytes,
    graph: CodeKnowledgeGraph,
):
    """Parse a Python file and extract classes, functions, imports."""
    parser = tree_sitter.Parser(PYTHON_LANGUAGE)
    tree = parser.parse(source)
    root = tree.root_node

    file_id = f"file::{relative_path}"
    file_node = GraphNode(
        node_id=file_id,
        node_type="file",
        name=os.path.basename(relative_path),
        file_path=relative_path,
        start_line=1,
        end_line=root.end_point[0] + 1,
        language="python",
    )
    graph.add_node(file_node)

    for child in root.children:
        if child.type == "class_definition":
            _parse_python_class(child, source, relative_path, file_id, graph)
        elif child.type == "function_definition":
            _parse_python_function(child, source, relative_path, file_id, graph)
        elif child.type == "decorated_definition":
            # Unwrap the decorator to get the actual definition
            for sub in child.children:
                if sub.type == "class_definition":
                    _parse_python_class(sub, source, relative_path, file_id, graph)
                elif sub.type == "function_definition":
                    _parse_python_function(sub, source, relative_path, file_id, graph)
        elif child.type in ("import_statement", "import_from_statement"):
            _parse_python_import(child, source, relative_path, file_id, graph)


def _parse_python_class(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    graph: CodeKnowledgeGraph,
):
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    class_name = _get_node_text(name_node, source)
    class_id = f"class::{rel_path}::{class_name}"

    # Get parent classes (superclasses)
    superclasses = []
    arg_list = node.child_by_field_name("superclasses")
    if arg_list:
        for arg in arg_list.children:
            if arg.type == "identifier":
                superclasses.append(_get_node_text(arg, source))

    # Get docstring
    docstring = _extract_python_docstring(node, source)

    class_node = GraphNode(
        node_id=class_id,
        node_type="class",
        name=class_name,
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language="python",
        metadata={
            "superclasses": superclasses,
            "docstring": docstring[:200] if docstring else None,
        },
    )
    graph.add_node(class_node)
    graph.add_edge(GraphEdge(parent_id, class_id, "contains"))

    # Add inheritance edges
    for sc in superclasses:
        # We'll try to resolve later; for now link by name
        graph.add_edge(GraphEdge(class_id, f"class::*::{sc}", "inherits", {"unresolved": True}))

    # Parse methods inside the class
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "function_definition":
                _parse_python_function(child, source, rel_path, class_id, graph, is_method=True)
            elif child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type == "function_definition":
                        _parse_python_function(sub, source, rel_path, class_id, graph, is_method=True)


def _parse_python_function(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    graph: CodeKnowledgeGraph,
    is_method: bool = False,
):
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    func_name = _get_node_text(name_node, source)
    func_type = "method" if is_method else "function"
    func_id = f"{func_type}::{rel_path}::{parent_id.split('::')[-1]}::{func_name}" if is_method \
        else f"function::{rel_path}::{func_name}"

    # Get parameters
    params = []
    params_node = node.child_by_field_name("parameters")
    if params_node:
        for p in params_node.children:
            if p.type in ("identifier", "typed_parameter", "default_parameter"):
                params.append(_get_node_text(p, source))

    # Get return type
    return_type = None
    ret_node = node.child_by_field_name("return_type")
    if ret_node:
        return_type = _get_node_text(ret_node, source)

    # Get decorators
    decorators = _extract_decorators(node, source)

    # Get docstring
    docstring = _extract_python_docstring(node, source)

    func_node = GraphNode(
        node_id=func_id,
        node_type=func_type,
        name=func_name,
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language="python",
        metadata={
            "parameters": params[:10],  # Cap for size
            "return_type": return_type,
            "decorators": decorators,
            "docstring": docstring[:200] if docstring else None,
            "is_async": any(c.type == "async" for c in node.children if hasattr(c, 'type')),
        },
    )
    graph.add_node(func_node)
    graph.add_edge(GraphEdge(parent_id, func_id, "contains"))

    # Detect function calls inside the body
    body = node.child_by_field_name("body")
    if body:
        _extract_function_calls(body, source, func_id, rel_path, graph)


def _parse_python_import(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    file_id: str,
    graph: CodeKnowledgeGraph,
):
    import_text = _get_node_text(node, source)
    # Create import node
    import_id = f"import::{rel_path}::{node.start_point[0]}"
    import_node = GraphNode(
        node_id=import_id,
        node_type="import",
        name=import_text.strip(),
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language="python",
        metadata={"raw": import_text.strip()},
    )
    graph.add_node(import_node)
    graph.add_edge(GraphEdge(file_id, import_id, "imports"))


def _extract_python_docstring(node: tree_sitter.Node, source: bytes) -> Optional[str]:
    """Extract the docstring from a class or function node."""
    body = node.child_by_field_name("body")
    if not body or len(body.children) == 0:
        return None
    first_stmt = body.children[0]
    if first_stmt.type == "expression_statement":
        expr = first_stmt.children[0] if first_stmt.children else None
        if expr and expr.type == "string":
            text = _get_node_text(expr, source)
            # Strip triple quotes
            for q in ('"""', "'''"):
                if text.startswith(q) and text.endswith(q):
                    return text[3:-3].strip()
            return text.strip("'\"").strip()
    return None


def _extract_decorators(node: tree_sitter.Node, source: bytes) -> List[str]:
    """Extract decorator names from a node's parent."""
    decorators = []
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                decorators.append(_get_node_text(child, source).lstrip("@").strip())
    return decorators


def _extract_function_calls(
    body_node: tree_sitter.Node,
    source: bytes,
    caller_id: str,
    rel_path: str,
    graph: CodeKnowledgeGraph,
):
    """Recursively find function call expressions in a body."""
    calls_found = set()

    def _walk(node):
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func:
                call_name = _get_node_text(func, source)
                # Keep only simple names, skip very long chains
                if len(call_name) < 100:
                    calls_found.add(call_name)
        for child in node.children:
            _walk(child)

    _walk(body_node)

    for call_name in list(calls_found)[:20]:  # Cap at 20 calls per function
        graph.add_edge(GraphEdge(
            caller_id,
            f"callable::*::{call_name}",
            "calls",
            {"unresolved": True, "call_name": call_name},
        ))


# ---------------------------------------------------------------------------
#  JavaScript / TypeScript Parsing
# ---------------------------------------------------------------------------

def parse_js_ts_file(
    file_path: str,
    relative_path: str,
    source: bytes,
    language: tree_sitter.Language,
    lang_name: str,
    graph: CodeKnowledgeGraph,
):
    """Parse a JavaScript or TypeScript file."""
    parser = tree_sitter.Parser(language)
    tree = parser.parse(source)
    root = tree.root_node

    file_id = f"file::{relative_path}"
    file_node = GraphNode(
        node_id=file_id,
        node_type="file",
        name=os.path.basename(relative_path),
        file_path=relative_path,
        start_line=1,
        end_line=root.end_point[0] + 1,
        language=lang_name,
    )
    graph.add_node(file_node)

    _walk_js_node(root, source, relative_path, file_id, lang_name, graph)


def _walk_js_node(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    lang_name: str,
    graph: CodeKnowledgeGraph,
):
    """Recursively walk JS/TS AST for classes, functions, imports."""
    for child in node.children:
        if child.type == "class_declaration":
            _parse_js_class(child, source, rel_path, parent_id, lang_name, graph)

        elif child.type in (
            "function_declaration",
            "generator_function_declaration",
        ):
            _parse_js_function(child, source, rel_path, parent_id, lang_name, graph)

        elif child.type == "lexical_declaration":
            # const Foo = () => {} or const Foo = function() {}
            for decl in child.children:
                if decl.type == "variable_declarator":
                    value = decl.child_by_field_name("value")
                    if value and value.type in ("arrow_function", "function"):
                        name_node = decl.child_by_field_name("name")
                        if name_node:
                            _parse_js_arrow_or_func(
                                name_node, value, source, rel_path,
                                parent_id, lang_name, graph,
                            )

        elif child.type == "export_statement":
            # Recurse into exported declarations
            _walk_js_node(child, source, rel_path, parent_id, lang_name, graph)

        elif child.type in ("import_statement", "import_declaration"):
            _parse_js_import(child, source, rel_path, parent_id, graph, lang_name)


def _parse_js_class(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    lang_name: str,
    graph: CodeKnowledgeGraph,
):
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    class_name = _get_node_text(name_node, source)
    class_id = f"class::{rel_path}::{class_name}"

    # Superclass
    superclass = None
    heritage = node.child_by_field_name("heritage") or node.child_by_field_name("superclass")
    if heritage:
        superclass = _get_node_text(heritage, source)

    graph.add_node(GraphNode(
        node_id=class_id,
        node_type="class",
        name=class_name,
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language=lang_name,
        metadata={"superclass": superclass},
    ))
    graph.add_edge(GraphEdge(parent_id, class_id, "contains"))

    # Parse methods inside class body
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "method_definition":
                mname_node = child.child_by_field_name("name")
                if mname_node:
                    method_name = _get_node_text(mname_node, source)
                    method_id = f"method::{rel_path}::{class_name}::{method_name}"
                    graph.add_node(GraphNode(
                        node_id=method_id,
                        node_type="method",
                        name=method_name,
                        file_path=rel_path,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        language=lang_name,
                    ))
                    graph.add_edge(GraphEdge(class_id, method_id, "contains"))


def _parse_js_function(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    lang_name: str,
    graph: CodeKnowledgeGraph,
):
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    func_name = _get_node_text(name_node, source)
    func_id = f"function::{rel_path}::{func_name}"

    params = []
    params_node = node.child_by_field_name("parameters")
    if params_node:
        for p in params_node.children:
            if p.type not in ("(", ")", ","):
                params.append(_get_node_text(p, source))

    graph.add_node(GraphNode(
        node_id=func_id,
        node_type="function",
        name=func_name,
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language=lang_name,
        metadata={"parameters": params[:10]},
    ))
    graph.add_edge(GraphEdge(parent_id, func_id, "contains"))


def _parse_js_arrow_or_func(
    name_node: tree_sitter.Node,
    value_node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    parent_id: str,
    lang_name: str,
    graph: CodeKnowledgeGraph,
):
    func_name = _get_node_text(name_node, source)
    func_id = f"function::{rel_path}::{func_name}"

    graph.add_node(GraphNode(
        node_id=func_id,
        node_type="function",
        name=func_name,
        file_path=rel_path,
        start_line=value_node.start_point[0] + 1,
        end_line=value_node.end_point[0] + 1,
        language=lang_name,
    ))
    graph.add_edge(GraphEdge(parent_id, func_id, "contains"))


def _parse_js_import(
    node: tree_sitter.Node,
    source: bytes,
    rel_path: str,
    file_id: str,
    graph: CodeKnowledgeGraph,
    lang_name: str,
):
    import_text = _get_node_text(node, source).strip()
    import_id = f"import::{rel_path}::{node.start_point[0]}"
    graph.add_node(GraphNode(
        node_id=import_id,
        node_type="import",
        name=import_text[:120],
        file_path=rel_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language=lang_name,
        metadata={"raw": import_text},
    ))
    graph.add_edge(GraphEdge(file_id, import_id, "imports"))


# ---------------------------------------------------------------------------
#  Dependency File Parsing (package.json, requirements.txt, etc.)
# ---------------------------------------------------------------------------

def parse_dependency_files(repo_path: str, graph: CodeKnowledgeGraph):
    """Parse package.json, requirements.txt etc. for project-level dependencies."""
    # package.json
    pkg_json_path = os.path.join(repo_path, "package.json")
    if os.path.exists(pkg_json_path):
        try:
            with open(pkg_json_path, "r") as f:
                pkg = json.load(f)
            deps = list((pkg.get("dependencies") or {}).keys())
            dev_deps = list((pkg.get("devDependencies") or {}).keys())
            graph.repo_summary["npm_dependencies"] = deps
            graph.repo_summary["npm_dev_dependencies"] = dev_deps
            graph.repo_summary["project_name"] = pkg.get("name", "")
            graph.repo_summary["project_version"] = pkg.get("version", "")
        except Exception as e:
            logger.warning(f"Error parsing package.json: {e}")

    # requirements.txt
    req_path = os.path.join(repo_path, "requirements.txt")
    if os.path.exists(req_path):
        try:
            with open(req_path, "r") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            graph.repo_summary["python_requirements"] = lines
        except Exception as e:
            logger.warning(f"Error parsing requirements.txt: {e}")

    # README
    for readme_name in ("README.md", "readme.md", "README.rst", "README"):
        readme_path = os.path.join(repo_path, readme_name)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", errors="replace") as f:
                    content = f.read(5000)  # First 5KB
                graph.repo_summary["readme_excerpt"] = content
            except Exception:
                pass
            break


# ---------------------------------------------------------------------------
#  Main Pipeline: Build Knowledge Graph
# ---------------------------------------------------------------------------

def build_knowledge_graph(
    repo_path: str,
    repo_url: Optional[str] = None,
) -> CodeKnowledgeGraph:
    """
    Build a complete knowledge graph from a local repository path.

    Args:
        repo_path: Local path to the repository
        repo_url: Optional URL for metadata

    Returns:
        CodeKnowledgeGraph with all nodes, edges, and file contents
    """
    graph = CodeKnowledgeGraph()
    graph.repo_summary["repo_url"] = repo_url or ""
    graph.repo_summary["repo_path"] = repo_path

    # 1. Discover files
    files = discover_files(repo_path)
    logger.info(f"Discovered {len(files)} parseable source files")
    graph.repo_summary["total_source_files"] = len(files)

    # 2. Parse dependency files
    parse_dependency_files(repo_path, graph)

    # 3. Parse each source file
    parsed_count = 0
    errors = []
    for file_info in files:
        try:
            with open(file_info["path"], "rb") as f:
                source = f.read()

            # Store file content for later snippet retrieval
            try:
                text_content = source.decode("utf-8", errors="replace")
                graph.file_contents[file_info["relative_path"]] = text_content
            except Exception:
                pass

            ext = file_info["extension"]
            lang = EXTENSION_LANGUAGE_MAP.get(ext)
            if not lang:
                continue

            if ext == ".py":
                parse_python_file(
                    file_info["path"],
                    file_info["relative_path"],
                    source,
                    graph,
                )
            else:
                lang_name = file_info["language"]
                parse_js_ts_file(
                    file_info["path"],
                    file_info["relative_path"],
                    source,
                    lang,
                    lang_name,
                    graph,
                )
            parsed_count += 1

        except Exception as e:
            errors.append({"file": file_info["relative_path"], "error": str(e)})
            logger.warning(f"Error parsing {file_info['relative_path']}: {e}")

    logger.info(f"Parsed {parsed_count}/{len(files)} files. Errors: {len(errors)}")
    graph.repo_summary["parsed_files"] = parsed_count
    graph.repo_summary["parse_errors"] = len(errors)

    return graph


# ---------------------------------------------------------------------------
#  Public API: Full pipeline from repo URL
# ---------------------------------------------------------------------------

async def index_repository(
    repo_url: str,
    token: Optional[str] = None,
    branch: str = "main",
) -> Tuple[CodeKnowledgeGraph, str]:
    """
    Full pipeline: clone repo → parse AST → build knowledge graph.

    Returns:
        (CodeKnowledgeGraph, repo_local_path)
    """
    repo_path = clone_repository(repo_url, token=token, branch=branch)
    graph = build_knowledge_graph(repo_path, repo_url=repo_url)
    return graph, repo_path


def generate_graph_text_for_rag(graph: CodeKnowledgeGraph) -> List[str]:
    """
    Convert the knowledge graph into text chunks suitable for
    insertion into LightRAG. Each chunk describes a code entity
    and its relationships.
    """
    chunks = []

    # 1. Repo summary chunk
    summary_lines = ["REPOSITORY OVERVIEW"]
    if graph.repo_summary.get("repo_url"):
        summary_lines.append(f"URL: {graph.repo_summary['repo_url']}")
    if graph.repo_summary.get("project_name"):
        summary_lines.append(f"Project: {graph.repo_summary['project_name']}")
    stats = graph.stats()
    summary_lines.append(f"Files: {stats['total_files']}")
    summary_lines.append(f"Languages: {', '.join(stats['languages'])}")
    if graph.repo_summary.get("npm_dependencies"):
        summary_lines.append(f"NPM deps: {', '.join(graph.repo_summary['npm_dependencies'][:20])}")
    if graph.repo_summary.get("python_requirements"):
        summary_lines.append(f"Python deps: {', '.join(graph.repo_summary['python_requirements'][:20])}")
    if graph.repo_summary.get("readme_excerpt"):
        summary_lines.append(f"\nREADME:\n{graph.repo_summary['readme_excerpt'][:2000]}")
    chunks.append("\n".join(summary_lines))

    # 2. Per-file chunks with structure
    file_nodes = [n for n in graph.nodes.values() if n.node_type == "file"]
    for file_node in file_nodes:
        file_lines = [f"FILE: {file_node.file_path} ({file_node.language})"]
        file_lines.append(f"Lines: {file_node.start_line}-{file_node.end_line}")

        # Get children (classes, functions, imports)
        children = graph.get_edges_from(file_node.node_id)
        classes = []
        functions = []
        imports = []
        for edge in children:
            child = graph.get_node(edge.target_id)
            if not child:
                continue
            if child.node_type == "class":
                classes.append(child)
            elif child.node_type == "function":
                functions.append(child)
            elif child.node_type == "import":
                imports.append(child)

        if imports:
            file_lines.append(f"\nImports: {len(imports)}")
            for imp in imports[:10]:
                file_lines.append(f"  - {imp.name[:80]}")

        if classes:
            file_lines.append(f"\nClasses:")
            for cls in classes:
                sc = cls.metadata.get("superclasses") or cls.metadata.get("superclass")
                inherit = f" extends {sc}" if sc else ""
                file_lines.append(f"  class {cls.name}{inherit} (L{cls.start_line}-{cls.end_line})")
                if cls.metadata.get("docstring"):
                    file_lines.append(f"    \"{cls.metadata['docstring']}\"")
                # Methods
                methods = graph.get_edges_from(cls.node_id)
                for m_edge in methods:
                    method = graph.get_node(m_edge.target_id)
                    if method and method.node_type == "method":
                        params = ", ".join(method.metadata.get("parameters", [])[:5])
                        file_lines.append(f"    def {method.name}({params}) L{method.start_line}-{method.end_line}")

        if functions:
            file_lines.append(f"\nFunctions:")
            for fn in functions:
                params = ", ".join(fn.metadata.get("parameters", [])[:5])
                async_prefix = "async " if fn.metadata.get("is_async") else ""
                file_lines.append(f"  {async_prefix}def {fn.name}({params}) L{fn.start_line}-{fn.end_line}")
                if fn.metadata.get("docstring"):
                    file_lines.append(f"    \"{fn.metadata['docstring']}\"")
                if fn.metadata.get("decorators"):
                    for d in fn.metadata["decorators"]:
                        file_lines.append(f"    @{d}")

        # Include actual source code (trimmed)
        content = graph.file_contents.get(file_node.file_path, "")
        if content:
            # For large files, include first 200 lines
            content_lines = content.split("\n")
            if len(content_lines) > 200:
                code_text = "\n".join(content_lines[:200]) + f"\n... ({len(content_lines) - 200} more lines)"
            else:
                code_text = content
            file_lines.append(f"\nSOURCE CODE:\n```\n{code_text}\n```")

        chunks.append("\n".join(file_lines))

    return chunks
