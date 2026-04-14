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
            
            messages = [
                {"role": "system", "content": "You are an expert software developer."},
                {"role": "user", "content": prompt}
            ]
            
            # Call AI
            response = self.ai_caller(messages, temperature=0.2, show_thinking=False)
            
            # Parse and write files
            files_written = self._parse_and_write_files(response)
            
            # Verify all expected files were created
            expected_files = set(task.files_to_create + task.files_to_modify)
            missing_files = expected_files - set(files_written)
            
            if missing_files:
                return {
                    "success": False,
                    "files_written": files_written,
                    "error": f"Missing files: {', '.join(missing_files)}",
                    "ai_response_length": len(response)
                }
            
            return {
                "success": True,
                "files_written": files_written,
                "error": None,
                "ai_response_length": len(response)
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
        Validate that all expected files were created
        
        Returns:
            {
                "valid": bool,
                "missing_files": List[str],
                "extra_files": List[str]
            }
        """
        expected_files = set(task.files_to_create + task.files_to_modify)
        actual_files = set()
        
        for file_path in expected_files:
            full_path = self.workspace_dir / file_path
            if full_path.exists():
                actual_files.add(file_path)
        
        missing = expected_files - actual_files
        
        return {
            "valid": len(missing) == 0,
            "missing_files": list(missing),
            "created_files": list(actual_files)
        }
