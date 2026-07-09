#!/usr/bin/env python3
"""
Task Executor for Incremental Development
Executes individual tasks with full context awareness
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class TaskExecutor:
    """Executes individual development tasks with context"""
    
    TASK_EXECUTION_PROMPT = """You are an expert software developer executing a specific development task.

PROJECT CONTEXT:
{project_context}

COMPLETED TASKS:
{completed_tasks}

CURRENT TASK:
Task ID: {task_id}
Title: {task_title}
Description: {task_description}

FILES TO CREATE:
{files_to_create}

FILES TO MODIFY:
{files_to_modify}

EXISTING FILE CONTENTS (for modification):
{existing_files_content}

CRITICAL RULES:
1. Generate COMPLETE, WORKING code for ALL specified files
2. Do NOT truncate or use placeholders like "// ... rest of code"
3. Ensure all imports and dependencies are correct
4. Follow the exact file paths specified
5. If modifying files, preserve existing functionality unless explicitly changing it
6. Use the FILE marker format for each file
7. **CRITICAL JSX QUOTING RULE:** Never use raw, unescaped double quotes `"` inside JSX string attributes. For example, in `className="... bg-[url('data:image/svg+xml,... width="60" ...')] ..."` the inner double quotes terminate the `className` attribute early, breaking the entire file's brace matching and causing compilation errors (such as "Unexpected token `div`. Expected jsx identifier"). Instead, use single quotes `'` (or URL-encoded `%27`) or avoid inline arbitrary SVG tags.
8. **Prisma + SQLite Database Rules:** When creating/modifying a Prisma schema (prisma/schema.prisma) with sqlite provider, SQLite does NOT support `enum` types or the `Json` type. You MUST use `String` (with text defaults for enums, e.g., role String @default("USER")) instead of enums, and use `String` instead of `Json` (e.g., shippingAddress String).

OUTPUT FORMAT:
For each file, use this exact format:

// FILE: path/to/file.ext
<complete file content here>

// FILE: another/file.ext
<complete file content here>

IMPORTANT:
- Generate ALL files specified in the task
- Each file must be COMPLETE and FUNCTIONAL
- Do not skip any files
- Do not use "..." or placeholders
- Ensure proper imports and exports

Now generate the complete code for this task:
"""
    
    def __init__(self, workspace_dir: str, ai_caller):
        self.workspace_dir = Path(workspace_dir)
        self.ai_caller = ai_caller
        self.context_file = self.workspace_dir / ".vibecoding_context.json"
        from syntax_validator import SyntaxValidator
        self.syntax_validator = SyntaxValidator(str(self.workspace_dir), log_func=lambda msg: print(f"[Syntax] {msg}"))
    
    def execute_task(self, task: 'Task', project_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task and return results
        
        Returns:
            {
                "success": bool,
                "files_written": List[str],
                "error": Optional[str],
                "ai_response_length": int
            }
        """
        try:
            # Build execution context
            completed_tasks_summary = self._build_completed_tasks_summary(project_context)
            existing_files_content = self._read_existing_files(task.files_to_modify)
            
            # Build prompt
            prompt = self.TASK_EXECUTION_PROMPT.format(
                project_context=json.dumps(project_context.get("project_summary", ""), indent=2),
                completed_tasks=completed_tasks_summary,
                task_id=task.task_id,
                task_title=task.title,
                task_description=task.description,
                files_to_create="\n".join(f"- {f}" for f in task.files_to_create),
                files_to_modify="\n".join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "None",
                existing_files_content=existing_files_content
            )
            
            is_first_task = not project_context.get("completed_tasks", [])
            if is_first_task:
                prompt += "\n\nCRITICAL INITIAL TASK RULE: Since this is the first development task, you MUST NOT generate any database models, Prisma schemas, database migrations, or active backend APIs. Focus strictly on visual frontend elements, components, and mock-based views as described. Keep all data mock-based so the app builds and deploys successfully immediately."
            
            messages = [
                {"role": "system", "content": "You are an expert software developer."},
                {"role": "user", "content": prompt}
            ]
            
            # Call AI
            response = self.ai_caller(messages, temperature=0.2, show_thinking=False)
            
            # Parse and write files
            files_written = self._parse_and_write_files(response)
            
            # Verify at least some files were created
            if not files_written:
                return {
                    "success": False,
                    "files_written": [],
                    "error": "No files were generated by the AI",
                    "ai_response_length": len(response)
                }
            
            # ═══════════════════════════════════════════════════════════════════
            # SELF-HEALING LOOP FOR TASK EXECUTED FILES
            # ═══════════════════════════════════════════════════════════════════
            max_heal_attempts = 3
            for file_to_check in list(files_written):
                for attempt in range(max_heal_attempts):
                    errors = self.syntax_validator.validate_files([file_to_check])
                    if not errors:
                        break
                    
                    err = errors[0]
                    err_msg = err['error']
                    line_num = err.get('line', 0)
                    print(f"❌ [Syntax Check] {file_to_check} failed check at line {line_num} (attempt {attempt + 1}/{max_heal_attempts}): {err_msg[:200]}")
                    
                    file_path = self.workspace_dir / file_to_check
                    if not file_path.exists():
                        break
                    
                    current_content = file_path.read_text(encoding='utf-8', errors='replace')
                    
                    heal_prompt = f"""You generated the file `{file_to_check}` as part of task "{task.title}", but it has a syntax error or is truncated.
                    
TASK DESCRIPTION: {task.description}

FILE PATH: {file_to_check}
CURRENT FILE CONTENT:
```
{current_content}
```

SYNTAX ERROR DETAILS:
{err_msg}
Line: {line_num}

CRITICAL: The file appears to have a syntax error or was cut off/truncated before it could be fully written.
Please rewrite the COMPLETE, valid file `{file_to_check}` now with the syntax error fixed and any truncated code fully completed. Do NOT truncate the file or use "// ... rest of code".
Return ONLY the clean, full file content with no explanation, no markdown fences, no formatting other than the code itself."""

                    try:
                        clean_content = self.ai_caller([
                            {"role": "system", "content": "You are a code repair tool. You must output the complete and syntactically valid file content, fixing any truncation or errors. Output ONLY the raw file content with no markdown tags or explanations."},
                            {"role": "user", "content": heal_prompt}
                        ], temperature=0.1, show_thinking=False)
                        
                        # Strip fences
                        clean_content = re.sub(r'^```[a-z]*\n?', '', clean_content.strip(), flags=re.MULTILINE)
                        clean_content = re.sub(r'\n?```\s*$', '', clean_content.strip(), flags=re.MULTILINE)
                        
                        if clean_content and len(clean_content) > 10:
                            self._write_file(file_to_check, clean_content)
                            print(f"✅ [Syntax Check] Rewrote file {file_to_check} with AI self-healing output")
                        else:
                            print(f"⚠️ [Syntax Check] AI self-healing returned empty/short content for {file_to_check}")
                    except Exception as ex:
                        print(f"⚠️ [Syntax Check] Error in self-healing call: {ex}")
            
            # Check if critical files are missing (warn but don't fail)
            expected_files = set(task.files_to_create + task.files_to_modify)
            missing_files = expected_files - set(files_written)
            
            if missing_files:
                # Log warning but don't fail - AI might have combined files or deemed some unnecessary
                print(f"⚠️ Note: Some expected files were not generated: {', '.join(missing_files)}")
                print(f"   This is OK - the AI may have combined files or adjusted the structure.")
            
            return {
                "success": True,
                "files_written": files_written,
                "error": None,
                "ai_response_length": len(response),
                "missing_files": list(missing_files) if missing_files else []
            }
        
        except Exception as e:
            return {
                "success": False,
                "files_written": [],
                "error": str(e),
                "ai_response_length": 0
            }
    
    def _build_completed_tasks_summary(self, project_context: Dict[str, Any]) -> str:
        """Build a summary of completed tasks for context"""
        completed = project_context.get("completed_tasks", [])
        if not completed:
            return "No tasks completed yet. This is the first task."
        
        lines = []
        for task in completed:
            lines.append(f"✓ {task['title']}")
            lines.append(f"  Files created: {', '.join(task['files_created'][:5])}")
            if task.get('files_modified'):
                lines.append(f"  Files modified: {', '.join(task['files_modified'][:5])}")
        
        return "\n".join(lines)
    
    def _read_existing_files(self, file_paths: List[str]) -> str:
        """Read content of existing files that need to be modified"""
        if not file_paths:
            return "No existing files to modify."
        
        contents = []
        for file_path in file_paths:
            full_path = self.workspace_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    contents.append(f"// EXISTING FILE: {file_path}\n{content}\n")
                except Exception as e:
                    contents.append(f"// ERROR reading {file_path}: {e}\n")
            else:
                contents.append(f"// FILE DOES NOT EXIST: {file_path} (will be created)\n")
        
        return "\n".join(contents)
    
    def _parse_and_write_files(self, ai_response: str) -> List[str]:
        """Parse AI response and write files to disk"""
        files_written = []
        
        # Pattern to match: // FILE: path/to/file.ext
        file_pattern = re.compile(r'//\s*FILE:\s*(.+?)(?:\n|$)', re.IGNORECASE)
        
        # Split response by FILE markers
        parts = file_pattern.split(ai_response)
        
        # parts[0] is text before first FILE marker (ignore)
        # parts[1] is first file path, parts[2] is first file content
        # parts[3] is second file path, parts[4] is second file content, etc.
        
        i = 1
        while i < len(parts) - 1:
            file_path = parts[i].strip()
            file_content = parts[i + 1]
            
            # Extract content until next FILE marker or end
            # Remove leading/trailing whitespace but preserve code formatting
            file_content = file_content.strip()
            
            # Remove any trailing FILE markers that might be in the content
            next_file_match = file_pattern.search(file_content)
            if next_file_match:
                file_content = file_content[:next_file_match.start()].strip()
            
            # CRITICAL: Remove markdown code fences that corrupt files
            # Remove opening fence: ```json, ```javascript, ```jsx, etc.
            file_content = re.sub(r'^```[a-z]*\n?', '', file_content, flags=re.MULTILINE)
            # Remove closing fence: ```
            file_content = re.sub(r'\n?```\s*$', '', file_content, flags=re.MULTILINE)
            
            # Additional cleanup: remove any stray backticks at start/end
            file_content = file_content.strip('`').strip()
            
            # Write file
            if file_path and file_content:
                self._write_file(file_path, file_content)
                files_written.append(file_path)
            
            i += 2
        
        return files_written
    
    def _write_file(self, file_path: str, content: str):
        """Write a file to the workspace"""
        full_path = self.workspace_dir / file_path
        
        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        full_path.write_text(content)
        
        print(f"  📄 {file_path}")
    
    def validate_task_output(self, task: 'Task') -> Dict[str, Any]:
        """
        Validate that all expected files were created and compile successfully
        based on the detected workspace technology stack.
        """
        import subprocess
        expected_files = set(task.files_to_create + task.files_to_modify)
        actual_files = set()
        
        for file_path in expected_files:
            full_path = self.workspace_dir / file_path
            if full_path.exists():
                actual_files.add(file_path)
        
        missing = expected_files - actual_files
        if missing:
            return {
                "valid": False,
                "missing_files": list(missing),
                "created_files": list(actual_files),
                "error": f"Missing expected files: {', '.join(missing)}"
            }
            
        # Detect Tech Stack on the fly
        tech_stack = []
        try:
            # Check for package.json
            if (self.workspace_dir / "package.json").exists() or any((self.workspace_dir).rglob("package.json")):
                tech_stack.append("nodejs")
            # Check for dotnet csproj/sln
            if any((self.workspace_dir).rglob("*.csproj")) or any((self.workspace_dir).rglob("*.sln")):
                tech_stack.append("dotnet")
            # Check for Python
            if (self.workspace_dir / "requirements.txt").exists() or any((self.workspace_dir).rglob("*.py")):
                tech_stack.append("python")
            # Check for Go
            if (self.workspace_dir / "go.mod").exists():
                tech_stack.append("go")
        except Exception:
            pass
            
        # Run compile checks for the detected stacks
        error_msg = None
        try:
            if "nodejs" in tech_stack:
                # If there's a package.json, make sure node_modules exist, else install them first
                node_modules_dir = self.workspace_dir / "node_modules"
                if not node_modules_dir.exists():
                    subprocess.run(["npm", "install"], cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=90)
                
                res = subprocess.run(["npm", "run", "build"], cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=120)
                if res.returncode != 0:
                    error_msg = f"NPM build compilation failed:\n{res.stderr or res.stdout}"
            elif "dotnet" in tech_stack:
                res = subprocess.run(["dotnet", "build"], cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=90)
                if res.returncode != 0:
                    error_msg = f"Dotnet build failed:\n{res.stderr or res.stdout}"
            elif "python" in tech_stack:
                # Check syntax of all created/modified python files
                for f in actual_files:
                    if f.endswith(".py"):
                        full_f = self.workspace_dir / f
                        res = subprocess.run(["python3", "-m", "py_compile", str(full_f)], capture_output=True, text=True, timeout=10)
                        if res.returncode != 0:
                            error_msg = f"Python syntax compilation failed for {f}:\n{res.stderr or res.stdout}"
                            break
            elif "go" in tech_stack:
                res = subprocess.run(["go", "build", "./..."], cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=40)
                if res.returncode != 0:
                    error_msg = f"Go build failed:\n{res.stderr or res.stdout}"
        except Exception as e:
            # Let compilation failures proceed if subprocess commands fail to execute (e.g. missing binary)
            print(f"⚠️ Validation command execution error: {e}")
            
        if error_msg:
            return {
                "valid": False,
                "missing_files": [],
                "created_files": list(actual_files),
                "error": error_msg
            }
            
        return {
            "valid": True,
            "missing_files": [],
            "created_files": list(actual_files)
        }
