#!/usr/bin/env python3
"""
AI-Powered Self-Healing Agent
Fully dynamic: works with any tech stack via pure AI-driven analysis.
All tunables controlled via environment variables — zero hardcoded assumptions.

ENV VARS (all optional):
  AI_API_KEY / NVIDIA_API_KEY   - LLM provider API key
  AI_API_URL                    - OpenAI-compatible endpoint
  AI_MODEL                      - Model name
  PORT                          - Port the server must bind to (default: 8080)
  MAX_RETRIES                   - Self-healing retry limit (default: 3)
  STARTUP_TIMEOUT               - Seconds to monitor startup (default: 20)
  AI_TIMEOUT                    - Seconds to wait for AI response (default: 60)
  MAX_FILE_SIZE                 - Max bytes per file sent to AI (default: 5000)
  MAX_FILES                     - Max files in AI context (default: 10)
  ERROR_KEYWORDS                - Comma-separated error log signals
  SUCCESS_KEYWORDS              - Comma-separated startup success signals
  SCAN_EXTENSIONS               - Comma-separated file extensions (default: auto)
  PROJECT_VERSIONS_DIR          - Root dir for versioned workspaces (default: /project/versions)
  WORKSPACE_PATH                - Explicit workspace path override
  FALLBACK_RUN_CMD              - Command when no AI key is available
  ERROR_LOG_TAIL                - Chars of error log sent to AI (default: 3000)
  FILE_SNIPPET_CHARS            - Chars per file in AI context (default: 3000)
  MAX_CONTEXT_FILES             - Files included in fix prompt (default: 5)
  POLL_INTERVAL                 - Stdout read loop sleep in seconds (default: 0.05)
  DRAIN_TIMEOUT                 - Extra seconds to drain output after process exits (default: 3.0)
  MAX_ATTEMPTS                  - Hard ceiling on total attempts regardless of fix success (default: MAX_RETRIES * 3)
  BG_READY_TIMEOUT              - Seconds to wait for background process ready signal (default: 30)
  FUZZY_PATCH_THRESHOLD         - difflib match threshold for fuzzy patching (default: 0.85)
"""

import os
import sys
import subprocess
import json
import time
import re
import shutil
import tempfile
import platform
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple
from queue import Queue, Empty
from threading import Thread


# ---------------------------------------------------------------------------
# Centralised configuration — all values from environment, never hardcoded
# ---------------------------------------------------------------------------

@dataclass
class Config:
    api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get('AI_API_KEY')
    )
    api_url: Optional[str] = field(
        default_factory=lambda: os.environ.get('AI_API_URL') or os.environ.get('AI_URL')
    )
    ai_model: Optional[str] = field(
        default_factory=lambda: os.environ.get('AI_MODEL')
    )
    port: str = field(
        default_factory=lambda: os.environ.get('PORT', '8080')
    )
    additional_ports: list = field(
        default_factory=lambda: [p.strip() for p in os.environ.get('ADDITIONAL_PORTS', '').split(',') if p.strip()]
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get('MAX_RETRIES', '3'))
    )
    max_attempts: int = field(
        default_factory=lambda: int(os.environ.get('MAX_ATTEMPTS', str(int(os.environ.get('MAX_RETRIES', '3')) * 3)))
    )
    startup_timeout: int = field(
        default_factory=lambda: int(os.environ.get('STARTUP_TIMEOUT', '20'))
    )
    ai_timeout: int = field(
        default_factory=lambda: int(os.environ.get('AI_TIMEOUT', '120'))
    )
    max_file_size: int = field(
        default_factory=lambda: int(os.environ.get('MAX_FILE_SIZE', '30000'))
    )
    max_files: int = field(
        default_factory=lambda: int(os.environ.get('MAX_FILES', '20'))
    )
    error_keywords: list = field(
        default_factory=lambda: os.environ.get(
            'ERROR_KEYWORDS', 'error,exception,traceback,failed,fatal,panic,crash'
        ).lower().split(',')
    )
    success_keywords: list = field(
        default_factory=lambda: os.environ.get(
            'SUCCESS_KEYWORDS', 'running,listening,started,ready,serving'
        ).lower().split(',')
    )
    scan_extensions: Optional[list] = field(
        default_factory=lambda: (
            [e.strip() for e in os.environ['SCAN_EXTENSIONS'].split(',')]
            if os.environ.get('SCAN_EXTENSIONS') else None
        )
    )
    versions_dir: str = field(
        default_factory=lambda: os.environ.get('PROJECT_VERSIONS_DIR', '/project/versions')
    )
    bg_ready_timeout: float = field(
        default_factory=lambda: float(os.environ.get('BG_READY_TIMEOUT', '30'))
    )
    fallback_run_cmd: str = field(
        default_factory=lambda: os.environ.get('FALLBACK_RUN_CMD', '')
    )
    fuzzy_threshold: float = field(
        default_factory=lambda: float(os.environ.get('FUZZY_PATCH_THRESHOLD', '0.85'))
    )
    user_prompt: str = field(
        default_factory=lambda: os.environ.get('USER_PROMPT', '')
    )
    # State tracking for monitoring
    seen_bind_all: bool = False
    seen_bind_local: bool = False


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AIAgent:
    def __init__(self):
        self.config = Config()
        self.retry_count = 0
        self.os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        self.workspace = self._resolve_workspace()
        self.tools = self._get_installed_tools()
        self.manifest = self._get_manifest_contents()

    # ------------------------------------------------------------------
    # Workspace resolution
    # ------------------------------------------------------------------

    def _resolve_workspace(self) -> str:
        explicit = os.environ.get('WORKSPACE_PATH', os.getcwd())
        if not os.path.isabs(explicit):
            explicit = os.path.abspath(explicit)

        if os.path.exists(explicit) and os.listdir(explicit):
            os.chdir(explicit)
            return explicit

        for env_var in ('CURRENT_VERSION', 'INITIAL_VERSION'):
            version = os.environ.get(env_var)
            if version:
                versioned = os.path.join(self.config.versions_dir, version)
                if os.path.exists(versioned):
                    os.chdir(versioned)
                    return versioned

        if os.path.exists(self.config.versions_dir):
            versions = sorted(os.listdir(self.config.versions_dir))
            if versions:
                latest = os.path.join(self.config.versions_dir, versions[-1])
                os.chdir(latest)
                return latest

        os.chdir(explicit)
        return explicit

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, emoji: str, message: str):
        print(f"{emoji} {message}", flush=True)

    # ------------------------------------------------------------------
    # Core AI call — single reusable method
    # ------------------------------------------------------------------

    # Directories to always skip when scanning
    SKIP_DIRS = frozenset({
        'node_modules', '.git', '__pycache__', 'venv', '.venv', 'dist',
        'build', '.next', '.cache', '.nuxt', '.svelte-kit', 'target',
        'bin', 'obj', '.gradle', '.idea', '.vscode', 'coverage',
        'tmp', 'temp', '.tmp', '.temp', 'vendor', 'bower_components',
    })

    def _get_installed_tools(self) -> str:
        """Dynamically discover all available executables in the system PATH."""
        tools = set()
        path_env = os.environ.get("PATH", "")
        for folder in path_env.split(os.pathsep):
            if not os.path.isdir(folder):
                continue
            try:
                for item in os.listdir(folder):
                    path = os.path.join(folder, item)
                    if os.path.isfile(path) and os.access(path, os.X_OK):
                        tools.add(item)
            except:
                continue
        return ", ".join(sorted(list(tools)))

    def _get_file_tree(self, max_entries: int = 200) -> str:
        """Recursively list all project files as a tree (like `find .`) for full AI context.
        This is critical — without seeing subdirectories (src/, public/, components/),
        the AI cannot understand React/Vue/Angular projects."""
        tree_lines = []
        count = 0
        for root, dirs, fnames in os.walk(self.workspace):
            # Prune skip directories in-place
            dirs[:] = sorted([d for d in dirs if d not in self.SKIP_DIRS])
            for fname in sorted(fnames):
                if count >= max_entries:
                    tree_lines.append(f"... and more files (truncated at {max_entries})")
                    return "\n".join(tree_lines)
                rel = os.path.relpath(os.path.join(root, fname), self.workspace)
                try:
                    size = os.path.getsize(os.path.join(root, fname))
                    tree_lines.append(f"  {rel} ({size} bytes)")
                except OSError:
                    tree_lines.append(f"  {rel}")
                count += 1
        return "\n".join(tree_lines) if tree_lines else "(empty workspace)"

    def _get_manifest_contents(self) -> str:
        """Recursively find and read config/manifest files as metadata context.
        Reads package.json, requirements.txt, Cargo.toml, pom.xml, etc.
        Also reads key source files (index.html, index.js, App.js) for better context."""
        # Config files to always include (any depth)
        PRIORITY_FILES = {
            'package.json', 'requirements.txt', 'Pipfile', 'pyproject.toml',
            'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle', 'Gemfile',
            'composer.json', 'tsconfig.json', 'vite.config.js', 'vite.config.ts',
            'next.config.js', 'next.config.mjs', 'webpack.config.js',
            'babel.config.js', '.babelrc', 'tailwind.config.js',
            'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
            'run.sh', 'start.sh', 'Procfile', 'Makefile',
        }
        # Source entry points to include for structural understanding
        ENTRY_POINT_FILES = {
            'index.html', 'index.js', 'index.jsx', 'index.ts', 'index.tsx',
            'App.js', 'App.jsx', 'App.tsx', 'app.py', 'main.py', 'server.js',
            'app.js', 'main.go', 'main.rs', 'Program.cs',
        }
        manifests = {}
        try:
            for root, dirs, fnames in os.walk(self.workspace):
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
                for fname in fnames:
                    if fname in PRIORITY_FILES or fname in ENTRY_POINT_FILES:
                        fpath = Path(root) / fname
                        rel_path = str(fpath.relative_to(self.workspace))
                        try:
                            size = fpath.stat().st_size
                            if size < 30000:  # Don't read very large files
                                content = fpath.read_text(encoding="utf-8").strip()
                                if content:
                                    # Config files get more space, source files less
                                    limit = 4000 if fname in PRIORITY_FILES else 2000
                                    manifests[rel_path] = content[:limit]
                        except (UnicodeDecodeError, PermissionError, OSError):
                            continue
        except Exception:
            pass
        return json.dumps(manifests, indent=2)

    def _call_ai(self, prompt: str, temperature: float = 0.1) -> Optional[dict]:
        if not self.config.api_key:
            self.log("⚠️", "No AI API key — skipping AI call")
            return None

        provider = os.environ.get('AI_PROVIDER', 'openai').lower().strip()

        try:
            import requests

            if provider == 'bournai':
                headers = {"Content-Type": "application/json"}
                payload = {
                    "agent_id": self.config.api_key,
                    "model": self.config.ai_model or "BournAI",
                    "platform_id": os.environ.get('BOURNAI_PLATFORM_ID', 'DSuite'),
                    "stream": True,
                    "prompt": prompt,
                }
            else:
                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.config.ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }

            is_stream = payload.get("stream", False)
            response = requests.post(
                self.config.api_url,
                headers=headers,
                json=payload,
                stream=is_stream,
                timeout=self.config.ai_timeout,
            )

            if response.status_code != 200:
                self.log("❌", f"AI API error {response.status_code}: {response.text[:300]}")
                return None

            if is_stream:
                content = self._aggregate_stream(response)
            else:
                content = response.json()["choices"][0]["message"]["content"]

            # Primary: parse <vibe-fix> tags (expected format)
            if "<vibe-fix" in content:
                parsed = self._parse_vibe_fix_tags(content)
                if parsed:
                    return parsed
                else:
                    self.log("⚠️", "<vibe-fix> tags found but parsing failed")
                    self.log("📄", f"Response preview (first 1200 chars):\n{content[:1200]}")
            else:
                # Fallback: try JSON extraction (for backward compatibility)
                self.log("⚠️", "No <vibe-fix> tags found, trying JSON extraction")
                parsed_json = self._extract_json_from_response(content)
                if parsed_json:
                    return parsed_json

            # Log the response for debugging
            self.log("❌", "AI response could not be parsed")
            self.log("📄", f"Full response:\n{content}")

        except json.JSONDecodeError as e:
            self.log("❌", f"JSON parse error in AI response: {e}")
            if 'content' in locals():
                self.log("📄", f"Response preview: {content[:500]}")
        except Exception as e:
            self.log("❌", f"AI call failed: {e}")
            import traceback
            self.log("📄", f"Traceback: {traceback.format_exc()}")

        return None

    def _extract_json_from_response(self, content: str) -> Optional[dict]:
        """Extract and parse JSON from AI response with multiple fallback strategies"""
        
        # Strategy 1: JSON in code blocks (most reliable)
        for pattern in (r"```json\s*(\{.*?\})\s*```", r"```json\s*(\[.*?\])\s*```"):
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        
        # Strategy 2: Raw JSON object (only if it looks like valid JSON structure)
        # Must start with { and end with }, and have at least one key-value pair
        match = re.search(r'\{\s*"[^"]+"\s*:', content, re.DOTALL)
        if match:
            # Find the complete JSON object starting from this position
            start_pos = match.start()
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i in range(start_pos, len(content)):
                char = content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Found complete JSON object
                            json_str = content[start_pos:i+1]
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                break
        
        # Strategy 3: Try to find and fix common JSON errors
        # Only attempt this if we see clear JSON structure indicators
        if '{"' in content or '{ "' in content:
            # Remove trailing commas before } or ]
            cleaned = re.sub(r',(\s*[}\]])', r'\1', content)
            
            # Try to extract JSON object from cleaned content
            match = re.search(r'\{\s*"[^"]+"\s*:', cleaned, re.DOTALL)
            if match:
                start_pos = match.start()
                brace_count = 0
                in_string = False
                escape_next = False
                
                for i in range(start_pos, len(cleaned)):
                    char = cleaned[i]
                    
                    if escape_next:
                        escape_next = False
                        continue
                        
                    if char == '\\':
                        escape_next = True
                        continue
                        
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                        
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_str = cleaned[start_pos:i+1]
                                try:
                                    return json.loads(json_str)
                                except json.JSONDecodeError:
                                    break
        
        return None

    def _parse_vibe_fix_tags(self, text: str) -> Optional[dict]:
        """
        Parse a tagged fix response:
        <vibe-fix>
          <diagnosis>...</diagnosis>
          <fix_type>code_patch|code_change|commands</fix_type>
          <confidence>high|medium|low</confidence>
          <fix_details>...</fix_details>
        </vibe-fix>
        """
        try:
            # Quick guard
            if "<vibe-fix" not in text:
                return None

            # Extract outer block
            m_fix = re.search(r"<vibe-fix\b[^>]*>([\s\S]*?)</vibe-fix>", text, re.DOTALL)
            if not m_fix:
                self.log("⚠️", "Found <vibe-fix but no closing </vibe-fix>")
                return None
            block = m_fix.group(1)

            def _tag(tag: str) -> str:
                m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", block, re.DOTALL)
                return m.group(1).strip() if m else ""

            diagnosis = _tag("diagnosis")
            fix_type = _tag("fix_type")
            confidence = _tag("confidence")

            details_block_match = re.search(r"<fix_details>([\s\S]*?)</fix_details>", block, re.DOTALL)
            details_block = details_block_match.group(1) if details_block_match else block

            if not fix_type:
                self.log("⚠️", "No <fix_type> found in <vibe-fix> block")
                return None

            if fix_type == "code_patch":
                file = re.search(r"<file>([\s\S]*?)</file>", details_block, re.DOTALL)
                if not file:
                    self.log("⚠️", "code_patch missing <file> tag")
                    return None
                filepath = file.group(1).strip()
                hunks = []
                for hm in re.finditer(r"<vibe-hunk>([\s\S]*?)</vibe-hunk>", details_block, re.DOTALL):
                    h = hm.group(1)
                    sm = re.search(r"<search>([\s\S]*?)</search>", h, re.DOTALL)
                    rm = re.search(r"<replace>([\s\S]*?)</replace>", h, re.DOTALL)
                    if not sm or not rm:
                        continue
                    search = sm.group(1)
                    replace = rm.group(1)
                    if search.strip() == "":
                        continue
                    hunks.append({"search": search, "replace": replace})

                if not hunks:
                    self.log("⚠️", "code_patch has no valid hunks")
                    return None

                return {
                    "diagnosis": diagnosis,
                    "fix_type": "code_patch",
                    "fix_details": {"file": filepath, "hunks": hunks},
                    "confidence": confidence,
                }

            if fix_type == "code_change":
                file = re.search(r"<file>([\s\S]*?)</file>", details_block, re.DOTALL)
                content_tag = re.search(r"<content>([\s\S]*?)</content>", details_block, re.DOTALL)
                append_tag = re.search(r"<append>([\s\S]*?)</append>", details_block, re.DOTALL)
                if not file or not content_tag:
                    self.log("⚠️", "code_change missing <file> or <content> tag")
                    return None
                append = False
                if append_tag:
                    append = append_tag.group(1).strip().lower() in ("true", "1", "yes")

                return {
                    "diagnosis": diagnosis,
                    "fix_type": "code_change",
                    "fix_details": {"file": file.group(1).strip(), "content": content_tag.group(1), "append": append},
                    "confidence": confidence,
                }

            if fix_type == "commands":
                cmds = []
                for cm in re.finditer(r"<command>([\s\S]*?)</command>", details_block, re.DOTALL):
                    c = cm.group(1).strip()
                    if c:
                        cmds.append(c)
                run_cmd_m = re.search(r"<run_command>([\s\S]*?)</run_command>", details_block, re.DOTALL)
                fix_details = {"commands": cmds}
                if run_cmd_m:
                    fix_details["run_command"] = run_cmd_m.group(1).strip()

                return {
                    "diagnosis": diagnosis,
                    "fix_type": "commands",
                    "fix_details": fix_details,
                    "confidence": confidence,
                }

            # Unknown fix type
            self.log("⚠️", f"Unknown fix_type: {fix_type}")
            return None
            
        except Exception as e:
            self.log("❌", f"Exception parsing <vibe-fix> tags: {e}")
            import traceback
            self.log("📄", f"Traceback: {traceback.format_exc()}")
            return None

    def _aggregate_stream(self, response) -> str:
        """Aggregate SSE stream into a single string. Handles both OpenAI and BournAI formats."""
        provider = os.environ.get('AI_PROVIDER', 'openai').lower().strip()
        content = ""
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
            if line.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(line)
                if provider == 'bournai':
                    for part in chunk.get("content", []):
                        if isinstance(part, dict) and part.get("type") == "text":
                            content += part.get("text", "")
                    if chunk.get("stop_reason") == "end_turn":
                        break
                else:
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        if delta.get("content"):
                            content += delta["content"]
            except json.JSONDecodeError:
                continue
        return content

    # ------------------------------------------------------------------
    # Project file scanner
    # ------------------------------------------------------------------

    def scan_project_files(self) -> dict:
        """Recursively scan project files for AI context.
        Uses os.walk to find ALL source files, not just root-level.
        This is critical for React/Vue/Angular projects where source is in src/."""
        files_content: dict = {}

        for root, dirs, fnames in os.walk(self.workspace):
            # Prune directories we never want to scan
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for fname in sorted(fnames):
                if len(files_content) >= self.config.max_files:
                    return files_content

                fpath = Path(root) / fname

                # Apply extension filter if configured
                if self.config.scan_extensions:
                    if fpath.suffix not in self.config.scan_extensions:
                        continue

                # Skip binary / lock files
                if fname in ('package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
                             'Pipfile.lock', 'poetry.lock', '.DS_Store'):
                    continue

                try:
                    size = fpath.stat().st_size
                    if size > self.config.max_file_size:
                        continue
                    content = fpath.read_text(encoding="utf-8")
                    rel_path = str(fpath.relative_to(self.workspace))
                    files_content[rel_path] = content
                except (UnicodeDecodeError, PermissionError, OSError):
                    pass

        return files_content

    # ------------------------------------------------------------------
    # Execution plan
    # ------------------------------------------------------------------

    def get_ai_execution_plan(self, files: list) -> Optional[dict]:
        """Ask AI for execution plan based on full recursive file analysis.
        Provides the AI with the complete project tree, manifest contents,
        and framework-aware build guidance."""
        if not self.config.api_key:
            if self.config.fallback_run_cmd:
                self.log("📜", f"No AI key, using configured fallback: {self.config.fallback_run_cmd}")
                return {
                    "project_type": "unknown",
                    "processes": [
                        {
                            "name": "fallback-server",
                            "command": self.config.fallback_run_cmd,
                            "type": "primary",
                            "ready_signal": None
                        }
                    ],
                    "success_patterns": self.config.success_keywords,
                    "analysis": "Configured fallback mode (No AI key)",
                }
            
            self.log("❌", "No AI key provided and no fallback command found. Cannot determine execution plan.")
            return None

        self.log("🤖", "AI is analyzing project structure and requirements...")

        # Build a full recursive file tree for proper context
        file_tree = self._get_file_tree(max_entries=200)

        prompt = """You are an expert DevOps engineer. Analyze the project structure below and produce a
complete, working execution plan for this system.

USER INTENT (CRITICAL): [USER_PROMPT]
SYSTEM: [OS_INFO]
INSTALLED TOOLS: [TOOLS]
TARGET PORT: [PORT]
ADDITIONAL PORTS: [ADDITIONAL_PORTS]

═══════════════════════════════════════════
 COMPLETE PROJECT FILE TREE
═══════════════════════════════════════════
[FILE_TREE]

═══════════════════════════════════════════
 KEY FILE CONTENTS (manifests, configs, entry points)
═══════════════════════════════════════════
[MANIFEST]

Return ONLY a raw JSON object (no markdown fences, no extra text):
{
    "project_type": "detected runtime/framework(s)",
    "file_writes": [
        {
            "path": "relative/path/to/file.ext",
            "content": "full file content as a string"
        }
    ],
    "processes": [
        {
            "name": "descriptive name",
            "command": "exact shell command",
            "type": "setup | background | primary",
            "ready_signal": "log substring that means this process is ready (null for setup/primary)"
        }
    ],
    "success_patterns": ["log substrings that confirm the primary server started successfully"],
    "analysis": "one-sentence explanation",
    "nginx_config": "site configuration (server blocks ONLY - no http/events wrapper). MUST listen on port 80 to proxy backends (e.g. 8080) and serve frontends."
}

FILE WRITES (CRITICAL — use instead of echo/cat for creating or updating files):
- file_writes is an array of {path, content} objects. The agent writes each file directly
  from Python — no shell quoting, no bash escaping, no truncation risk.
- Use file_writes for ALL file creation/modification (HTML, CSS, JS, JSON, config files, etc.).
- Setup commands should ONLY be used for: installing packages (npm install, pip3 install),
  building assets (npm run build), chmod, mkdir, or other non-file-write operations.
- NEVER use 'echo', 'cat', 'printf', or shell redirection (>, >>) to write file content
  inside setup commands — it breaks on quotes, backticks, and special characters.
- file_writes entries are applied BEFORE setup commands run.


NGINX GATEWAY RULE:
- If you provide `nginx_config`, do NOT add `nginx` to the `processes` list.
- Use `nginx_config` as the primary gateway on port 80.
- Ensure `nginx_config` contains ONLY `server { ... }` blocks (no `http {` or `events {`).
- Redirect/Proxy internal backend requests from the frontend to their respective background ports (e.g. 8080).

PROCESS TYPES:
- setup      → one-time commands that must complete before anything runs (install deps, build assets, compile code, etc.).
               NEVER use setup commands to write file content — use file_writes instead.
- background → long-running processes that other processes depend on (databases, backend APIs, message queues, etc.).
               Must include a ready_signal so the agent waits for it before starting next steps.
- primary    → exactly ONE entry — the main server that will be monitored and exposed on port [PORT].
               This MUST be the last entry in the array.

═══════════════════════════════════════════
 FRAMEWORK BUILD PATTERNS (CRITICAL)
═══════════════════════════════════════════
IMPORTANT: Many modern web frameworks require a BUILD step before serving.
Do NOT serve source files directly — you MUST build first.

React (create-react-app / react-scripts):
  setup: npm install
  setup: npm run build
  primary: serve -s build -l [PORT]    (serve is pre-installed globally)
  → Serves from build/ directory. NEVER use react-scripts start in production.

React (Vite-based):
  setup: npm install
  setup: npm run build
  primary: serve -s dist -l [PORT]
  → Serves from dist/ directory.

Vue.js:
  setup: npm install
  setup: npm run build
  primary: serve -s dist -l [PORT]

Angular:
  setup: npm install
  setup: npx ng build --configuration production
  primary: serve -s dist/{project-name} -l [PORT]

Svelte / SvelteKit:
  setup: npm install
  setup: npm run build
  primary: serve -s build -l [PORT]   (or node build/index.js for SvelteKit)

Next.js:
  setup: npm install
  setup: npm run build
  primary: npx next start -p [PORT]
  → Next.js has its own server, no need for serve.

Python (Flask/FastAPI/Django):
  setup: pip3 install -r requirements.txt (if exists)
  primary: python3 app.py  OR  uvicorn main:app --host 0.0.0.0 --port [PORT]
  → CRITICAL: Always use 'python3', never 'python' (python command may not exist on the system)

Static HTML/CSS/JS (no package.json):
  primary: serve -l [PORT]
  → serve is pre-installed globally, just point it at the directory.

Node.js Backend (Express/Koa/Fastify):
  setup: npm install
  primary: node server.js  (or whatever the entry point is, with PORT=[PORT])
  → MUST set HOST=0.0.0.0 or bind to 0.0.0.0 explicitly.

Full-Stack (Backend + Frontend in same project):
  setup: npm install (in frontend dir)
  setup: npm run build (in frontend dir)
  setup: pip3 install -r requirements.txt (in backend dir, if Python)
  background: python3 backend/app.py (on port 8000)
  primary: nginx (on port [PORT], reverse proxy to backend + serve frontend build)
  → Use nginx_config to route /api/* to backend and serve static from frontend build dir.

KEY RULE: If package.json exists with a "build" script, you MUST run "npm run build".
NEVER skip the build step for framework-based projects.

ARCHITECTURE DETECTION:
- Analyze the project structure to determine if it's single-tier or multi-tier.
- If multiple services need to run (e.g., separate backend and frontend, or multiple microservices):
  * Use Nginx as a reverse proxy/load balancer for the primary process
  * Run dependent services as background processes on different ports
  * Configure Nginx to route requests appropriately
- If it's a single service, run it directly as the primary process.

NGINX USAGE (when needed):
- Use Nginx when you need to:
  * Serve static files AND proxy API requests
  * Combine multiple services under one port
  * Provide routing, load balancing, or SSL termination
- Nginx config should:
  * Listen on port [PORT]
  * Route requests based on path patterns (e.g., /api/*, /ws/*, etc.)
  * Serve static files from the appropriate directory
  * Proxy dynamic requests to background services
  * Include appropriate headers and error handling
- CRITICAL: nginx_config should ONLY contain server blocks. NEVER include events, http, or worker_processes directives - these belong in the main nginx.conf, not site configs.
- Only include nginx_config if Nginx is actually needed. Set to null otherwise.

CONSTRAINTS:
- Running inside Docker (Ubuntu 22.04, Python3 + Node.js 18 + Nginx + serve pre-installed).
- CRITICAL: Always use 'python3' command, never 'python' (python command does not exist on this system).
- The primary server MUST bind to port [PORT] on ALL interfaces (0.0.0.0).
- Background services can use any available ports (recommend 8000, 8001, 8002, etc.).
- Services should communicate via localhost or environment variables.
- Working directory is /project/workspace.
- Consider the USER INTENT when making architectural decisions.
"""
        
        # Perform replacements on the template
        prompt = prompt.replace("[USER_PROMPT]", str(self.config.user_prompt or "Unknown"))
        prompt = prompt.replace("[OS_INFO]", str(self.os_info))
        prompt = prompt.replace("[TOOLS]", str(self.tools))
        prompt = prompt.replace("[PORT]", str(self.config.port))
        prompt = prompt.replace("[ADDITIONAL_PORTS]", str(", ".join(self.config.additional_ports) or "None"))
        prompt = prompt.replace("[FILE_TREE]", str(file_tree))
        prompt = prompt.replace("[MANIFEST]", str(self.manifest))
        
        result = self._call_ai(prompt, temperature=0.1)
        if result:
            return result

        self.log("❌", "AI could not produce an execution plan")
        return None

    # ------------------------------------------------------------------
    # grep pre-flight — AI decides what regex patterns to search
    # ------------------------------------------------------------------

    def locate_error_files(self, error_log: str) -> list:
        patterns = self._get_ai_search_terms(error_log)
        if not patterns:
            return []

        try:
            combined = '|'.join(patterns)
            result = subprocess.run(
                ['grep', '-rlE', combined, self.workspace],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                matched = []
                for p in result.stdout.strip().splitlines():
                    try:
                        rel = str(Path(p).relative_to(self.workspace))
                        matched.append(rel)
                    except ValueError:
                        matched.append(Path(p).name)
                self.log("🔍", f"AI-directed grep found: {', '.join(matched)}")
                return matched
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return []

    def _get_ai_search_terms(self, error_log: str) -> list:
        prompt = """Analyze this error log. Return ONLY a JSON object with grep regex patterns.

ERROR LOG:
{error_log[-1500:]}

Return ONLY:
{
    "patterns": [
        "regex pattern 1",
        "regex pattern 2",
        "regex pattern 3"
    ]
}

RULES:
- Maximum 5 patterns. Each must be a valid grep -E extended regex.
- Patterns should match filenames, function names, class names, module imports,
  variable names, or any identifier directly related to the error.
- Write broader patterns where useful:
    e.g. "authMiddleware|auth_middleware" to catch naming variants
    e.g. "import.*express|require.*express" to catch the import line
    e.g. "def\\s+handle_request" to match a specific function definition
- Do NOT use generic patterns like "error", "line", "failed", "undefined".
- If nothing meaningful can be extracted, return empty patterns array.
"""
        
        # Simple replacement - no template variables needed for this prompt
        prompt = prompt.replace("{error_log[-1500:]}", error_log[-1500:])
        
        result = self._call_ai(prompt, temperature=0.0)
        if not result:
            return []

        patterns = [p for p in result.get("patterns", []) if p and len(p) > 2]
        self.log("🔍", f"AI regex patterns: {patterns}")
        return patterns

    # ------------------------------------------------------------------
    # Error fix — AI diagnosis with grep-prioritised file context
    # ------------------------------------------------------------------


    def _check_hardcoded_fixes(self, error_log: str) -> Optional[dict]:
        """Check for extremely common errors that have 100% reliable fixes."""
        # Fix for python command not found - use python3 instead
        if "python: command not found" in error_log or "/bin/bash: line 1: python: command not found" in error_log:
            self.log("💡", "Detected 'python' command not found. Switching to 'python3'...")
            return {
                "diagnosis": "python command not found, system uses python3",
                "fix_type": "commands",
                "confidence": "high",
                "fix_details": {
                    "run_command": "python3 app.py"  # Update the run command
                }
            }
        
        # Fix for JSX syntax errors - mismatched tags
        if "Expected closing" in error_log and "tag to match opening" in error_log:
            self.log("💡", "Detected JSX syntax error with mismatched tags. Needs AI fix for proper JSX structure...")
            # Return None to let AI handle the complex JSX fix
            return None
        
        if "ImportError: cannot import name 'url_quote' from 'werkzeug.urls'" in error_log:
            self.log("💡", "Detected Flask/Werkzeug version incompatibility. Applying fix...")
            return {
                "diagnosis": "Flask/Werkzeug version mismatch (url_quote removed in Werkzeug 3.x)",
                "fix_type": "commands",
                "confidence": "high",
                "fix_details": {
                    "commands": ["pip3 install werkzeug==2.2.2"]
                }
            }
        
        if "ModuleNotFoundError: No module named" in error_log:
            module_match = re.search(r"No module named '(.*?)'", error_log)
            if module_match:
                module = module_match.group(1)
                self.log("💡", f"Detected missing module: {module}. Installing...")
                return {
                    "diagnosis": f"Missing python module: {module}",
                    "fix_type": "commands",
                    "confidence": "high",
                    "fix_details": {
                        "commands": [f"pip3 install {module}"]
                    }
                }
        
        return None

    def call_ai_for_fix(
        self, error_log: str, project_type: str, files_content: dict
    ) -> Optional[dict]:
        hard_fix = self._check_hardcoded_fixes(error_log)
        if hard_fix:
            return hard_fix
        
        self.log("🤖", "Consulting AI for error diagnosis...")

        priority_files = self.locate_error_files(error_log)
        if priority_files:
            ordered = {k: v for k, v in files_content.items() if k in priority_files}
            ordered.update({k: v for k, v in files_content.items() if k not in priority_files})
            files_content = ordered

        tail_chars    = int(os.environ.get('ERROR_LOG_TAIL', '5000'))
        snippet_chars = int(os.environ.get('FILE_SNIPPET_CHARS', '20000'))
        max_ctx_files = int(os.environ.get('MAX_CONTEXT_FILES', '8'))

        files_context = ""
        for name, content in list(files_content.items())[:max_ctx_files]:
            # Use the smaller of original content or snippet_chars limit
            display_content = content[:snippet_chars]
            files_context += f"// FILE: {name}\n{display_content}\n\n"

        prompt = """You are an expert debugging engineer. Diagnose this runtime error and provide a surgical fix.

USER INTENT (CRITICAL): [USER_PROMPT]
SYSTEM: [OS_INFO]
INSTALLED TOOLS: [TOOLS]
MANIFESTS: [MANIFEST]
PROJECT TYPE: [PROJECT_TYPE]

ERROR LOG (last_tail):
[ERROR_LOG]

PROJECT FILES:
[FILES_CONTEXT]

CRITICAL: Return ONLY the following tagged XML-like structure (no JSON, no narrative, no markdown):

<vibe-fix>
  <diagnosis>root cause in one sentence</diagnosis>
  <fix_type>commands | code_patch | code_change</fix_type>
  <confidence>high | medium | low</confidence>
  <fix_details>
    <!-- code_patch -->
    <file>relative file path</file>
    <vibe-hunk>
      <search>exact verbatim block to find</search>
      <replace>replacement block</replace>
    </vibe-hunk>

    <!-- code_change -->
    <content>complete new file content (only for code_change full rewrite)</content>
    <append>false</append>

    <!-- commands -->
    <command>one-time setup/install command only (never server start)</command>
    <run_command>updated server start command if it needs to change (optional)</run_command>
  </fix_details>
</vibe-fix>

RULES:
- Prefer fix_type=code_patch for targeted fixes (1-10 lines changed).
- Prefer fix_type=commands for missing packages/dependencies.
- Prefer fix_type=code_change if the entire file needs restructuring, is corrupted, or has syntax errors.
- For SyntaxError, IndentationError, EOF errors, bash quoting errors, or truncated files:
  ALWAYS use fix_type=code_change to provide the FULL, CORRECTED file. DO NOT TRUNCATE.
- JSX SYNTAX ERRORS: For React/JSX errors like "Expected closing tag" or mismatched tags:
  * Use fix_type=code_change to provide the complete corrected JSX file
  * Ensure ALL opening tags have matching closing tags: <div>...</div>, <button>...</button>
  * Check for proper nesting - buttons cannot contain divs, spans are inline elements
  * Verify all JSX expressions are properly closed with matching braces and parentheses
  * Self-closing tags must end with /> (e.g., <img />, <br />, <input />)
- 0.0.0.0 BINDING: Servers MUST bind to 0.0.0.0, never localhost.
- RELATIVE URLs: Frontend-to-backend calls must use relative paths (e.g., fetch('/api/todos')).
- NAMESPACING: API routes should stay under /api/* prefix.
- SPA FALLBACK: If fixing a backend that serves a frontend, ensure the fallback to index.html is preserved.
- NO DEV SERVERS: Fixes should never introduce dev servers (like Vite dev) as the primary process.
- ENVIRONMENT: Global installs only. No venv/virtualenv. No 'python' (use 'python3'). Bash syntax only.
- For pip conflicts: pip3 install --upgrade pip && pip3 install -r requirements.txt --use-deprecated=legacy-resolver
- NEVER use shell redirection syntax (echo, cat, printf with > or >>) inside 'commands' to write file content.
  If you need to create or fix a file, use fix_type=code_change instead. The agent writes files directly — no shell quoting needed.
- 'code_change' content must ONLY contain the literal source code for that file — no shell syntax.
- IGNORE access logs in the error log (e.g., "GET / HTTP/1.1 302" or "200"). These are NORMAL behaviors and not errors.
- DO NOT assume templates are missing just because you see a redirect to /login. Only fix missing files if there is an explicit "TemplateNotFound" or "FileNotExists" error.
- NEVER put the server start command inside commands[]. It will time out and kill the fix.
  If the run command needs to change (wrong path, wrong module, wrong port), put the
  corrected command in fix_details.run_command instead.
- NGINX SITE CONFIGS: When fixing nginx configs in /etc/nginx/sites-enabled/ or /etc/nginx/sites-available/, NEVER include events, http, or worker_processes directives. These belong ONLY in /etc/nginx/nginx.conf. Site configs should ONLY contain server blocks.
"""
        # Perform template replacements
        prompt = prompt.replace("[USER_PROMPT]", str(self.config.user_prompt or "Unknown"))
        prompt = prompt.replace("[OS_INFO]", str(self.os_info))
        prompt = prompt.replace("[TOOLS]", str(self.tools))
        prompt = prompt.replace("[MANIFEST]", str(self.manifest))
        prompt = prompt.replace("[PROJECT_TYPE]", str(project_type))
        prompt = prompt.replace("[ERROR_LOG]", error_log[-tail_chars:])
        prompt = prompt.replace("[FILES_CONTEXT]", files_context)
        
        return self._call_ai(prompt, temperature=0.2)

    # ------------------------------------------------------------------
    # Patch helpers — validation, line endings, atomic writes
    # ------------------------------------------------------------------

    def _validate_syntax(self, content: str, filepath: Path) -> Tuple[bool, Optional[str]]:
        """Validate syntax of patched content for known file types."""
        suffix = filepath.suffix.lower()
        if suffix == '.py':
            try:
                compile(content, str(filepath), 'exec')
                return True, None
            except SyntaxError as e:
                return False, f"line {e.lineno}: {e.msg}"
        if suffix == '.json':
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"line {e.lineno}: {e.msg}"
        return True, None

    def _detect_line_separator(self, text: str) -> str:
        """Detect the dominant line separator in text."""
        crlf = text.count('\r\n')
        lf = text.count('\n') - crlf
        if crlf > 0 and crlf >= lf:
            return '\r\n'
        return '\n'

    def _atomic_write(self, filepath: Path, content: str):
        """Write atomically via temp file + os.replace."""
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(filepath.parent), suffix='.tmp'
        )
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmp_path, str(filepath))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _match_hunk(self, content: str, search: str, replace: str, line_sep: str) -> Tuple[Optional[str], str]:
        """
        4-tier matching for a single hunk.
        Returns (new_content, tier_name) on success, or (None, reason) on failure.
        """
        # Tier 1: Exact match
        if search in content:
            return content.replace(search, replace, 1), "exact"

        search_lines = search.splitlines()
        replace_lines = replace.splitlines()
        content_lines = content.split(line_sep) if line_sep != '\n' else content.splitlines()
        trailing = content.endswith(line_sep) or content.endswith('\n')

        def _rejoin(lines):
            joined = line_sep.join(lines)
            if trailing:
                joined = joined.rstrip(line_sep) + line_sep
            return joined

        # Tier 2: Whitespace-normalised match
        def normalize(s):
            return re.sub(r'\s+', ' ', s).strip()

        norm_search = [normalize(l) for l in search_lines]
        for idx in range(len(content_lines) - len(search_lines) + 1):
            window = content_lines[idx: idx + len(search_lines)]
            if [normalize(l) for l in window] == norm_search:
                content_lines[idx: idx + len(search_lines)] = replace_lines
                return _rejoin(content_lines), "whitespace-norm"

        # Tier 3: Indentation-flexible match with relative indent preservation
        search_stripped = [l.strip() for l in search_lines]
        search_base = min(
            (len(l) - len(l.lstrip()) for l in search_lines if l.strip()),
            default=0
        )

        for idx in range(len(content_lines) - len(search_stripped) + 1):
            window = content_lines[idx: idx + len(search_stripped)]
            if [l.strip() for l in window] == search_stripped:
                window_base = min(
                    (len(l) - len(l.lstrip()) for l in window if l.strip()),
                    default=0
                )
                delta = window_base - search_base
                new_lines = []
                for l in replace_lines:
                    if not l.strip():
                        new_lines.append(l)
                    else:
                        new_indent = max(0, (len(l) - len(l.lstrip())) + delta)
                        new_lines.append(" " * new_indent + l.lstrip())
                content_lines[idx: idx + len(search_stripped)] = new_lines
                return _rejoin(content_lines), f"indent-flex(delta={delta:+d})"

        # Tier 4: difflib fuzzy match with variable window size (±2 lines)
        # Use whitespace-normalized matching to handle formatting drift.
        def norm_text(s: str) -> str:
            return re.sub(r'\s+', ' ', s).strip()

        search_norm = norm_text(search)

        base_window = len(search_lines)
        best_score, best_idx, best_size = 0.0, -1, base_window

        for size_delta in (0, -1, 1, -2, 2):
            ws = base_window + size_delta
            if ws < 1 or ws > len(content_lines):
                continue
            for idx in range(len(content_lines) - ws + 1):
                window_text = "\n".join(content_lines[idx: idx + ws])
                window_norm = norm_text(window_text)
                score = difflib.SequenceMatcher(None, search_norm, window_norm).ratio()
                if score > best_score:
                    best_score, best_idx, best_size = score, idx, ws

        if best_idx >= 0 and best_score >= self.config.fuzzy_threshold:
            content_lines[best_idx: best_idx + best_size] = replace_lines
            return _rejoin(content_lines), f"fuzzy(score={best_score:.2f}, win={best_size})"

        # Relaxed second-chance retry to prevent false negatives like no-match(best=0.51).
        relaxed_threshold = 0.65
        if best_idx >= 0 and best_score >= relaxed_threshold:
            anchor_lines = [l.strip() for l in search_lines[:3] if l.strip()]
            if not anchor_lines:
                content_lines[best_idx: best_idx + best_size] = replace_lines
                return _rejoin(content_lines), f"fuzzy-relaxed(score={best_score:.2f}, win={best_size})"

            window_norm = norm_text("\n".join(content_lines[best_idx: best_idx + best_size]))
            if any(norm_text(a) in window_norm for a in anchor_lines):
                content_lines[best_idx: best_idx + best_size] = replace_lines
                return _rejoin(content_lines), f"fuzzy-relaxed(score={best_score:.2f}, win={best_size})"

        return None, f"no-match(best={best_score:.2f})"

        # ------------------------------------------------------------------
        # Surgical patch engine — tolerant (best-effort per-hunk)
        # ------------------------------------------------------------------

    def _apply_code_patch(self, filepath: Path, hunks: list) -> bool:
        if not filepath.exists():
            self.log("❌", f"Patch target not found: {filepath}")
            return False

        try:
            original = filepath.read_text(encoding="utf-8")
        except Exception as e:
            self.log("❌", f"Cannot read {filepath}: {e}")
            return False

        line_sep = self._detect_line_separator(original)
        content = original
        applied = 0
        tiers = []

        for i, hunk in enumerate(hunks):
            search = hunk.get("search", "")
            replace = hunk.get("replace", "")

            if not search:
                self.log("⚠️", f"Hunk {i+1}: empty search — skipping")
                continue

            new_content, tier = self._match_hunk(content, search, replace, line_sep)

            if new_content is None:
                # Retry mechanism: re-read file from disk and try again
                self.log("⚠️", f"Hunk {i+1}: {tier} — re-reading file and retrying")
                
                try:
                    # Re-read current file state from disk
                    fresh_content = filepath.read_text(encoding="utf-8")
                    fresh_line_sep = self._detect_line_separator(fresh_content)
                    
                    # Retry the hunk with fresh content
                    new_content, retry_tier = self._match_hunk(fresh_content, search, replace, fresh_line_sep)
                    
                    if new_content is None:
                        # Still failed after retry - skip this hunk
                        self.log("⚠️", f"Hunk {i+1}: {retry_tier} after retry — skipping hunk")
                        continue
                    else:
                        # Retry succeeded
                        self.log("✅", f"Hunk {i+1}: {retry_tier} (after retry)")
                        content = new_content
                        line_sep = fresh_line_sep
                        applied += 1
                        tiers.append(f"{retry_tier}(retry)")
                except Exception as e:
                    self.log("❌", f"Hunk {i+1}: retry failed with error: {e} — skipping hunk")
                    continue
            else:
                content = new_content
                applied += 1
                tiers.append(tier)
                self.log("✅", f"Hunk {i+1}: {tier}")

        if applied == 0:
            self.log("❌", "No hunks applied")
            return False

        if content == original:
            self.log("⚠️", "Patch produced no changes")
            return False

        is_valid, err = self._validate_syntax(content, filepath)
        if not is_valid:
            self.log("❌", f"Post-patch syntax error in {filepath.name}: {err} — aborting")
            return False

        if "/etc/nginx/sites-enabled" in str(filepath):
            backup = Path("/tmp") / f"{filepath.name}.bak"
        else:
            backup = filepath.with_suffix(filepath.suffix + ".bak")
        shutil.copy2(filepath, backup)
        self.log("💾", f"Backup: {backup}")

        try:
            self._atomic_write(filepath, content)
        except Exception as e:
            self.log("❌", f"Atomic write failed for {filepath.name}: {e} — restoring backup")
            shutil.copy2(backup, filepath)
            return False

        self.log("🩹", f"Patched {filepath.name}: {applied}/{len(hunks)} hunks [{', '.join(tiers)}]")
        return True

    def _resolve_path(self, filename: str) -> Optional[Path]:
        """Tries to find the intended file within the workspace if direct path fails."""
        if not filename:
            return None
        
        # 1. Direct match
        direct = Path(self.workspace) / filename
        if direct.exists():
            return direct
            
        # 2. Search for filename (basename) in workspace
        basename = os.path.basename(filename)
        for root, _, files in os.walk(self.workspace):
            if basename in files:
                target = Path(root) / basename
                self.log("🔍", f"Redirected {filename} -> {target.relative_to(self.workspace)}")
                return target
                
        return None

    # ------------------------------------------------------------------
    # Apply fix dispatcher
    # ------------------------------------------------------------------

    def apply_fix(self, fix_data: dict) -> Tuple[bool, Optional[str]]:
        """
        Returns (success, new_run_command).
        new_run_command is non-None when AI provides a corrected server start command.
        """
        if not fix_data:
            return False, None

        self.log("🔧", f"Applying fix [{fix_data.get('confidence', '?')}]: "
                        f"{fix_data.get('diagnosis', '')[:120]}")

        fix_type        = fix_data.get("fix_type")
        details         = fix_data.get("fix_details", {})
        new_run_command = details.get("run_command") or None   # ← extract updated run command

        if new_run_command:
            self.log("🔄", f"AI updated run command: {new_run_command}")

        try:
            if fix_type == "commands":
                for cmd in details.get("commands", []):
                    # Use streaming runner to avoid blind hangs
                    success, _ = self._run_setup_command(cmd)
                    if not success:
                        self.log("⚠️", f"Command failed: {cmd}")
                return True, new_run_command

            elif fix_type == "code_patch":
                filename = details.get("file")
                hunks    = details.get("hunks", [])
                if not filename or not hunks:
                    self.log("⚠️", "code_patch missing file or hunks")
                    return False, None
                
                filepath = self._resolve_path(filename)
                if not filepath:
                    self.log("❌", f"Patch target not found: {filename}")
                    return False, None
                    
                return self._apply_code_patch(filepath, hunks), new_run_command

            elif fix_type == "code_change":
                filename = details.get("file")
                content  = details.get("content")
                append   = details.get("append", False)
                if filename and content:
                    filepath = self._resolve_path(filename)
                    if not filepath:
                        # If totally new file, create in root or as specified
                        filepath = Path(self.workspace) / filename
                        filepath.parent.mkdir(parents=True, exist_ok=True)
                    
                    if append:
                        with filepath.open("a", encoding="utf-8") as f:
                            f.write(content)
                    else:
                        filepath.write_text(content, encoding="utf-8")
                    self.log("✅", f"{'Appended' if append else 'Wrote'} {filename}")
                    return True, new_run_command

            else:
                self.log("⚠️", f"Unknown fix_type '{fix_type}' — skipping")

        except subprocess.TimeoutExpired:
            self.log("❌", "Command timed out")
        except Exception as e:
            self.log("❌", f"Fix application failed: {e}")

        return False, None

    # ------------------------------------------------------------------
    # Log-line classifiers
    # ------------------------------------------------------------------

    def _is_error_line(self, line: str) -> bool:
        lower = line.lower()
        
        # Track binding signals
        is_running_msg = any(x in lower for x in ("listening", "running", "serving"))
        if is_running_msg:
            if "0.0.0.0" in lower or "all addresses" in lower or "*:" in lower:
                self.config.seen_bind_all = True
            elif "127.0.0.1" in lower or "localhost" in lower:
                self.config.seen_bind_local = True

        # Actual error keywords (ignoring access logs unless they indicate a broken root)
        # We look for "GET / HTTP/1.1" 404 which usually means the entrypoint is misconfigured
        if re.search(r'GET /\s+HTTP/.*"\s+404', line, re.IGNORECASE) or \
           re.search(r'GET /\?.*HTTP/.*"\s+404', line, re.IGNORECASE):
            self.log("⚠️", "Root path returned 404 — entrypoint might be misconfigured")
            return True

        if re.search(r'"[A-Z]+\s+.*\s+HTTP/.*"\s+\d{3}', line):
            # Ignore standard 2xx/3xx/404 on subpaths (which might be user clicking around)
            return False

        return any(kw in lower for kw in self.config.error_keywords)

    def _is_success_line(self, line: str, extra_patterns: list) -> bool:
        lower = line.lower().strip()
        all_patterns = self.config.success_keywords + [p.lower() for p in extra_patterns]
        for p in all_patterns:
            if not p: continue
            if p in lower: return True
            import re
            if any(c in p for c in ('*', '+', '?', '[', '(', '^', '$')):
                try:
                    if re.search(p, line, re.IGNORECASE): return True
                except re.error: pass
        return False

    def _check_port_open(self, port: int, host: str = "127.0.0.1") -> bool:
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                return s.connect_ex((host, port)) == 0
        except: return False

    # ------------------------------------------------------------------
    # Subprocess output streamer — Thread + Queue (stdlib only)
    # ------------------------------------------------------------------

    def _stream_process(self, process) -> tuple:
        """
        Streams process stdout via a background thread into a Queue.
        Guarantees ALL output is captured even if process dies instantly.

        Returns (q, sentinel, reader_thread)
        """
        q        = Queue()
        sentinel = object()  # signals thread has finished draining

        def _reader(stream, queue):
            """Runs in background — reads until EOF then posts sentinel."""
            try:
                for line in iter(stream.readline, ''):
                    queue.put(line)
            finally:
                queue.put(sentinel)   # always signals done, even on exception
                stream.close()

        reader_thread = Thread(target=_reader, args=(process.stdout, q), daemon=True)
        reader_thread.start()
        return q, sentinel, reader_thread


    def _monitor_process(self, process, success_patterns: list) -> tuple:
        """
        Monitors a running process using Thread + Queue.
        Collects output for startup_timeout seconds, then drains any remaining
        buffered output if the process has already exited.

        Returns (output_lines: list, error_flag: bool)
        """
        q, sentinel, reader_thread = self._stream_process(process)
        # Store queue info so _monitor_runtime can continue later
        setattr(process, '_q_info', (q, sentinel, reader_thread))

        output_lines = []
        error_flag   = False
        start        = time.time()
        done         = False

        # ── Phase 1: Live monitoring window ──────────────────────────────
        process_ready = False
        last_port_check = 0
        target_port = None
        import re
        cmd = str(getattr(process, 'args', ''))
        port_match = re.search(r'(?:--port|PORT=)\s*(\d+)', cmd) or re.search(r':(\d{3,})\b', cmd)
        if port_match:
            try: target_port = int(port_match.group(1))
            except: pass

        while time.time() - start < self.config.startup_timeout:
            if target_port and time.time() - last_port_check > 1.2:
                last_port_check = time.time()
                if self._check_port_open(target_port):
                    self.log("✅", f"Port {target_port} is open — process is ready")
                    process_ready = True
                    break

            try:
                item = q.get(timeout=float(os.environ.get('POLL_INTERVAL', '0.05')))
            except Empty:
                if process.poll() is not None and done: break
                continue

            if item is sentinel:
                done = True
                break

            print(item, end="", flush=True)
            output_lines.append(item)
            if self._is_error_line(item): error_flag = True
            
            if not process_ready and self._is_success_line(item, success_patterns) and not error_flag:
                self.log("✅", "Ready signal detected in logs")
                process_ready = True
                if getattr(process, '_vibe_type', '') == 'setup': break
            
            if process_ready and not error_flag: break

        if not process_ready and not error_flag and process.poll() is None:
            if target_port and self._check_port_open(target_port):
                self.log("✅", f"Port {target_port} is active — proceeding")
                process_ready = True

        # ── Phase 1.5: Final Binding Validation ──────────────────────────
        # If we finished the startup window and strictly only saw 127.0.0.1
        if self.config.seen_bind_local and not self.config.seen_bind_all:
            self.log("⚠️", "Detected local-only binding — triggering self-healing for 0.0.0.0")
            error_flag = True

        # ── Phase 2: Drain remaining buffer after process exits ──────────
        # Captures the actual error line that arrives after the traceback header
        if process.poll() is not None:
            drain_timeout = float(os.environ.get('DRAIN_TIMEOUT', '3.0'))
            drain_start   = time.time()

            while time.time() - drain_start < drain_timeout:
                try:
                    item = q.get(timeout=0.1)
                except Empty:
                    if done:
                        break
                    continue

                if item is sentinel:
                    break

                print(item, end="", flush=True)
                output_lines.append(item)

                if self._is_error_line(item):
                    error_flag = True

        return output_lines, error_flag

    def _monitor_runtime(self, process, success_patterns: list) -> tuple:
        """
        Continuously drains and monitors a process after it has successfully started.
        Maintains real-time log streaming and checks for runtime errors.
        """
        self.log("👁️", "Entering runtime monitoring mode...")
        
        # Retrieve the queue state from the process (stored by _monitor_process)
        qinfo = getattr(process, '_q_info', None)
        if not qinfo:
            self.log("⚠️", "No queue info found on process — cannot monitor runtime")
            return [], False
            
        q, sentinel, _ = qinfo
        runtime_lines = []
        runtime_error = False
        
        while True:
            try:
                # Use a slightly longer timeout for idle runtime
                item = q.get(timeout=float(os.environ.get('POLL_INTERVAL', '0.05')))
            except Empty:
                if process.poll() is not None:
                    break
                continue

            if item is sentinel:
                break

            print(item, end="", flush=True)
            runtime_lines.append(item)

            if self._is_error_line(item):
                self.log("🚨", "Runtime issue detected in logs")
                runtime_error = True
                # Break to trigger self-healing
                break
                
        return runtime_lines, runtime_error

    def _apply_file_writes(self, file_writes: list) -> int:
        """
        Write files directly from structured data — no shell quoting needed.
        Returns the number of files successfully written.
        """
        written = 0
        for entry in file_writes:
            rel_path = entry.get("path", "").strip()
            content = entry.get("content")
            if not rel_path or content is None:
                continue
            filepath = Path(self.workspace) / rel_path
            try:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")
                self.log("📄", f"Wrote {rel_path} ({len(content)} chars)")
                written += 1
            except Exception as e:
                self.log("❌", f"Failed to write {rel_path}: {e}")
        return written

    @staticmethod
    def _is_echo_redirect(cmd: str) -> bool:
        """Detect shell commands that try to write file content via echo/cat/printf redirection."""
        return bool(re.search(
            r"""(?:^|\s)(?:echo|printf|cat)\s+['"].*['"]?\s*>{1,2}\s*\S+""",
            cmd, re.DOTALL
        ))

    def _run_setup_command(self, cmd: str) -> tuple:
        """
        Runs a setup command to completion with live streaming output.
        Returns (success: bool, output: list)
        """
        if self._is_echo_redirect(cmd):
            self.log("⚠️", f"[setup] Intercepted unsafe echo/redirect — skipping: {cmd[:80]}...")
            return True, []

        self.log("⚙️", f"[setup] {cmd}")
        output_lines = []

        try:
            process = subprocess.Popen(
                cmd, shell=True,
                executable='/bin/bash',
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            q        = Queue()
            sentinel = object()

            def _reader(stream, queue):
                try:
                    for line in iter(stream.readline, ''):
                        queue.put(line)
                finally:
                    queue.put(sentinel)
                    stream.close()

            Thread(target=_reader, args=(process.stdout, q), daemon=True).start()

            while True:
                try:
                    item = q.get(timeout=1.0)
                except Empty:
                    # No output for 1s — check if process is still alive
                    if process.poll() is not None:
                        break
                    continue

                if item is sentinel:
                    break

                print(item, end="", flush=True)
                output_lines.append(item)

            process.wait()

            if process.returncode != 0:
                self.log("⚠️", f"Setup exited {process.returncode}")
                return False, output_lines

            return True, output_lines

        except Exception as e:
            self.log("❌", f"Setup command failed: {e}")
            return False, []

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def run_with_healing(self) -> bool:
        self.log("🚀", "Starting AI-Driven Self-Healing Agent")
        self.log("📂", f"Workspace : {self.workspace}")
        self.log("🖥️", f"System    : {self.os_info}")
        self.log("🔌", f"Port      : {self.config.port}")

        # Build recursive file list for full project awareness
        all_files = []
        for root, dirs, fnames in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in fnames:
                rel = os.path.relpath(os.path.join(root, fname), self.workspace)
                all_files.append(rel)

        if not all_files:
            self.log("❌", "Workspace is empty — nothing to run")
            return False

        self.log("📋", f"Found {len(all_files)} files in workspace")

        plan = self.get_ai_execution_plan(all_files)
        if not plan:
            return False

        # Prepare context for AI (define at method level for exception handler access)
        files_content    = self.scan_project_files()
        project_type     = plan.get("project_type", "unknown")
        processes        = plan.get("processes", [])
        success_patterns = plan.get("success_patterns", [])
        nginx_config     = plan.get("nginx_config")
        background_pids  = []   # Initialize early for exception handler cleanup

        self.log("🎯", f"Stack  : {project_type}")
        self.log("📋", f"Plan   : {plan.get('analysis', '')}")

        # ── Phase 0: Apply structured file writes (safe, no shell quoting) ──
        file_writes = plan.get("file_writes") or []
        if file_writes:
            n = self._apply_file_writes(file_writes)
            self.log("📝", f"Applied {n}/{len(file_writes)} file writes")
            if n > 0:
                files_content = self.scan_project_files()

        if not processes:
            self.log("❌", "AI returned no processes")
            return False

        # Separate by type — order matters: setup → background → primary
        setup_procs      = [p for p in processes if p.get("type") == "setup"]
        background_procs = [p for p in processes if p.get("type") == "background"]
        primary_proc     = next((p for p in processes if p.get("type") == "primary"), None)

        if not primary_proc:
            self.log("❌", "AI returned no primary process")
            return False

        run_command      = primary_proc.get("command", "")
        # background_pids already initialized earlier

        for proc in setup_procs:
            cmd = proc.get("command", "")
            success, setup_output = self._run_setup_command(cmd)
            
            if not success:
                self.log("🚨", "Setup failed — attempting AI fix...")
                error_log = "".join(setup_output)
                fix = self.call_ai_for_fix(error_log, project_type, files_content)
                fix_success, _ = self.apply_fix(fix) if fix else (False, None)
                
                if fix_success:
                    self.log("🔄", "Setup fix applied — retrying setup...")
                    files_content = self.scan_project_files()
                    # Re-run the current setup command once more
                    success, _ = self._run_setup_command(cmd)
                    if not success:
                        self.log("⚠️", "Retry failed — continuing anyway")
                else:
                    self.log("⚠️", "No fix applied — continuing anyway")

        
        # ── Phase 1.5: Apply Nginx gateway (after setup/build) ──
        nginx_config = plan.get("nginx_config")
        if nginx_config:
            try:
                # Clean up sites-enabled backup garbage
                sites_enabled_dir = Path("/etc/nginx/sites-enabled")
                if sites_enabled_dir.exists():
                    for f in sites_enabled_dir.glob("*.bak*"):
                        try: f.unlink()
                        except: pass
                
                # CLEANUP NGINX CONFIG: strip http, events, and other global blocks
                # We only want the server { ... } blocks for sites-enabled/default
                original_nginx_config = nginx_config
                if "http {" in nginx_config:
                    self.log("🧹", "Stripping http wrapper from Nginx config")
                    # Try to extract contents of http block using balanced braces or regex
                    # Simple regex approach first:
                    h_match = re.search(r'http\s*\{(.+)\}\s*(?:events|$|worker)', nginx_config, re.DOTALL)
                    if h_match:
                        nginx_config = h_match.group(1).strip()
                    else:
                        # Fallback for complex nesting: remove first '{' and last '}'
                        parts = nginx_config.split('{', 1)
                        if len(parts) > 1:
                            nginx_config = parts[1].rsplit('}', 1)[0]
                
                # Further cleanup: remove events, worker_processes, etc. if they are still at top level
                nginx_config = re.sub(r'events\s*\{.*?\}', '', nginx_config, flags=re.DOTALL)
                nginx_config = re.sub(r'worker_processes\s+.*?;', '', nginx_config)
                nginx_config = re.sub(r'user\s+.*?;', '', nginx_config)
                nginx_config = re.sub(r'error_log\s+.*?;', '', nginx_config)
                nginx_config = re.sub(r'pid\s+.*?;', '', nginx_config)
                
                # Re-wrap in a single server block if only directives are left without server wrapper
                # (Handle case where AI might give location blocks only)
                if "location" in nginx_config and "server {" not in nginx_config:
                    self.log("🔧", "Wrapping location blocks in a default server block")
                    nginx_config = "server {\n    listen 80;\n    server_name localhost;\n" + nginx_config + "\n}"

                nginx_config = nginx_config.strip()

                # Write and validate
                nginx_conf_path = Path("/etc/nginx/sites-enabled/default")
                nginx_conf_path.parent.mkdir(parents=True, exist_ok=True)
                nginx_conf_path.write_text(nginx_config, encoding="utf-8")
                
                # HARD RESTART: stop and kill current nginx to ensure it binds to fresh config
                self.log("🔄", "Hard restarting Nginx gateway...")
                subprocess.run(["nginx", "-s", "stop"], capture_output=True, timeout=5)
                subprocess.run(["pkill", "-9", "nginx"], capture_output=True, timeout=5)
                
                test_result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
                if test_result.returncode == 0:
                    start_res = subprocess.run(["nginx"], capture_output=True, timeout=10)
                    if start_res.returncode == 0:
                        self.log("🚀", "Nginx gateway active on port 80")
                    else:
                        self.log("❌", f"Nginx failed: {start_res.stderr}")
                else:
                    self.log("⚠️", f"Nginx config invalid: {test_result.stderr}")
                    # Revert to valid config if possible?
            except Exception as e:
                self.log("⚠️", f"Failed to setup Nginx: {e}")

        # ── Phase 2: Background processes (non-blocking, wait for signal) ──
        for proc in background_procs:
            cmd          = proc.get("command", "")
            ready_signal = proc.get("ready_signal") or ""
            name         = proc.get("name", "background")

            self.log("🔀", f"[background] {name}: {cmd}")
            bg = subprocess.Popen(
                cmd, shell=True, executable='/bin/bash',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            background_pids.append(bg)

            # Wait for ready_signal before continuing
            if ready_signal:
                wait_start = time.time()
                bg_timeout = self.config.bg_ready_timeout
                self.log("⏳", f"Waiting for [{name}] ready signal (log or port)...")
                
                # Extract port for background process monitoring
                bg_port = None
                p_match = re.search(r'(?:--port|PORT=)\s*(\d+)', cmd) or re.search(r':(\d{3,})\b', cmd)
                if p_match: bg_port = int(p_match.group(1))

                while time.time() - wait_start < bg_timeout:
                    # Smart check 1: Port is open
                    if bg_port and self._check_port_open(bg_port):
                        self.log("✅", f"[{name}] port {bg_port} is open")
                        break
                    
                    # Smart check 2: Log matching
                    if bg.stdout is not None:
                        line = bg.stdout.readline()
                        if line:
                            print(line, end="", flush=True)
                            if self._is_success_line(line, [ready_signal]):
                                self.log("✅", f"[{name}] ready signal detected")
                                break
                    if bg.poll() is not None:
                        self.log("⚠️", f"[{name}] exited early")
                        break
                    time.sleep(0.1)

        # ── Phase 3: Primary process with self-healing ─────────────────────
        files_content  = self.scan_project_files()
        max_attempts   = self.config.max_attempts
        attempt_count  = 0

        try:
            while self.retry_count < self.config.max_retries and attempt_count < max_attempts:
                attempt_count += 1
                self.log("▶️", f"Attempt {attempt_count} (stuck={self.retry_count}/{self.config.max_retries}): {run_command}")

                try:
                    process = subprocess.Popen(
                        run_command,
                        shell=True,
                        executable='/bin/bash',
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )

                    setattr(process, '_vibe_type', 'primary')
                    output_lines, error_flag = self._monitor_process(process, success_patterns)

                    if process.poll() is not None or error_flag:
                        self.log("❌", "Runtime issue detected — invoking AI fix...")
                        try:
                            process.terminate()
                        except Exception:
                            pass

                        error_log = "".join(output_lines)

                        # ── Fast-path: port already in use — just kill it and retry ──
                        if 'EADDRINUSE' in error_log or 'address already in use' in error_log.lower():
                            self.log("🔌", f"Port [PORT] in use — killing and retrying...")
                            try:
                                subprocess.run(
                                    ['sh', '-c', f'lsof -ti:[PORT] | xargs -r kill -9'],
                                    capture_output=True, timeout=3
                                )
                                subprocess.run(
                                    ['sh', '-c', f'fuser -k [PORT]/tcp'],
                                    capture_output=True, timeout=3
                                )
                            except Exception:
                                pass
                            import time as _time; _time.sleep(1)
                            continue
                        fix = self.call_ai_for_fix(error_log, project_type, files_content)
                        success, new_run_cmd = self.apply_fix(fix) if fix else (False, None)

                        if success:
                            if new_run_cmd:
                                run_command = new_run_cmd
                                self.log("🔄", "Run command updated for next attempt")
                            self.log("✅", "Fix applied — retrying...")
                            files_content = self.scan_project_files()
                            continue
                        else:
                            self.log("❌", "AI fix could not be applied")
                            self.retry_count += 1
                            continue

                    if process.poll() is None:
                        self.log("✅", "Project is running successfully!")

                        # Keep draining stdout forever — no more blind waiting
                        runtime_lines, runtime_error = self._monitor_runtime(process, success_patterns)

                        if runtime_error:
                            self.log("🚨", "Runtime error detected — invoking AI fix...")
                            try:
                                process.terminate()
                            except Exception:
                                pass

                            error_log = "".join(output_lines + runtime_lines)

                            # ── Fast-path: port already in use ──
                            if 'EADDRINUSE' in error_log or 'address already in use' in error_log.lower():
                                self.log("🔌", f"Port [PORT] in use — killing and retrying...")
                                try:
                                    subprocess.run(
                                        ['sh', '-c', f'lsof -ti:[PORT] | xargs -r kill -9'],
                                        capture_output=True, timeout=3
                                    )
                                    subprocess.run(
                                        ['sh', '-c', f'fuser -k [PORT]/tcp'],
                                        capture_output=True, timeout=3
                                    )
                                except Exception:
                                    pass
                                import time as _time; _time.sleep(1)
                                continue
                            fix = self.call_ai_for_fix(error_log, project_type, files_content)
                            success, new_run_cmd = self.apply_fix(fix) if fix else (False, None)

                            if success:
                                if new_run_cmd:
                                    run_command = new_run_cmd
                                self.log("✅", "Runtime fix applied — restarting...")
                                files_content = self.scan_project_files()
                                continue
                            else:
                                self.log("❌", "Runtime fix failed")
                                self.retry_count += 1
                                continue

                        return True

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.log("❌", f"Execution error: {e}")
                    self.retry_count += 1

        except KeyboardInterrupt:
            self.log("🛑", "Interrupted")
        finally:
            # ── Cleanup all background processes ──────────────────────────
            for bg in background_pids:
                try:
                    bg.terminate()
                except Exception:
                    pass

        self.log("❌", f"Failed after {attempt_count} attempts")
        return False


if __name__ == "__main__":
    agent = AIAgent()
    sys.exit(0 if agent.run_with_healing() else 1)
