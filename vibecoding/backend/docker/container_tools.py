#!/usr/bin/env python3
"""
Lightweight tool system for Docker container AI agent.
Provides structured file modification tools without external dependencies.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ContainerTools:
    """Lightweight file modification tools for container AI agent."""
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
    
    def write_file(self, path: str, content: str, create_dirs: bool = True) -> Dict[str, Any]:
        """Create or overwrite a file."""
        try:
            file_path = self.workspace_dir / path
            
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "path": path,
                "message": f"File written: {path}",
                "size": len(content)
            }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }
    
    def modify_file(self, path: str, search: str, replace: str, occurrence: int = 1) -> Dict[str, Any]:
        """Find and replace text in a file."""
        try:
            file_path = self.workspace_dir / path
            
            if not file_path.exists():
                return {
                    "success": False,
                    "path": path,
                    "error": f"File not found: {path}"
                }
            
            content = file_path.read_text(encoding='utf-8')
            
            if search not in content:
                return {
                    "success": False,
                    "path": path,
                    "error": f"Search text not found in {path}"
                }
            
            if occurrence == 0:
                # Replace all occurrences
                new_content = content.replace(search, replace)
                count = content.count(search)
            else:
                # Replace specific occurrence
                parts = content.split(search, occurrence)
                if len(parts) <= occurrence:
                    return {
                        "success": False,
                        "path": path,
                        "error": f"Occurrence {occurrence} not found"
                    }
                new_content = search.join(parts[:occurrence]) + replace + search.join(parts[occurrence:])
                count = 1
            
            file_path.write_text(new_content, encoding='utf-8')
            
            return {
                "success": True,
                "path": path,
                "message": f"Modified {path} ({count} replacement(s))",
                "replacements": count
            }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }
    
    def read_file(self, path: str, start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
        """Read file content."""
        try:
            file_path = self.workspace_dir / path
            
            if not file_path.exists():
                return {
                    "success": False,
                    "path": path,
                    "error": f"File not found: {path}"
                }
            
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            if end_line == -1:
                end_line = len(lines)
            
            selected_lines = lines[start_line-1:end_line]
            selected_content = '\n'.join(selected_lines)
            
            return {
                "success": True,
                "path": path,
                "content": selected_content,
                "total_lines": len(lines),
                "returned_lines": len(selected_lines)
            }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }
    
    def list_files(self, directory: str = "", pattern: str = "*") -> Dict[str, Any]:
        """List files in a directory."""
        try:
            if directory:
                search_dir = self.workspace_dir / directory
            else:
                search_dir = self.workspace_dir
            
            if not search_dir.exists():
                return {
                    "success": False,
                    "directory": directory,
                    "error": f"Directory not found: {directory}"
                }
            
            files = []
            for item in search_dir.glob(pattern):
                rel_path = str(item.relative_to(self.workspace_dir))
                files.append({
                    "path": rel_path,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0
                })
            
            return {
                "success": True,
                "directory": directory or ".",
                "pattern": pattern,
                "files": files,
                "count": len(files)
            }
        except Exception as e:
            return {
                "success": False,
                "directory": directory,
                "error": str(e)
            }
    
    def delete_file(self, path: str) -> Dict[str, Any]:
        """Delete a file."""
        try:
            file_path = self.workspace_dir / path
            
            if not file_path.exists():
                return {
                    "success": False,
                    "path": path,
                    "error": f"File not found: {path}"
                }
            
            if file_path.is_dir():
                import shutil
                shutil.rmtree(file_path)
                item_type = "directory"
            else:
                file_path.unlink()
                item_type = "file"
            
            return {
                "success": True,
                "path": path,
                "message": f"Deleted {item_type}: {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }


# Tool definitions for AI (OpenAI function calling format)
CONTAINER_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file (e.g., 'src/App.jsx')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete file content"
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "Create parent directories if needed (default: true)",
                        "default": True
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_file",
            "description": "Find and replace text within a file. Search text must match exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file"
                    },
                    "search": {
                        "type": "string",
                        "description": "Exact text to find"
                    },
                    "replace": {
                        "type": "string",
                        "description": "Text to replace with"
                    },
                    "occurrence": {
                        "type": "integer",
                        "description": "Which occurrence to replace (1=first, 0=all)",
                        "default": 1
                    }
                },
                "required": ["path", "search", "replace"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file content to understand structure before modifying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start reading from this line (1-indexed)",
                        "default": 1
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Stop at this line (-1 = end of file)",
                        "default": -1
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path (empty = workspace root)",
                        "default": ""
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '*.jsx', '**/*.py')",
                        "default": "*"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to delete"
                    }
                },
                "required": ["path"]
            }
        }
    }
]


def execute_tool(tool_name: str, arguments: Dict[str, Any], workspace_dir: str) -> str:
    """Execute a tool and return JSON result."""
    tools = ContainerTools(workspace_dir)
    
    tool_map = {
        "write_file": tools.write_file,
        "modify_file": tools.modify_file,
        "read_file": tools.read_file,
        "list_files": tools.list_files,
        "delete_file": tools.delete_file
    }
    
    handler = tool_map.get(tool_name)
    if not handler:
        return json.dumps({
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        })
    
    try:
        result = handler(**arguments)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        })
