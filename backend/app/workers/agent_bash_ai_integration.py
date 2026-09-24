"""
AI Integration for Agent Bash Executor
Provides AI agents with natural language interface to execute bash commands
and gather context from their containers.
"""
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

from agent_bash_executor import AgentBashExecutor, BashExecutionResult, create_bash_executor
from app.integrations.llm import llm_gateway

logger = logging.getLogger(__name__)


class AIBashInterface:
    """
    Natural language interface for AI agents to execute bash commands
    and gather context from their containers.
    """
    
    def __init__(self, executor: AgentBashExecutor, agent_id: str):
        self.executor = executor
        self.agent_id = agent_id
        self.conversation_history: List[Dict[str, str]] = []
    
    async def process_ai_request(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a natural language request from the AI to execute bash commands.
        
        Args:
            request: Natural language request (e.g., "find all Python files")
            context: Additional context about the task
            
        Returns:
            Dict with execution results and AI interpretation
        """
        logger.info(f"AI bash request from {self.agent_id}: {request[:100]}")
        
        # Generate bash commands from natural language
        commands = await self._generate_commands_from_request(request, context)
        
        if not commands:
            return {
                "success": False,
                "error": "Could not generate commands from request",
                "request": request
            }
        
        # Execute commands
        results = []
        for cmd in commands:
            result = await self.executor.execute_command(cmd["command"], timeout=cmd.get("timeout", 60))
            results.append({
                "command": cmd["command"],
                "description": cmd.get("description", ""),
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration
            })
        
        # Interpret results with AI
        interpretation = await self._interpret_results(request, results, context)
        
        return {
            "success": all(r["success"] for r in results),
            "request": request,
            "commands_executed": len(results),
            "results": results,
            "interpretation": interpretation,
            "agent_id": self.agent_id
        }
    
    async def _generate_commands_from_request(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use AI to generate bash commands from natural language request.
        """
        system_prompt = """You are a bash command generator for AI agents working in Docker containers.
Generate safe, efficient bash commands based on natural language requests.

Available tools and commands:
- find: Search for files and directories
- grep: Search within files
- tree: Display directory structure
- cat/head/tail: Read file contents
- ls: List files
- wc: Count lines/words
- file: Determine file type
- git: Git operations
- sed/awk: Text processing

IMPORTANT RULES:
1. Generate ONLY safe read-only commands unless explicitly asked to modify
2. Use proper escaping and quoting
3. Include error handling (|| true for non-critical commands)
4. Limit output size (use head/tail when appropriate)
5. Exclude common directories: .git, node_modules, __pycache__, venv, .venv

Return a JSON array of command objects with this structure:
[
  {
    "command": "the bash command",
    "description": "what this command does",
    "timeout": 60
  }
]

Return ONLY the JSON array, no other text."""

        user_prompt = f"""Generate bash commands for this request:
{request}

Context:
- Working directory: {self.executor.working_dir}
- Container: {self.executor.container_name}
"""
        
        if context:
            user_prompt += f"\nAdditional context:\n{json.dumps(context, indent=2)}"
        
        try:
            response = await llm_gateway.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=llm_gateway.resolve_model(),
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.get("content", "").strip()
            
            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            commands = json.loads(content)
            
            if not isinstance(commands, list):
                logger.error(f"AI returned non-list: {commands}")
                return []
            
            logger.info(f"Generated {len(commands)} commands from request")
            return commands
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}\nResponse: {content}")
            return []
        except Exception as e:
            logger.error(f"Failed to generate commands: {e}")
            return []
    
    async def _interpret_results(
        self,
        request: str,
        results: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Use AI to interpret command execution results.
        """
        system_prompt = """You are an AI assistant helping interpret bash command results.
Provide clear, concise summaries of what was found and what it means for the task.

Focus on:
1. Key findings and insights
2. Relevant files and their purposes
3. Potential issues or concerns
4. Recommendations for next steps

Be concise but informative."""

        # Prepare results summary (truncate large outputs)
        results_summary = []
        for r in results:
            stdout_preview = r["stdout"][:2000] if r["stdout"] else ""
            stderr_preview = r["stderr"][:500] if r["stderr"] else ""
            
            results_summary.append({
                "command": r["command"],
                "description": r.get("description", ""),
                "success": r["success"],
                "stdout": stdout_preview + ("..." if len(r["stdout"]) > 2000 else ""),
                "stderr": stderr_preview + ("..." if len(r["stderr"]) > 500 else ""),
            })
        
        user_prompt = f"""Original request: {request}

Command execution results:
{json.dumps(results_summary, indent=2)}

Please interpret these results and provide insights."""
        
        if context:
            user_prompt += f"\n\nTask context:\n{json.dumps(context, indent=2)}"
        
        try:
            response = await llm_gateway.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=llm_gateway.resolve_model(),
                temperature=0.5,
                max_tokens=800
            )
            
            return response.get("content", "").strip()
            
        except Exception as e:
            logger.error(f"Failed to interpret results: {e}")
            return "Could not interpret results"
    
    # ── Predefined AI Actions ───────────────────────────────────────────────
    
    async def analyze_codebase(self) -> Dict[str, Any]:
        """AI-driven codebase analysis."""
        request = """Analyze this codebase:
1. Get the folder structure
2. Identify the main programming languages
3. Find configuration files
4. Count lines of code by file type
5. Check for dependency files"""
        
        return await self.process_ai_request(request)
    
    async def find_relevant_files(self, task_description: str) -> Dict[str, Any]:
        """Find files relevant to a specific task."""
        request = f"""Find files relevant to this task: {task_description}

Search for:
1. Files with related names
2. Files containing relevant keywords
3. Configuration files that might be affected
4. Test files related to this functionality"""
        
        return await self.process_ai_request(
            request,
            context={"task": task_description}
        )
    
    async def investigate_error(self, error_message: str) -> Dict[str, Any]:
        """Investigate an error by searching the codebase."""
        request = f"""Investigate this error: {error_message}

1. Search for the error message in the codebase
2. Find files that might be causing it
3. Check for related imports or dependencies
4. Look for similar error patterns"""
        
        return await self.process_ai_request(
            request,
            context={"error": error_message}
        )
    
    async def get_file_context(self, file_path: str) -> Dict[str, Any]:
        """Get comprehensive context about a file."""
        request = f"""Get context about file: {file_path}

1. Show file info (size, type, line count)
2. Read the file content
3. Find related files (imports, similar names)
4. Check git history for this file"""
        
        return await self.process_ai_request(
            request,
            context={"file": file_path}
        )


# ── Integration with Agent Service ──────────────────────────────────────────

_bash_executors: Dict[str, AgentBashExecutor] = {}
_ai_interfaces: Dict[str, AIBashInterface] = {}


def get_bash_executor(container_name: str, working_dir: str = "/workspace") -> AgentBashExecutor:
    """Get or create a bash executor for a container."""
    if container_name not in _bash_executors:
        _bash_executors[container_name] = create_bash_executor(container_name, working_dir)
    return _bash_executors[container_name]


def get_ai_bash_interface(
    container_name: str,
    agent_id: str,
    working_dir: str = "/workspace"
) -> AIBashInterface:
    """Get or create an AI bash interface for an agent."""
    key = f"{agent_id}:{container_name}"
    if key not in _ai_interfaces:
        executor = get_bash_executor(container_name, working_dir)
        _ai_interfaces[key] = AIBashInterface(executor, agent_id)
    return _ai_interfaces[key]


def cleanup_bash_executor(container_name: str):
    """Clean up bash executor when container is removed."""
    if container_name in _bash_executors:
        del _bash_executors[container_name]
    
    # Clean up AI interfaces for this container
    keys_to_remove = [k for k in _ai_interfaces if k.endswith(f":{container_name}")]
    for key in keys_to_remove:
        del _ai_interfaces[key]


# ── Example Usage ────────────────────────────────────────────────────────────

async def example_usage():
    """Example of how to use the AI bash interface."""
    
    # Create executor
    executor = create_bash_executor("agent_container_01", "/workspace")
    
    # Direct command execution
    result = await executor.execute_command("find . -name '*.py' | head -10")
    print(f"Found Python files:\n{result.stdout}")
    
    # Get folder structure
    structure = await executor.get_folder_structure(max_depth=2)
    print(f"Folder structure:\n{structure.stdout}")
    
    # Search for pattern
    grep_result = await executor.grep_files("def main", file_pattern="*.py")
    print(f"Found main functions:\n{grep_result.stdout}")
    
    # AI-powered interface
    ai_interface = AIBashInterface(executor, "agent_01")
    
    # Natural language request
    analysis = await ai_interface.process_ai_request(
        "Find all configuration files and show their contents"
    )
    print(f"AI Analysis:\n{analysis['interpretation']}")
    
    # Predefined actions
    codebase_analysis = await ai_interface.analyze_codebase()
    print(f"Codebase analysis:\n{codebase_analysis['interpretation']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
