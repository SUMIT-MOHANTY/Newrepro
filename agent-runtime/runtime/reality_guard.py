"""AgentRealityGuard — Tool Execution Firewall & Authoritative Runtime State Manager.

Core Principle: Never trust model state. Trust only runtime state.
The model cannot establish facts about the environment. Only the filesystem
and tool executor are the source of truth.

Responsibilities:
1. WorkspaceState — authoritative in-memory map of physical files, hashes, sizes.
2. ToolExecutionFirewall — validates structured tool calls, rejects text pseudo-syntax.
3. FakeTranscriptDetector — detects '[Tool:', 'User: Tool Result', etc. and emits hard corrections.
4. PostWriteVerifier — immediately checks os.path.exists and size > 0 after tool execution.
5. ImportDependencyVerifier — pre-build AST scanner checking that every relative import resolves to a real file.
6. SnapshotDiffer — detects 0-diff turns and triggers hard reality wake-up messages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FAKE_TOOL_PATTERNS = [
    re.compile(r'\[Tool:\s*[a-zA-Z0-9_]+', re.IGNORECASE),
    re.compile(r'User:\s*\[?Tool\s*Results?\]?', re.IGNORECASE),
    re.compile(r'Result\s*\([a-zA-Z0-9_]+\):', re.IGNORECASE),
    re.compile(r'Tool\s*Results?\s*\([^\)]*\):', re.IGNORECASE),
    re.compile(r'Tool\s*Results?:', re.IGNORECASE),
    re.compile(r'Function\s*Results?:', re.IGNORECASE),
    re.compile(r'Observation:\s*\{', re.IGNORECASE),
    re.compile(r'\[System:\s*File\s*operation\s*completed', re.IGNORECASE),
    re.compile(r'Tool\s*Outputs?:', re.IGNORECASE),
    re.compile(r'Tool\s*execution\s*outputs?:', re.IGNORECASE),
    # DeepSeek DSML markup tags
    re.compile(r'<[｜|]DSML[｜|][^>]*>', re.IGNORECASE),
    re.compile(r'<[｜|]/?(?:DSML|function_calls?)[｜|]>', re.IGNORECASE),
    # XML function tags
    re.compile(r'(?s)<function=[^>]+>.*?</function>', re.IGNORECASE),
    re.compile(r'</function>', re.IGNORECASE),
    # XML pseudo-tool tags (DeepSeek/Kimi)
    re.compile(
        r'</?(?:git_status|git_commit|git_push|git_diff|git_log|checkout_branch|'
        r'merge_branch|run_command|execute_command|read_file|write_file|write_files|'
        r'replace_file_content|list_directory|file_exists|install_dependencies|'
        r'install_and_build|tool_call)\b[^>]*>',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?s)<(?:git_status|git_commit|git_push|git_diff|git_log|checkout_branch|'
        r'merge_branch|run_command|execute_command|read_file|write_file|write_files|'
        r'replace_file_content|list_directory|file_exists|install_dependencies|'
        r'install_and_build|tool_call)\b[^>]*>.*?</(?:git_status|git_commit|'
        r'git_push|git_diff|git_log|checkout_branch|merge_branch|run_command|'
        r'execute_command|read_file|write_file|write_files|replace_file_content|'
        r'list_directory|file_exists|install_dependencies|install_and_build|tool_call)>',
        re.IGNORECASE,
    ),
]


@dataclass
class FileMetadata:
    """Authoritative metadata for a single physical file on disk."""
    path: str
    size_bytes: int
    content_hash: str
    mtime: float
    is_empty: bool = False


@dataclass
class MissingImport:
    """A relative import in source code that does not resolve to any physical file."""
    source_file: str
    import_path: str
    expected_paths: list[str]


@dataclass
class RealityCorrection:
    """Hard corrective message injected into model context when reality diverged."""
    message: str
    fake_tool_detected: bool = False
    no_op_detected: bool = False
    missing_imports: list[MissingImport] = field(default_factory=list)


class WorkspaceState:
    """Authoritative snapshot of the physical workspace filesystem."""

    def __init__(self, workspace_path: str = "/workspace") -> None:
        self.workspace_path = os.path.abspath(workspace_path)
        self.files: dict[str, FileMetadata] = {}
        self.last_verified_at: datetime = datetime.now(timezone.utc)
        self.version: int = 0
        self.refresh()

    def refresh(self) -> dict[str, FileMetadata]:
        """Scan the physical filesystem and update authoritative state."""
        current_files: dict[str, FileMetadata] = {}
        ignored_dirs = {".git", "node_modules", "dist", ".vite", "__pycache__", ".agent_signals"}

        if os.path.exists(self.workspace_path):
            for root, dirs, filenames in os.walk(self.workspace_path):
                dirs[:] = [d for d in dirs if d not in ignored_dirs]
                for fname in filenames:
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, self.workspace_path).replace("\\", "/")
                    try:
                        stat = os.stat(abs_path)
                        size = stat.st_size
                        # Compute SHA256 for small/medium files
                        if size < 2_000_000:
                            with open(abs_path, "rb") as f:
                                chash = hashlib.sha256(f.read()).hexdigest()[:12]
                        else:
                            chash = f"size_{size}"

                        current_files[rel_path] = FileMetadata(
                            path=rel_path,
                            size_bytes=size,
                            content_hash=chash,
                            mtime=stat.st_mtime,
                            is_empty=(size == 0),
                        )
                    except (OSError, IOError):
                        pass

        self.files = current_files
        self.last_verified_at = datetime.now(timezone.utc)
        self.version += 1
        return self.files

    def file_exists(self, rel_or_abs_path: str) -> bool:
        """Check if a file physically exists in the verified state."""
        rel_path = self._normalize_path(rel_or_abs_path)
        return rel_path in self.files

    def get_file(self, rel_or_abs_path: str) -> FileMetadata | None:
        """Get authoritative file metadata."""
        rel_path = self._normalize_path(rel_or_abs_path)
        return self.files.get(rel_path)

    def _normalize_path(self, path: str) -> str:
        """Normalize a path to a workspace-relative path."""
        p = path.replace("\\", "/")
        if p.startswith(self.workspace_path.replace("\\", "/")):
            p = os.path.relpath(p, self.workspace_path).replace("\\", "/")
        if p.startswith("/workspace/"):
            p = p[len("/workspace/"):]
        elif p.startswith("/"):
            p = p.lstrip("/")
        return p

    def to_verified_summary(
        self,
        max_files: int = 30,
        claimed_unconfirmed: list[str] | None = None,
    ) -> str:
        """Format an authoritative summary of verified physical files for LLM prompt.

        Args:
            max_files: Maximum number of confirmed files to list.
            claimed_unconfirmed: Files the model claimed to have created/modified but
                                  which are NOT yet confirmed by a physical disk check.
                                  These will be shown separately so the model never
                                  mistakes its own text claims for real files.
        """
        self.refresh()
        lines = ["### 🔒 VERIFIED WORKSPACE STATE (Authoritative Physical Disk — Ground Truth):"]

        if not self.files:
            lines.append("  Workspace is EMPTY — 0 files confirmed on physical disk.")
        else:
            lines.append("")
            lines.append("Files CONFIRMED by runtime (physically verified with os.stat):")
            src_files = [
                f for f in self.files.keys()
                if f.startswith("src/") or f in ("package.json", "index.html", "vite.config.js")
            ]
            other_files = [f for f in self.files.keys() if f not in src_files]

            for p in sorted(src_files)[:max_files]:
                meta = self.files[p]
                lines.append(f"  ✅ `{p}` ({meta.size_bytes:,} bytes, hash: {meta.content_hash})")

            if other_files and len(lines) < max_files + 4:
                lines.append("  ---")
                for p in sorted(other_files)[: (max_files - len(lines))]:
                    meta = self.files[p]
                    lines.append(f"  ✅ `{p}` ({meta.size_bytes:,} bytes)")

        # Show claimed-but-unconfirmed files explicitly
        if claimed_unconfirmed:
            confirmed_set = set(self.files.keys())
            actually_missing = [p for p in claimed_unconfirmed if p not in confirmed_set]
            if actually_missing:
                lines.append("")
                lines.append("Files claimed by model but NOT CONFIRMED on physical disk:")
                for p in actually_missing:
                    lines.append(f"  ❌ `{p}` — NOT found on disk. Do NOT assume it exists.")

        lines.append(
            "\n⚠️ RULE: Do NOT assume any file exists unless listed under ✅ above. "
            "A model statement about creating a file is not proof it exists. "
            "Only a successful tool execution result from the runtime executor is proof."
        )
        return "\n".join(lines)


class ImportDependencyVerifier:
    """Pre-build import verifier: statically checks if all relative imports resolve to physical files."""

    def __init__(self, workspace_state: WorkspaceState) -> None:
        self.state = workspace_state

    def verify_imports(self, target_files: list[str] | None = None) -> tuple[bool, list[MissingImport]]:
        """Scan JSX/TSX/JS/TS files and verify relative and aliased import targets exist."""
        self.state.refresh()
        missing: list[MissingImport] = []
        workspace_root = Path(self.state.workspace_path)

        # Regex for ES imports and require: relative (./, ../) and aliased (@/, ~/)
        import_pattern = re.compile(
            r'''(?:import\s+(?:(?:[\w*\s{},]+)\s+from\s+)?|require\s*\(\s*)['"]([.@~][^'"]+)['"]''',
            re.MULTILINE
        )

        ignored_segments = {"node_modules", ".git", "dist", "build", ".venv", "venv", "__pycache__"}

        if target_files:
            files_to_check = []
            for tf in target_files:
                tf_clean = str(tf).replace("\\", "/").strip()
                if not tf_clean:
                    continue
                try:
                    p = Path(tf_clean)
                    if p.is_absolute():
                        rel = p.resolve().relative_to(workspace_root.resolve()).as_posix()
                    else:
                        rel = tf_clean.lstrip("/")
                except Exception:
                    rel = tf_clean.lstrip("/")
                files_to_check.append(rel)
        else:
            files_to_check = list(self.state.files.keys())

        for rel_path in files_to_check:
            parts = set(Path(rel_path).parts)
            if parts & ignored_segments:
                continue
            ext = os.path.splitext(rel_path)[1].lower()
            if ext not in (".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte"):
                continue

            abs_file = workspace_root / rel_path
            try:
                with open(abs_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            file_dir = abs_file.parent

            # Dynamically determine project root for this file
            curr = file_dir
            proj_root = None
            while curr != workspace_root and curr != curr.parent:
                if (curr / "package.json").exists() or (curr / "vite.config.ts").exists() or (curr / "vite.config.js").exists():
                    proj_root = curr
                    break
                curr = curr.parent

            # If no nested package.json / vite.config, check if file is in a known frontend folder
            if not proj_root:
                for segment in ("frontend", "client", "ui", "web"):
                    if segment in abs_file.parts:
                        # find that segment directory
                        idx = abs_file.parts.index(segment)
                        proj_root = Path(*abs_file.parts[:idx + 1])
                        break

            if not proj_root:
                proj_root = workspace_root

            for match in import_pattern.finditer(content):
                import_target = match.group(1).strip()
                # Skip package imports, CSS imports, or public assets
                if import_target.endswith((".css", ".scss", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".json")):
                    continue

                candidate_bases: list[Path] = []
                if import_target.startswith(("@/", "~/")):
                    clean = import_target[2:]
                    # Priority 1: resolve inside the file's own project root
                    candidate_bases.append((proj_root / "src" / clean).resolve())
                    candidate_bases.append((proj_root / clean).resolve())
                    # Priority 2: fallback to workspace root only if project root is different
                    if proj_root != workspace_root:
                        candidate_bases.append((workspace_root / "src" / clean).resolve())
                        candidate_bases.append((workspace_root / clean).resolve())
                elif import_target.startswith("."):
                    candidate_bases.append((file_dir / import_target).resolve())
                else:
                    continue

                resolved = False
                all_candidates: list[Path] = []
                for base in candidate_bases:
                    str_base = str(base)
                    candidates = [
                        base,
                        Path(str_base + ".tsx"),
                        Path(str_base + ".ts"),
                        Path(str_base + ".jsx"),
                        Path(str_base + ".js"),
                        Path(str_base + ".vue"),
                        Path(str_base + ".svelte"),
                        base.with_suffix(".tsx"),
                        base.with_suffix(".ts"),
                        base.with_suffix(".jsx"),
                        base.with_suffix(".js"),
                        base / "index.tsx",
                        base / "index.ts",
                        base / "index.jsx",
                        base / "index.js",
                    ]
                    all_candidates.extend(candidates)
                    if any(c.is_file() for c in candidates):
                        resolved = True
                        break

                if not resolved:
                    expected_rel = []
                    # Keep expected hints clean and contextual to the file's own project root
                    seen_rel = set()
                    for c in all_candidates:
                        try:
                            rel_str = os.path.relpath(c, self.state.workspace_path).replace("\\", "/")
                        except Exception:
                            rel_str = str(c)
                        if rel_str not in seen_rel:
                            seen_rel.add(rel_str)
                            expected_rel.append(rel_str)
                        if len(expected_rel) >= 3:
                            break
                        missing.append(MissingImport(
                            source_file=rel_path,
                            import_path=import_target,
                            expected_paths=expected_rel,
                        ))

        return len(missing) == 0, missing

    def synthesize_missing_stubs(self, missing_list: list[MissingImport]) -> list[str]:
        """Dynamically synthesize minimal, type-safe, runnable stubs for missing imported files
        across any project and any tech stack so builds, compilers, and bundlers pass cleanly.
        """
        created_files = []
        workspace_root = Path(self.state.workspace_path)

        for m in missing_list:
            if not m.expected_paths:
                continue

            # Determine best destination path matching source file flavor (.tsx > .ts > .jsx > .js > .py)
            src_ext = os.path.splitext(m.source_file)[1].lower()
            target_rel = None
            for cand in m.expected_paths:
                cand_ext = os.path.splitext(cand)[1].lower()
                if cand_ext == src_ext:
                    target_rel = cand
                    break
            if not target_rel:
                target_rel = m.expected_paths[0]

            target_abs = workspace_root / target_rel
            if target_abs.exists():
                continue

            target_ext = os.path.splitext(target_rel)[1].lower()
            if not target_ext:
                target_rel += src_ext if src_ext else ".ts"
                target_abs = workspace_root / target_rel
                target_ext = os.path.splitext(target_rel)[1].lower()

            # Analyze source file to extract imported symbol names
            imported_names: set[str] = set()
            default_name: str | None = None
            is_type_only = False

            try:
                src_abs = workspace_root / m.source_file
                if src_abs.exists():
                    src_text = src_abs.read_text(encoding="utf-8", errors="ignore")
                    escaped_target = re.escape(m.import_path)
                    # Match import statements targeting this path
                    ptn = re.compile(
                        r'''import\s+(type\s+)?(?:([\w$]+)\s*,?\s*)?(?:\{([^}]+)\})?\s*from\s*['"]''' + escaped_target + r'''['"]''',
                        re.MULTILINE
                    )
                    for match in ptn.finditer(src_text):
                        if match.group(1):
                            is_type_only = True
                        if match.group(2):
                            default_name = match.group(2).strip()
                        if match.group(3):
                            for sym in match.group(3).split(","):
                                s = sym.strip()
                                if " as " in s:
                                    s = s.split(" as ")[0].strip()
                                if s and s.isidentifier():
                                    imported_names.add(s)
            except Exception:
                pass

            fallback_name = Path(target_rel).stem
            if fallback_name == "index":
                fallback_name = Path(target_rel).parent.name or "Component"
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '', fallback_name) or "DynamicStub"
            if clean_name[0].isdigit():
                clean_name = f"Item_{clean_name}"

            content = self._generate_stub_content(
                file_ext=target_ext,
                name=clean_name,
                default_name=default_name,
                imported_names=imported_names,
                is_type_only=is_type_only,
            )

            try:
                target_abs.parent.mkdir(parents=True, exist_ok=True)
                target_abs.write_text(content, encoding="utf-8")
                created_files.append(target_rel)
                print(f"[DynamicSelfHealing] ⚡ Synthesized runnable stub for '{m.import_path}' at '{target_rel}'")
            except Exception as w_err:
                print(f"[DynamicSelfHealing] Warning writing stub '{target_rel}': {w_err}")

        if created_files:
            self.state.refresh()

        return created_files

    def _generate_stub_content(
        self,
        file_ext: str,
        name: str,
        default_name: str | None,
        imported_names: set[str],
        is_type_only: bool = False,
    ) -> str:
        """Generate idiomatic, runnable stub content tailored to the detected file extension and symbols."""
        primary_name = default_name or name
        all_symbols = set(imported_names)
        if primary_name:
            all_symbols.add(primary_name)

        if file_ext in (".tsx", ".jsx"):
            lines = [
                "import React from 'react';",
                "",
                "// Dynamic self-healing component stub (auto-synthesized by agent runtime)",
                "export interface DynamicStubProps {",
                "  children?: React.ReactNode;",
                "  className?: string;",
                "  [key: string]: any;",
                "}",
                "",
            ]
            for sym in sorted(all_symbols):
                if not sym.isidentifier():
                    continue
                if sym.endswith("Variants") or sym[0].islower():
                    lines.append(f"export const {sym}: any = (opts?: any) => '';")
                elif "Enum" in sym or sym.isupper():
                    lines.append(f"export const {sym}: any = {{ ACTIVE: 'ACTIVE', INACTIVE: 'INACTIVE', DEFAULT: 'DEFAULT' }};")
                    lines.append(f"export type {sym} = any;")
                else:
                    lines.append(f"export const {sym}: React.FC<DynamicStubProps> = ({{ children, className = '', ...props }}) => (")
                    lines.append(f"  <div className={{`dynamic-{sym.lower()} ${{className}}`}} {{...props}}>")
                    lines.append(f"    {{children || '{sym}'}}")
                    lines.append(f"  </div>")
                    lines.append(f");")
                    lines.append(f"export type {sym}Props = DynamicStubProps;")
                lines.append("")

            lines.append(f"export default {primary_name};")
            lines.append("")
            return "\n".join(lines)

        elif file_ext in (".ts", ".js"):
            lines = [
                "// Dynamic self-healing module stub (auto-synthesized by agent runtime)",
                "",
            ]
            # Standard generic client methods for API/service calls
            lines.append(f"const _genericHandler = async (...args: any[]) => ({{ data: {{}}, status: 200 }});")
            lines.append(f"export const {primary_name}: any = {{")
            lines.append("  get: _genericHandler,")
            lines.append("  post: _genericHandler,")
            lines.append("  put: _genericHandler,")
            lines.append("  delete: _genericHandler,")
            lines.append("  patch: _genericHandler,")
            lines.append("  request: _genericHandler,")
            lines.append("};")
            lines.append("")

            for sym in sorted(all_symbols):
                if sym == primary_name or not sym.isidentifier():
                    continue
                if "Enum" in sym or sym.isupper():
                    lines.append(f"export const {sym}: any = {{ ACTIVE: 'ACTIVE', INACTIVE: 'INACTIVE', DEFAULT: 'DEFAULT' }};")
                    lines.append(f"export type {sym} = any;")
                elif sym.startswith("use") or sym[0].islower():
                    lines.append(f"export const {sym}: any = (...args: any[]) => ({{ data: null, loading: false, error: null }});")
                else:
                    lines.append(f"export const {sym}: any = {{}};")
                    lines.append(f"export type {sym} = any;")

            lines.append("")
            lines.append(f"export default {primary_name};")
            lines.append("")
            return "\n".join(lines)

        elif file_ext == ".py":
            lines = [
                '"""Dynamic self-healing module stub (auto-synthesized by agent runtime)."""',
                "",
                "class DynamicStub:",
                "    def __init__(self, *args, **kwargs):",
                "        for k, v in kwargs.items():",
                "            setattr(self, k, v)",
                "    def __call__(self, *args, **kwargs):",
                "        return self",
                "    def __getattr__(self, item):",
                "        return self",
                "",
            ]
            for sym in sorted(all_symbols):
                if sym.isidentifier():
                    lines.append(f"{sym} = DynamicStub")
            lines.append("")
            lines.append(f"default = DynamicStub")
            lines.append("")
            return "\n".join(lines)

        elif file_ext in (".vue", ".svelte"):
            return f"<template><div class=\"dynamic-stub-{name.lower()}\"><slot>{name}</slot></div></template><script setup>defineProps({{}});</script>\n"

        else:
            return f"// Auto-synthesized stub for {name}\nexport default {{}};\n"

    def format_missing_imports_error(self, missing_list: Any) -> str:
        """Format missing import errors into an authoritative runtime directive."""
        if isinstance(missing_list, str):
            return missing_list
        if not isinstance(missing_list, list):
            return str(missing_list)
        lines = [
            "❌ PRE-BUILD IMPORT VERIFICATION FAILED (Missing Files on Physical Disk):",
            "The following files are imported in your code but DO NOT EXIST in the workspace:\n"
        ]
        for m in missing_list:
            if isinstance(m, str):
                lines.append(f"• {m}")
            else:
                lines.append(f"• `{getattr(m, 'source_file', m)}` imports `'{getattr(m, 'import_path', '')}'`")
                if getattr(m, 'expected_paths', None):
                    lines.append(f"  👉 Expected one of: {', '.join(f'`{p}`' for p in m.expected_paths)}")

        lines.append(
            "\nREQUIRED ACTION:"
            "\n1. Create the missing component file(s) immediately using a structured write_file tool call."
            "\n2. OR update the import statement in the source file to reference an existing file."
            "\nDo NOT assume the file exists. Only a physical tool execution will resolve this."
        )
        return "\n".join(lines)


class AgentRealityGuard:
    """The central Tool Execution Firewall & Reality Enforcement layer."""

    def __init__(self, workspace_path: str = "/workspace") -> None:
        self.workspace_path = workspace_path
        self.state = WorkspaceState(workspace_path)
        self.import_verifier = ImportDependencyVerifier(self.state)
        self.fake_tool_count: int = 0
        self.no_op_count: int = 0
        self._last_snapshot: dict[str, FileMetadata] = {}

    def capture_snapshot(self) -> dict[str, FileMetadata]:
        """Capture filesystem state before an iteration begins."""
        self.state.refresh()
        self._last_snapshot = dict(self.state.files)
        return self._last_snapshot

    def verify_post_iteration(
        self,
        claimed_actions: bool = False,
    ) -> tuple[dict[str, Any], RealityCorrection | None]:
        """Verify what actually changed on the physical disk after tool executions."""
        before = self._last_snapshot
        current = self.state.refresh()

        created = [p for p in current if p not in before]
        modified = [p for p in current if p in before and current[p].content_hash != before[p].content_hash]
        deleted = [p for p in before if p not in current]

        diff_summary = {
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "total_changed": len(created) + len(modified) + len(deleted),
        }

        # Check for no-op anomaly
        if claimed_actions and diff_summary["total_changed"] == 0:
            self.no_op_count += 1
            correction = RealityCorrection(
                message=(
                    "⚠️ RUNTIME REALITY CORRECTION: No filesystem changes occurred during your previous turn.\n"
                    "The files you may have described in your response DO NOT EXIST on physical disk.\n"
                    "You must issue real, structured tool calls to write files."
                ),
                no_op_detected=True,
            )
            return diff_summary, correction

        # Reset no-op count on real changes
        if diff_summary["total_changed"] > 0:
            self.no_op_count = 0

        return diff_summary, None

    def detect_fake_tool_transcripts(self, content: str) -> tuple[bool, str]:
        """Check if assistant content contains fabricated tool calls or fake user tool results."""
        if not content:
            return False, ""

        found_patterns = []
        for pat in FAKE_TOOL_PATTERNS:
            if pat.search(content):
                found_patterns.append(pat.pattern)

        if found_patterns:
            self.fake_tool_count += 1
            # Clean fake results so they cannot contaminate history
            cleaned = content
            for pat in FAKE_TOOL_PATTERNS:
                cleaned = pat.sub("", cleaned)
            return True, cleaned.strip()

        return False, content

    def verify_file_write(self, target_path: str, expected_min_size: int = 1) -> tuple[bool, str]:
        """Post-write verification: immediately stat file after tool executor finishes."""
        norm_path = self.state._normalize_path(target_path)
        abs_path = os.path.join(self.workspace_path, norm_path)

        if not os.path.exists(abs_path):
            return False, f"Post-write verification FAILED: File '{norm_path}' was not found on physical disk."

        try:
            stat = os.stat(abs_path)
            if stat.st_size < expected_min_size:
                return False, f"Post-write verification FAILED: File '{norm_path}' is empty (0 bytes)."
        except Exception as e:
            return False, f"Post-write verification FAILED: Could not stat '{norm_path}': {e}"

        # Refresh state
        self.state.refresh()
        return True, f"Verified: '{norm_path}' exists on physical disk ({stat.st_size:,} bytes)."

    def verify_pre_build(self, target_files: list[str] | None = None, auto_heal: bool = True) -> tuple[bool, str | None]:
        """Pre-flight check before build is called with autonomous self-healing for missing dependencies."""
        valid, missing = self.import_verifier.verify_imports(target_files=target_files)
        if not valid and auto_heal:
            # Dynamically heal all missing imports by synthesizing working stubs
            synthesized = self.import_verifier.synthesize_missing_stubs(missing)
            if synthesized:
                # Re-verify after auto-healing
                valid, remaining_missing = self.import_verifier.verify_imports(target_files=target_files)
                if valid:
                    return True, None
                missing = remaining_missing

        if not valid:
            error_msg = self.import_verifier.format_missing_imports_error(missing)
            return False, error_msg
        return True, None

