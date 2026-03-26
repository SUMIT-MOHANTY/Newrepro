"""
Agent Bash Executor Service
Enables AI agents to execute bash scripts and Linux commands inside Docker containers
with full context-gathering capabilities (grep, find, tree, file reading, etc.)
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BashExecutionResult:
    """Result of a bash command execution"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    command: str
    error: Optional[str] = None


class AgentBashExecutor:
    """
    Provides AI agents with the ability to execute bash scripts and commands
    inside their Docker containers for context gathering and file operations.
    """
    
    def __init__(self, container_name: str, working_dir: str = "/workspace"):
        self.container_name = container_name
        self.working_dir = working_dir
        self.execution_history: List[BashExecutionResult] = []
        
    async def execute_command(
        self,
        command: str,
        timeout: int = 60,
        capture_output: bool = True,
        working_dir: Optional[str] = None
    ) -> BashExecutionResult:
        """
        Execute a single bash command inside the container.
        
        Args:
            command: The bash command to execute
            timeout: Maximum execution time in seconds
            capture_output: Whether to capture stdout/stderr
            working_dir: Override the default working directory
            
        Returns:
            BashExecutionResult with execution details
        """
        start_time = time.time()
        work_dir = working_dir or self.working_dir
        
        logger.info(f"Executing command in {self.container_name}: {command[:100]}")
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", "-w", work_dir, self.container_name, "bash", "-c", command],
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            
            duration = time.time() - start_time
            
            execution_result = BashExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                duration=duration,
                command=command
            )
            
            self.execution_history.append(execution_result)
            
            if not execution_result.success:
                logger.warning(
                    f"Command failed (exit {result.returncode}): {command[:100]}\n"
                    f"stderr: {result.stderr[:200]}"
                )
            
            return execution_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            error_result = BashExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration=duration,
                command=command,
                error="timeout"
            )
            self.execution_history.append(error_result)
            return error_result
            
        except Exception as e:
            duration = time.time() - start_time
            error_result = BashExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
                command=command,
                error=str(e)
            )
            self.execution_history.append(error_result)
            return error_result
    
    async def execute_script(
        self,
        script: str,
        script_name: str = "agent_script",
        timeout: int = 180,
        working_dir: Optional[str] = None
    ) -> BashExecutionResult:
        """
        Execute a multi-line bash script inside the container.
        
        Args:
            script: The bash script content
            script_name: Name for the script file
            timeout: Maximum execution time in seconds
            working_dir: Override the default working directory
            
        Returns:
            BashExecutionResult with execution details
        """
        start_time = time.time()
        work_dir = working_dir or self.working_dir
        
        logger.info(f"Executing script '{script_name}' in {self.container_name}")
        
        # Clean the script
        cleaned_script = self._clean_script(script)
        
        # Write to local temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sh",
            delete=False,
            prefix=f"{script_name}_",
            encoding="utf-8",
            newline='\n'
        ) as f:
            f.write(cleaned_script)
            local_script_path = f.name
        
        script_filename = os.path.basename(local_script_path)
        container_script_path = f"/tmp/{script_filename}"
        
        try:
            # Copy script to container
            cp_result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "cp", local_script_path, f"{self.container_name}:{container_script_path}"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if cp_result.returncode != 0:
                return BashExecutionResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Failed to copy script to container: {cp_result.stderr}",
                    duration=time.time() - start_time,
                    command=script[:100],
                    error="copy_failed"
                )
            
            # Make executable
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", self.container_name, "chmod", "+x", container_script_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Execute script
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", "-w", work_dir, self.container_name, "/bin/bash", container_script_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Clean up script in container
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", self.container_name, "rm", "-f", container_script_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            duration = time.time() - start_time
            
            execution_result = BashExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                duration=duration,
                command=f"script:{script_name}"
            )
            
            self.execution_history.append(execution_result)
            return execution_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return BashExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Script timed out after {timeout}s",
                duration=duration,
                command=f"script:{script_name}",
                error="timeout"
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return BashExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
                command=f"script:{script_name}",
                error=str(e)
            )
            
        finally:
            # Clean up local temp file
            try:
                os.unlink(local_script_path)
            except OSError:
                pass
    
    # ── Context Gathering Commands ──────────────────────────────────────────
    
    async def get_folder_structure(
        self,
        path: str = ".",
        max_depth: int = 3,
        exclude_patterns: Optional[List[str]] = None
    ) -> BashExecutionResult:
        """
        Get the folder structure using tree or find command.
        
        Args:
            path: Path to analyze (relative to working_dir)
            max_depth: Maximum depth to traverse
            exclude_patterns: Patterns to exclude (e.g., ['node_modules', '.git'])
        """
        exclude_patterns = exclude_patterns or [
            '.git', '__pycache__', 'node_modules', 'venv', '.venv',
            'dist', 'build', '*.pyc', '.DS_Store'
        ]
        
        # Try tree command first (more readable)
        tree_excludes = " ".join(f"-I '{pattern}'" for pattern in exclude_patterns)
        tree_cmd = f"tree -L {max_depth} {tree_excludes} {path} 2>/dev/null"
        
        result = await self.execute_command(tree_cmd, timeout=30)
        
        if result.success:
            return result
        
        # Fallback to find command
        find_excludes = " ".join(
            f"-not -path '*/{pattern}/*'" for pattern in exclude_patterns
        )
        find_cmd = f"find {path} -maxdepth {max_depth} -type f {find_excludes} | sort"
        
        return await self.execute_command(find_cmd, timeout=30)
    
    async def grep_files(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = "*",
        recursive: bool = True,
        case_sensitive: bool = False,
        context_lines: int = 2
    ) -> BashExecutionResult:
        """
        Search for a pattern in files using grep.
        
        Args:
            pattern: The pattern to search for
            path: Path to search in
            file_pattern: File pattern to match (e.g., '*.py')
            recursive: Whether to search recursively
            case_sensitive: Whether search is case-sensitive
            context_lines: Number of context lines to show
        """
        grep_flags = ["-n"]  # Line numbers
        
        if recursive:
            grep_flags.append("-r")
        
        if not case_sensitive:
            grep_flags.append("-i")
        
        if context_lines > 0:
            grep_flags.append(f"-C {context_lines}")
        
        # Add color for better readability
        grep_flags.append("--color=never")
        
        flags_str = " ".join(grep_flags)
        
        if file_pattern != "*":
            cmd = f"grep {flags_str} '{pattern}' {path} --include='{file_pattern}' 2>/dev/null || true"
        else:
            cmd = f"grep {flags_str} '{pattern}' {path} 2>/dev/null || true"
        
        return await self.execute_command(cmd, timeout=60)
    
    async def read_file(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_lines: int = 1000
    ) -> BashExecutionResult:
        """
        Read a file or specific lines from a file.
        
        Args:
            file_path: Path to the file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (1-indexed)
            max_lines: Maximum number of lines to read
        """
        if start_line and end_line:
            cmd = f"sed -n '{start_line},{end_line}p' {file_path}"
        elif start_line:
            cmd = f"tail -n +{start_line} {file_path} | head -n {max_lines}"
        elif end_line:
            cmd = f"head -n {end_line} {file_path}"
        else:
            cmd = f"head -n {max_lines} {file_path}"
        
        return await self.execute_command(cmd, timeout=30)
    
    async def find_files(
        self,
        name_pattern: Optional[str] = None,
        path: str = ".",
        file_type: str = "f",
        max_depth: Optional[int] = None,
        exclude_dirs: Optional[List[str]] = None
    ) -> BashExecutionResult:
        """
        Find files matching criteria.
        
        Args:
            name_pattern: File name pattern (e.g., '*.py')
            path: Path to search in
            file_type: Type of file (f=file, d=directory, l=symlink)
            max_depth: Maximum depth to search
            exclude_dirs: Directories to exclude
        """
        exclude_dirs = exclude_dirs or ['.git', 'node_modules', '__pycache__', 'venv', '.venv']
        
        cmd_parts = ["find", path]
        
        if max_depth:
            cmd_parts.append(f"-maxdepth {max_depth}")
        
        # Add exclusions
        for exclude_dir in exclude_dirs:
            cmd_parts.append(f"-not -path '*/{exclude_dir}/*'")
        
        cmd_parts.append(f"-type {file_type}")
        
        if name_pattern:
            cmd_parts.append(f"-name '{name_pattern}'")
        
        cmd = " ".join(cmd_parts)
        
        return await self.execute_command(cmd, timeout=60)
    
    async def get_file_info(self, file_path: str) -> BashExecutionResult:
        """Get detailed information about a file."""
        cmd = f"ls -lh {file_path} && file {file_path} && wc -l {file_path} 2>/dev/null || true"
        return await self.execute_command(cmd, timeout=10)
    
    async def count_lines_of_code(
        self,
        path: str = ".",
        extensions: Optional[List[str]] = None
    ) -> BashExecutionResult:
        """
        Count lines of code by file type.
        
        Args:
            path: Path to analyze
            extensions: List of file extensions to count (e.g., ['py', 'js'])
        """
        if extensions:
            find_patterns = " -o ".join(f"-name '*.{ext}'" for ext in extensions)
            cmd = f"find {path} -type f \\( {find_patterns} \\) -not -path '*/node_modules/*' -not -path '*/.git/*' -exec wc -l {{}} + | sort -n"
        else:
            cmd = f"find {path} -type f -not -path '*/node_modules/*' -not -path '*/.git/*' -exec wc -l {{}} + | sort -n"
        
        return await self.execute_command(cmd, timeout=60)
    
    async def check_dependencies(self) -> BashExecutionResult:
        """Check for dependency files and their contents."""
        cmd = """
        echo "=== Python Dependencies ===" && \
        (test -f requirements.txt && cat requirements.txt || echo "No requirements.txt") && \
        echo "" && \
        echo "=== Node Dependencies ===" && \
        (test -f package.json && cat package.json || echo "No package.json") && \
        echo "" && \
        echo "=== Docker ===" && \
        (test -f Dockerfile && echo "Dockerfile found" || echo "No Dockerfile")
        """
        return await self.execute_command(cmd, timeout=30)
    
    async def get_git_info(self) -> BashExecutionResult:
        """Get git repository information."""
        cmd = """
        echo "=== Git Status ===" && \
        git status --short && \
        echo "" && \
        echo "=== Current Branch ===" && \
        git branch --show-current && \
        echo "" && \
        echo "=== Recent Commits ===" && \
        git log --oneline -5 && \
        echo "" && \
        echo "=== Modified Files ===" && \
        git diff --name-only
        """
        return await self.execute_command(cmd, timeout=30)
    
    # ── Utility Methods ──────────────────────────────────────────────────────
    
    def _clean_script(self, script: str) -> str:
        """Clean and normalize a bash script."""
        import re
        
        # Remove Windows line endings
        script = script.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove non-printable characters except newlines and tabs
        script = re.sub(r'[^\x20-\x7E\n\t]', '', script)
        
        # Split into lines and clean
        lines = script.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.rstrip()
            
            # Skip empty lines at the start
            if not line and len(cleaned_lines) == 0:
                continue
            
            cleaned_lines.append(line)
        
        # Add shebang and set -e if not present
        script_content = '\n'.join(cleaned_lines).strip()
        
        if not script_content.startswith('#!/'):
            script_content = f"#!/usr/bin/env bash\nset -e\n\n{script_content}"
        
        return script_content
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        recent = self.execution_history[-limit:] if limit else self.execution_history
        return [
            {
                "command": result.command[:100],
                "success": result.success,
                "exit_code": result.exit_code,
                "duration": round(result.duration, 2),
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
            }
            for result in recent
        ]
    
    def clear_history(self):
        """Clear execution history."""
        self.execution_history.clear()


# ── Factory Function ─────────────────────────────────────────────────────────

def create_bash_executor(
    container_name: str,
    working_dir: str = "/workspace"
) -> AgentBashExecutor:
    """
    Create a bash executor for an agent container.
    
    Args:
        container_name: Name of the Docker container
        working_dir: Default working directory
        
    Returns:
        AgentBashExecutor instance
    """
    return AgentBashExecutor(container_name, working_dir)
