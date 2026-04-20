"""
Example: How to integrate bash execution into agent workflows
This shows how agents can use bash commands to gather context and understand codebases.
"""
import asyncio
import logging
from agent_bash_executor import create_bash_executor
from agent_bash_ai_integration import get_ai_bash_interface

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_agent_workflow(container_name: str, agent_id: str, task_description: str):
    """
    Example workflow showing how an agent can use bash execution
    to gather context before implementing a task.
    """
    
    # Step 1: Create bash executor for the agent's container
    executor = create_bash_executor(container_name, "/workspace")
    
    # Step 2: Create AI interface for natural language commands
    ai_interface = get_ai_bash_interface(container_name, agent_id, "/workspace")
    
    logger.info(f"Agent {agent_id} starting task: {task_description}")
    
    # Step 3: Gather initial context about the codebase
    logger.info("=== Phase 1: Analyzing Codebase ===")
    
    # Get folder structure
    structure = await executor.get_folder_structure(max_depth=3)
    logger.info(f"Folder structure:\n{structure.stdout[:500]}")
    
    # Check what languages/frameworks are used
    deps = await executor.check_dependencies()
    logger.info(f"Dependencies:\n{deps.stdout[:500]}")
    
    # Get git status
    git_info = await executor.get_git_info()
    logger.info(f"Git info:\n{git_info.stdout[:500]}")
    
    # Step 4: Use AI to find relevant files for the task
    logger.info("=== Phase 2: Finding Relevant Files ===")
    
    relevant_files = await ai_interface.find_relevant_files(task_description)
    logger.info(f"AI found relevant files:\n{relevant_files['interpretation']}")
    
    # Step 5: Read specific files that AI identified
    logger.info("=== Phase 3: Reading Relevant Files ===")
    
    # Example: Read a specific file
    if relevant_files.get('results'):
        for result in relevant_files['results'][:3]:  # First 3 results
            if result.get('stdout'):
                # Parse filenames from grep output
                lines = result['stdout'].split('\n')[:5]
                for line in lines:
                    if ':' in line:
                        filepath = line.split(':')[0]
                        file_content = await executor.read_file(filepath, max_lines=50)
                        if file_content.success:
                            logger.info(f"File {filepath} (first 50 lines):\n{file_content.stdout[:300]}")
    
    # Step 6: Search for specific patterns
    logger.info("=== Phase 4: Searching for Patterns ===")
    
    # Example: Find all function definitions
    functions = await executor.grep_files(
        pattern="def ",
        file_pattern="*.py",
        recursive=True,
        context_lines=1
    )
    logger.info(f"Found {len(functions.stdout.split('def '))-1} function definitions")
    
    # Step 7: Use AI to analyze and provide recommendations
    logger.info("=== Phase 5: AI Analysis ===")
    
    analysis = await ai_interface.process_ai_request(
        f"Based on the codebase structure, recommend the best approach to implement: {task_description}"
    )
    logger.info(f"AI Recommendation:\n{analysis['interpretation']}")
    
    # Step 8: Get execution history
    history = executor.get_execution_history(limit=5)
    logger.info(f"Executed {len(history)} commands")
    for entry in history:
        logger.info(f"  - {entry['command'][:50]} (success={entry['success']}, duration={entry['duration']}s)")
    
    return {
        "success": True,
        "context_gathered": True,
        "relevant_files_found": len(relevant_files.get('results', [])),
        "ai_recommendation": analysis['interpretation']
    }


async def example_error_investigation(container_name: str, agent_id: str, error_message: str):
    """
    Example: How an agent can investigate an error using bash commands.
    """
    
    ai_interface = get_ai_bash_interface(container_name, agent_id, "/workspace")
    executor = ai_interface.executor
    
    logger.info(f"Agent {agent_id} investigating error: {error_message}")
    
    # Step 1: Search for the error message in the codebase
    logger.info("=== Searching for error in codebase ===")
    
    error_search = await executor.grep_files(
        pattern=error_message[:50],  # First 50 chars of error
        recursive=True,
        context_lines=3
    )
    
    if error_search.success and error_search.stdout:
        logger.info(f"Found error references:\n{error_search.stdout[:500]}")
    
    # Step 2: Use AI to investigate
    investigation = await ai_interface.investigate_error(error_message)
    logger.info(f"AI Investigation:\n{investigation['interpretation']}")
    
    # Step 3: Check recent changes that might have caused it
    recent_changes = await executor.execute_command(
        "git log --oneline -10 && git diff HEAD~5..HEAD --name-only"
    )
    logger.info(f"Recent changes:\n{recent_changes.stdout[:500]}")
    
    return {
        "success": True,
        "error_found_in_code": bool(error_search.stdout),
        "investigation": investigation['interpretation']
    }


async def example_direct_commands(container_name: str):
    """
    Example: Direct bash command execution without AI.
    """
    
    executor = create_bash_executor(container_name, "/workspace")
    
    logger.info("=== Executing Direct Commands ===")
    
    # Find all Python files
    py_files = await executor.execute_command(
        "find . -name '*.py' -type f | head -20"
    )
    logger.info(f"Python files:\n{py_files.stdout}")
    
    # Count lines of code
    loc = await executor.count_lines_of_code(extensions=['py', 'js'])
    logger.info(f"Lines of code:\n{loc.stdout[:500]}")
    
    # Check for TODO comments
    todos = await executor.execute_command(
        "grep -r 'TODO\\|FIXME\\|XXX' . --include='*.py' --include='*.js' | head -10"
    )
    logger.info(f"TODOs found:\n{todos.stdout}")
    
    # Get file statistics
    stats = await executor.execute_command(
        "find . -type f -name '*.py' | wc -l && find . -type f -name '*.js' | wc -l"
    )
    logger.info(f"File statistics:\n{stats.stdout}")
    
    return {"success": True}


async def example_script_execution(container_name: str):
    """
    Example: Execute a multi-line bash script.
    """
    
    executor = create_bash_executor(container_name, "/workspace")
    
    logger.info("=== Executing Bash Script ===")
    
    script = """
#!/bin/bash
set -e

echo "=== Project Analysis ==="
echo ""

echo "Python files:"
find . -name "*.py" -type f | wc -l

echo ""
echo "JavaScript files:"
find . -name "*.js" -o -name "*.jsx" | wc -l

echo ""
echo "Total lines of Python code:"
find . -name "*.py" -type f -exec wc -l {} + | tail -1

echo ""
echo "Configuration files:"
ls -1 *.json *.yaml *.yml *.toml 2>/dev/null || echo "None found"

echo ""
echo "=== Analysis Complete ==="
"""
    
    result = await executor.execute_script(script, "project_analysis")
    
    if result.success:
        logger.info(f"Script output:\n{result.stdout}")
    else:
        logger.error(f"Script failed:\n{result.stderr}")
    
    return {"success": result.success, "output": result.stdout}


# Main example
async def main():
    """
    Run all examples (requires a running container).
    """
    
    # Replace with actual container name
    container_name = "agent_dev_agent_1"
    agent_id = "dev_agent_1"
    
    print("\n" + "="*60)
    print("Example 1: Agent Workflow with Context Gathering")
    print("="*60)
    try:
        result1 = await example_agent_workflow(
            container_name,
            agent_id,
            "Add user authentication with JWT tokens"
        )
        print(f"Result: {result1}")
    except Exception as e:
        print(f"Example 1 failed: {e}")
    
    print("\n" + "="*60)
    print("Example 2: Error Investigation")
    print("="*60)
    try:
        result2 = await example_error_investigation(
            container_name,
            agent_id,
            "ModuleNotFoundError: No module named 'flask'"
        )
        print(f"Result: {result2}")
    except Exception as e:
        print(f"Example 2 failed: {e}")
    
    print("\n" + "="*60)
    print("Example 3: Direct Commands")
    print("="*60)
    try:
        result3 = await example_direct_commands(container_name)
        print(f"Result: {result3}")
    except Exception as e:
        print(f"Example 3 failed: {e}")
    
    print("\n" + "="*60)
    print("Example 4: Script Execution")
    print("="*60)
    try:
        result4 = await example_script_execution(container_name)
        print(f"Result: {result4}")
    except Exception as e:
        print(f"Example 4 failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
