#!/usr/bin/env python3
"""
AI-Powered Self-Healing Agent
Fully dynamic: works with any tech stack via pure AI-driven analysis.
All tunables controlled via environment variables — zero hardcoded assumptions.

ENV VARS (all optional):
  AI_API_KEY / NVIDIA_API_KEY   – LLM provider API key
  AI_API_URL                    – OpenAI-compatible endpoint
  AI_MODEL                      – Model name
  PORT                          – Port the server must bind to (default: 8080)
  MAX_RETRIES                   – Self-healing retry limit (default: 3)
  STARTUP_TIMEOUT               – Seconds to monitor startup (default: 20)
  CMD_TIMEOUT                   – Max seconds per setup command (default: 120)
  AI_TIMEOUT                    – Seconds to wait for AI response (default: 60)
  MAX_FILE_SIZE                 – Max bytes per file sent to AI (default: 5000)
  MAX_FILES                     – Max files in AI context (default: 10)
  ERROR_KEYWORDS                – Comma-separated error log signals
  SUCCESS_KEYWORDS              – Comma-separated startup success signals
  SCAN_EXTENSIONS               – Comma-separated file extensions (default: auto)
  PROJECT_VERSIONS_DIR          – Root dir for versioned workspaces (default: /project/versions)
  WORKSPACE_PATH                – Explicit workspace path override
  FALLBACK_RUN_CMD              – Command when no AI key is available
  ERROR_LOG_TAIL                – Chars of error log sent to AI (default: 3000)
  FILE_SNIPPET_CHARS            – Chars per file in AI context (default: 3000)
  MAX_CONTEXT_FILES             – Files included in fix prompt (default: 5)
  POLL_INTERVAL                 – Stdout read loop sleep in seconds (default: 0.05)
  FUZZY_PATCH_THRESHOLD         – difflib match threshold for fuzzy patching (default: 0.85)
"""

import os
import sys
import subprocess
import json
import time
import re
import shutil
import platform
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Centralised configuration — all values from environment, never hardcoded
# ---------------------------------------------------------------------------

@dataclass
class Config:
    api_key: str = field(
        default_factory=lambda: os.environ.get('AI_API_KEY') or os.environ.get('NVIDIA_API_KEY', '')
    )
    api_url: str = field(
        default_factory=lambda: os.environ.get('AI_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
    )
    ai_model: str = field(
        default_factory=lambda: os.environ.get('AI_MODEL', 'openai/gpt-oss-120b')
    )
    port: str = field(
        default_factory=lambda: os.environ.get('PORT', '8080')
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get('MAX_RETRIES', '3'))
    )
    startup_timeout: int = field(
        default_factory=lambda: int(os.environ.get('STARTUP_TIMEOUT', '20'))
    )
    cmd_timeout: int = field(
        default_factory=lambda: int(os.environ.get('CMD_TIMEOUT', '120'))
    )
    ai_timeout: int = field(
        default_factory=lambda: int(os.environ.get('AI_TIMEOUT', '60'))
    )
    max_file_size: int = field(
        default_factory=lambda: int(os.environ.get('MAX_FILE_SIZE', '5000'))
    )
    max_files: int = field(
        default_factory=lambda: int(os.environ.get('MAX_FILES', '10'))
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
    fallback_run_cmd: str = field(
        default_factory=lambda: os.environ.get('FALLBACK_RUN_CMD', '')
    )
    fuzzy_threshold: float = field(
        default_factory=lambda: float(os.environ.get('FUZZY_PATCH_THRESHOLD', '0.85'))
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AIAgent:
    def __init__(self):
        self.config = Config()
        self.retry_count = 0
        self.os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        self.workspace = self._resolve_workspace()

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

    def _call_ai(self, prompt: str, temperature: float = 0.1) -> Optional[dict]:
        """
        Generic OpenAI-compatible API call.
        Handles JSON inside markdown code fences or as bare JSON.
        Returns parsed dict or None.
        """
        if not self.config.api_key:
            self.log("⚠️", "No AI API key — skipping AI call")
            return None

        try:
            import requests
            response = requests.post(
                self.config.api_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=self.config.ai_timeout,
            )

            if response.status_code != 200:
                self.log("❌", f"AI API error {response.status_code}: {response.text[:300]}")
                return None

            content = response.json()["choices"][0]["message"]["content"]

            # Extract JSON: markdown fence first, then bare object
            for pattern in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{.*\})"):
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))

            self.log("⚠️", "AI response contained no extractable JSON")

        except json.JSONDecodeError as e:
            self.log("❌", f"JSON parse error in AI response: {e}")
        except Exception as e:
            self.log("❌", f"AI call failed: {e}")

        return None

    # ------------------------------------------------------------------
    # Project file scanner — fully dynamic, no hardcoded extension list
    # ------------------------------------------------------------------

    def scan_project_files(self) -> dict:
        """
        Read all readable text files from workspace.
        Uses SCAN_EXTENSIONS if set, otherwise tries every file and
        skips binary ones via UTF-8 decode failure.
        """
        files_content: dict = {}
        candidates = [f for f in Path(self.workspace).glob("*") if f.is_file()]

        if self.config.scan_extensions:
            candidates = [f for f in candidates if f.suffix in self.config.scan_extensions]

        for file in candidates:
            if len(files_content) >= self.config.max_files:
                break
            try:
                content = file.read_text(encoding="utf-8")
                if len(content) <= self.config.max_file_size:
                    files_content[file.name] = content
            except (UnicodeDecodeError, PermissionError, OSError):
                pass

        return files_content

    # ------------------------------------------------------------------
    # Execution plan
    # ------------------------------------------------------------------

    def get_ai_execution_plan(self, files: list) -> Optional[dict]:
        """Ask AI to identify the stack and produce a full OS-aware execution plan."""
        if not self.config.api_key:
            fallback_cmd = (
                self.config.fallback_run_cmd
                or f"python3 -m http.server {self.config.port}"
            )
            self.log("⚠️", f"No AI key — fallback: {fallback_cmd}")
            return {
                "project_type": "unknown",
                "provision_commands": [],
                "dependency_commands": [],
                "run_command": fallback_cmd,
                "success_patterns": self.config.success_keywords,
                "analysis": "Fallback mode: no AI API key provided",
            }

        self.log("🤖", "AI is analyzing project structure and requirements...")

        prompt = f"""You are an expert DevOps engineer. Analyze the files below and produce a complete,
working execution plan for this system.

SYSTEM: {self.os_info}
TARGET PORT: {self.config.port}
WORKSPACE FILES: {", ".join(files)}

Return ONLY a raw JSON object (no markdown fences, no extra text):
{{
    "project_type": "exact runtime/framework (e.g. Node.js/Express, Python/FastAPI, Go/Fiber, Rust/Axum, PHP/Laravel, Ruby/Rails, Java/Spring, .NET/ASP, Deno, Bun, etc.)",
    "provision_commands": ["shell commands to install the runtime/compiler on {self.os_info} if not present"],
    "dependency_commands": ["shell commands to install project-level dependencies"],
    "run_command": "exact command to start the server; use $PORT env var where the framework supports it",
    "success_patterns": ["log substrings that confirm the server started successfully"],
    "analysis": "one-sentence explanation of what this project is and how you will run it"
}}

RULES:
- Detect the language/framework solely from the file names — do NOT assume anything.
- Use -y (or equivalent non-interactive flag) for all package manager installs.
- provision_commands must work even if the runtime is not installed yet.
- The server MUST bind to port {self.config.port}.
"""
        result = self._call_ai(prompt, temperature=0.1)
        if result:
            return result

        self.log("❌", "AI could not produce an execution plan")
        return None

    # ------------------------------------------------------------------
    # grep pre-flight — locates which files are relevant to the error
    # ------------------------------------------------------------------

    def locate_error_files(self, error_log: str) -> list:
        """
        Ask AI for regex patterns, then grep -rlE across workspace.
        AI decides both WHAT to search and HOW to match it.
        """
        patterns = self._get_ai_search_terms(error_log)
        if not patterns:
            return []

        try:
            combined = '|'.join(patterns)  # grep handles OR natively with -E
            result = subprocess.run(
                ['grep', '-rlE', combined, self.workspace],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                matched = [Path(p).name for p in result.stdout.strip().splitlines()]
                self.log("🔍", f"AI-directed grep found: {', '.join(matched)}")
                return matched
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return []

    def _get_ai_search_terms(self, error_log: str) -> list:
        """
        Lightweight AI call — returns regex patterns for grep -E.
        AI has full freedom to write broad or precise patterns.
        """
        prompt = f"""Analyze this error log. Return ONLY a JSON object with grep regex patterns.

ERROR LOG:
{error_log[-1500:]}

Return ONLY:
{{
    "patterns": [
        "regex pattern 1",
        "regex pattern 2",
        "regex pattern 3"
    ]
}}

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
        result = self._call_ai(prompt, temperature=0.0)
        if not result:
            return []

        patterns = [p for p in result.get("patterns", []) if p and len(p) > 2]
        self.log("🔍", f"AI regex patterns: {patterns}")
        return patterns

    # ------------------------------------------------------------------
    # Error fix — AI diagnosis with grep-prioritised file context
    # ------------------------------------------------------------------

    def call_ai_for_fix(
        self, error_log: str, project_type: str, files_content: dict
    ) -> Optional[dict]:
        """
        Ask AI to diagnose a runtime error and return a surgical fix.
        Files relevant to the error (via grep pre-flight) are placed first
        in the context window to maximise AI accuracy.
        """
        self.log("🤖", "Consulting AI for error diagnosis...")

        # grep pre-flight: prioritise files containing error identifiers
        priority_files = self.locate_error_files(error_log)
        if priority_files:
            ordered = {k: v for k, v in files_content.items() if k in priority_files}
            ordered.update({k: v for k, v in files_content.items() if k not in priority_files})
            files_content = ordered

        tail_chars     = int(os.environ.get('ERROR_LOG_TAIL', '3000'))
        snippet_chars  = int(os.environ.get('FILE_SNIPPET_CHARS', '3000'))
        max_ctx_files  = int(os.environ.get('MAX_CONTEXT_FILES', '5'))

        files_context = "\n\n".join(
            f"// FILE: {name}\n{content[:snippet_chars]}"
            for name, content in list(files_content.items())[:max_ctx_files]
        )

        prompt = f"""You are an expert debugging engineer. Diagnose this runtime error and provide a surgical fix.

SYSTEM: {self.os_info}
PROJECT TYPE: {project_type}

ERROR LOG (last {tail_chars} chars):
{error_log[-tail_chars:]}

PROJECT FILES:
{files_context}

Return ONLY a raw JSON object (no markdown fences):
{{
    "diagnosis": "root cause in one sentence",
    "fix_type": "commands | code_patch | code_change",
    "fix_details": {{
        "commands": ["full shell command 1", "full shell command 2"],
        "file": "relative file path (for code_patch or code_change)",
        "hunks": [
            {{
                "search": "exact verbatim block to find — include 1-2 surrounding context lines for uniqueness",
                "replace": "replacement block"
            }}
        ],
        "content": "complete new file content (only for code_change full rewrite)",
        "append": false
    }},
    "confidence": "high | medium | low"
}}

RULES:
- Prefer fix_type=code_patch for targeted fixes (1-10 lines changed).
- Prefer fix_type=commands for missing packages/dependencies.
- Only use fix_type=code_change if the entire file needs restructuring.
- For code_patch: hunk.search must be a verbatim copy of the exact lines to replace
  (preserve indentation and whitespace exactly). Include 1-2 context lines around the
  change to ensure uniqueness. Multiple hunks are allowed.
- For package installs, provide the FULL command derived from project_type
  (e.g. "npm install express", "pip install flask", "cargo add tokio --features rt-multi-thread").
"""
        return self._call_ai(prompt, temperature=0.2)

    # ------------------------------------------------------------------
    # Surgical patch engine — 4-tier matching strategy
    # ------------------------------------------------------------------

    def _apply_code_patch(self, filepath: Path, hunks: list) -> bool:
        """
        Apply search-replace hunks using a 4-tier matching strategy:
          Tier 1 — Exact string match
          Tier 2 — Whitespace-normalised match
          Tier 3 — Indentation-flexible match
          Tier 4 — difflib fuzzy match (threshold: FUZZY_PATCH_THRESHOLD)

        A .bak backup is created before any modification.
        If zero hunks match, restores from backup and returns False.
        """
        if not filepath.exists():
            self.log("❌", f"Patch target not found: {filepath}")
            return False

        try:
            original = filepath.read_text(encoding="utf-8")
        except Exception as e:
            self.log("❌", f"Cannot read {filepath}: {e}")
            return False

        backup = filepath.with_suffix(filepath.suffix + ".bak")
        shutil.copy2(filepath, backup)
        self.log("💾", f"Backup: {backup.name}")

        content = original
        applied = 0

        for i, hunk in enumerate(hunks):
            search  = hunk.get("search", "")
            replace = hunk.get("replace", "")

            if not search:
                self.log("⚠️", f"Hunk {i+1}: empty search — skipping")
                continue

            # Tier 1: Exact match
            if search in content:
                content = content.replace(search, replace, 1)
                self.log("✅", f"Hunk {i+1}: exact match")
                applied += 1
                continue

            # Tier 2: Whitespace-normalised match
            def normalize(s):
                return re.sub(r'\s+', ' ', s).strip()

            search_lines  = search.splitlines()
            replace_lines = replace.splitlines()
            content_lines = content.splitlines()

            norm_match = False
            for idx in range(len(content_lines) - len(search_lines) + 1):
                window = content_lines[idx: idx + len(search_lines)]
                if [normalize(l) for l in window] == [normalize(l) for l in search_lines]:
                    content_lines[idx: idx + len(search_lines)] = replace_lines
                    content = "\n".join(content_lines)
                    if original.endswith("\n"):
                        content += "\n"
                    self.log("✅", f"Hunk {i+1}: whitespace-normalised match")
                    applied += 1
                    norm_match = True
                    break
            if norm_match:
                continue

            # Tier 3: Indentation-flexible match
            search_stripped = [l.strip() for l in search_lines]
            content_lines   = content.splitlines()
            indent_match    = False

            for idx in range(len(content_lines) - len(search_stripped) + 1):
                window = content_lines[idx: idx + len(search_stripped)]
                if [l.strip() for l in window] == search_stripped:
                    indent = len(window[0]) - len(window[0].lstrip())
                    pad    = " " * indent
                    new_lines = [
                        pad + l.lstrip() if l.strip() else l
                        for l in replace_lines
                    ]
                    content_lines[idx: idx + len(search_stripped)] = new_lines
                    content = "\n".join(content_lines)
                    if original.endswith("\n"):
                        content += "\n"
                    self.log("✅", f"Hunk {i+1}: indentation-flexible match")
                    applied += 1
                    indent_match = True
                    break
            if indent_match:
                continue

            # Tier 4: difflib fuzzy match
            content_lines = content.splitlines()
            window_size   = len(search_lines)
            best_score, best_idx = 0.0, -1

            for idx in range(len(content_lines) - window_size + 1):
                window = "\n".join(content_lines[idx: idx + window_size])
                score  = difflib.SequenceMatcher(None, search, window).ratio()
                if score > best_score:
                    best_score, best_idx = score, idx

            if best_score >= self.config.fuzzy_threshold:
                content_lines[best_idx: best_idx + window_size] = replace_lines
                content = "\n".join(content_lines)
                if original.endswith("\n"):
                    content += "\n"
                self.log("✅", f"Hunk {i+1}: fuzzy match (score={best_score:.2f})")
                applied += 1
            else:
                self.log("⚠️", f"Hunk {i+1}: no match found (best={best_score:.2f}) — skipping")

        if applied == 0:
            self.log("❌", "No hunks applied — restoring backup")
            shutil.copy2(backup, filepath)
            return False

        filepath.write_text(content, encoding="utf-8")
        self.log("🩹", f"Patched {filepath.name}: {applied}/{len(hunks)} hunks applied")
        return True

    # ------------------------------------------------------------------
    # Apply fix dispatcher
    # ------------------------------------------------------------------

    def apply_fix(self, fix_data: dict) -> bool:
        """
        Dispatch AI fix by type:
          commands    → run shell commands (AI provides full commands, no hardcoded pkg managers)
          code_patch  → surgical search-replace via _apply_code_patch (4-tier)
          code_change → full file rewrite or append (last resort)
        """
        if not fix_data:
            return False

        self.log("🔧", f"Applying fix [{fix_data.get('confidence', '?')}]: "
                        f"{fix_data.get('diagnosis', '')[:120]}")

        fix_type = fix_data.get("fix_type")
        details  = fix_data.get("fix_details", {})

        try:
            if fix_type == "commands":
                for cmd in details.get("commands", []):
                    self.log("⚙️", f"Running: {cmd}")
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        timeout=self.config.cmd_timeout,
                    )
                    if result.returncode != 0:
                        self.log("⚠️", f"Exit {result.returncode}: {result.stderr[:300]}")
                return True

            elif fix_type == "code_patch":
                filename = details.get("file")
                hunks    = details.get("hunks", [])
                if not filename or not hunks:
                    self.log("⚠️", "code_patch missing file or hunks")
                    return False
                return self._apply_code_patch(Path(self.workspace) / filename, hunks)

            elif fix_type == "code_change":
                filename = details.get("file")
                content  = details.get("content")
                append   = details.get("append", False)
                if filename and content:
                    filepath = Path(self.workspace) / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    if append:
                        with filepath.open("a", encoding="utf-8") as f:
                            f.write(content)
                    else:
                        filepath.write_text(content, encoding="utf-8")
                    self.log("✅", f"{'Appended' if append else 'Wrote'} {filename}")
                    return True

            else:
                self.log("⚠️", f"Unknown fix_type '{fix_type}' — skipping")

        except subprocess.TimeoutExpired:
            self.log("❌", "Command timed out")
        except Exception as e:
            self.log("❌", f"Fix application failed: {e}")

        return False

    # ------------------------------------------------------------------
    # Log-line classifiers
    # ------------------------------------------------------------------

    def _is_error_line(self, line: str) -> bool:
        lower = line.lower()
        return any(kw in lower for kw in self.config.error_keywords)

    def _is_success_line(self, line: str, extra_patterns: list) -> bool:
        lower       = line.lower()
        all_patterns = self.config.success_keywords + [p.lower() for p in extra_patterns]
        return any(p in lower for p in all_patterns)

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def run_with_healing(self) -> bool:
        self.log("🚀", "Starting AI-Driven Self-Healing Agent")
        self.log("📂", f"Workspace : {self.workspace}")
        self.log("🖥️",  f"System    : {self.os_info}")
        self.log("🔌", f"Port      : {self.config.port}")

        files = os.listdir(self.workspace)
        if not files:
            self.log("❌", "Workspace is empty — nothing to run")
            return False

        plan = self.get_ai_execution_plan(files)
        if not plan:
            return False

        project_type    = plan.get("project_type", "unknown")
        run_command     = plan.get("run_command", "")
        success_patterns = plan.get("success_patterns", [])

        self.log("🎯", f"Stack  : {project_type}")
        self.log("📋", f"Plan   : {plan.get('analysis', '')}")

        # Setup phase — provision runtime + install dependencies
        setup_cmds = plan.get("provision_commands", []) + plan.get("dependency_commands", [])
        for cmd in setup_cmds:
            self.log("⚙️", f"Setup: {cmd}")
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=self.config.cmd_timeout,
            )
            if result.returncode != 0:
                self.log("⚠️", f"Setup warning: {result.stderr[:300]}")

        if not run_command:
            self.log("❌", "No run command in AI plan")
            return False

        files_content  = self.scan_project_files()
        poll_interval  = float(os.environ.get('POLL_INTERVAL', '0.05'))

        while self.retry_count < self.config.max_retries:
            self.log("▶️", f"Attempt {self.retry_count + 1}/{self.config.max_retries}: {run_command}")

            try:
                process = subprocess.Popen(
                    run_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                output_lines: list = []
                start      = time.time()
                error_flag = False

                while time.time() - start < self.config.startup_timeout:
                    line = process.stdout.readline()
                    if line:
                        print(line, end="", flush=True)
                        output_lines.append(line)
                        if self._is_error_line(line):
                            error_flag = True
                        if self._is_success_line(line, success_patterns):
                            self.log("✅", "Startup success signal detected")
                    if process.poll() is not None:
                        break
                    time.sleep(poll_interval)

                # Process died or emitted error lines
                if process.poll() is not None or error_flag:
                    self.log("❌", "Runtime issue detected — invoking AI fix...")
                    try:
                        process.terminate()
                    except Exception:
                        pass

                    error_log = "".join(output_lines)
                    fix = self.call_ai_for_fix(error_log, project_type, files_content)

                    if fix and self.apply_fix(fix):
                        self.log("✅", "Fix applied — retrying...")
                        self.retry_count += 1
                        files_content = self.scan_project_files()
                        continue
                    else:
                        self.log("❌", "AI fix could not be applied")
                        self.retry_count += 1
                        continue

                # Still alive after startup window — healthy
                if process.poll() is None:
                    self.log("✅", "Project is running successfully!")
                    process.wait()
                    return True

            except KeyboardInterrupt:
                self.log("🛑", "Interrupted")
                return False
            except Exception as e:
                self.log("❌", f"Execution error: {e}")
                self.retry_count += 1

        self.log("❌", f"Failed after {self.config.max_retries} attempts")
        return False


if __name__ == "__main__":
    agent = AIAgent()
    sys.exit(0 if agent.run_with_healing() else 1)
