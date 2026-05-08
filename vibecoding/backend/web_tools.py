"""
Web Tools Module for VibeCoding
Provides web search (DuckDuckGo) and page content fetching capabilities
that the AI model can invoke dynamically via function calling.

Uses:
- duckduckgo_search (AsyncDDGS) for web search
- httpx for async page fetching
- ai_config for AI API interaction
"""

import json
import re
import httpx
import asyncio
from typing import Dict, Any, List
from ddgs import DDGS
from ai_config import ai_config

# ──────────────────────────────────────────────
# Tool Definitions (OpenAI Function Calling Format)
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Use this when you need to find current information, documentation, examples, tutorials, or any real-time data from the internet to help answer the user's question or build their project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string. Be specific and descriptive for better results."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (1-10). Default is 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page_content",
            "description": "Fetch and extract the text content of a web page given its URL. Use this to read documentation, articles, code examples, or any web page content that was found via web_search or provided by the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the web page to fetch content from."
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum number of characters to return from the page content. Default is 8000.",
                        "default": 8000
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "patch",
            "description": "Apply targeted code patches to specific files using the // PATCH: filename block format. Use this for small tweaks, bug fixes, or style updates to existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "The patch content string following the // PATCH: file\\n<<<SEARCH\\n...\\n<<<REPLACE\\n... format."
                    }
                },
                "required": ["patch"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with complete content. Use this for new files or major rewrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file (e.g., 'src/components/Button.jsx')."
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete content of the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    }
]

# ──────────────────────────────────────────────
# Tool Implementations
# ──────────────────────────────────────────────

async def patch(patch: str) -> str:
    """Virtual tool that returns the patch string to the conversation aggregator."""
    return json.dumps({
        "status": "success",
        "message": "Patch received and queued for application.",
        "patch_content": patch[:100] + "..." if len(patch) > 100 else patch
    })

async def write_file(path: str, content: str) -> str:
    """Virtual tool that returns the file content string to the conversation aggregator."""
    return json.dumps({
        "status": "success",
        "message": f"File {path} received and queued for creation.",
        "content_preview": content[:100] + "..." if len(content) > 100 else content
    })

def _sync_web_search(query: str, max_results: int = 5) -> list:
    """Run DDGS text search synchronously."""
    ddgs = DDGS()
    return list(ddgs.text(query, max_results=max_results))

async def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo via the duckduckgo_search library.
    Returns structured JSON string of search results.
    """
    print(f"🔍 Web Search: '{query}' (max {max_results} results)")
    try:
        # Run the synchronous DDGS search in a separate thread so it doesn't block asyncio
        results = await asyncio.to_thread(_sync_web_search, query, max_results)

        formatted = [
            {"title": r["title"], "url": r["href"], "snippet": r["body"]}
            for r in results
        ]

        print(f"✅ Found {len(formatted)} results")
        return json.dumps({
            "status": "success",
            "query": query,
            "results_count": len(formatted),
            "results": formatted
        })
    except Exception as e:
        print(f"❌ Search error: {str(e)}")
        return json.dumps({
            "status": "error",
            "query": query,
            "message": f"Search failed: {str(e)}"
        })


async def fetch_page_content(url: str, max_length: int = 8000) -> str:
    """
    Fetch and extract text content from a web page using httpx (async).
    Strips HTML tags and returns clean text.
    """
    try:
        print(f"📄 Fetching page: {url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        content_type = response.headers.get('content-type', '')

        # If it's not HTML, return raw text (e.g., JSON, plain text)
        if 'html' not in content_type.lower():
            text = response.text[:max_length]
            return json.dumps({
                "status": "success",
                "url": url,
                "content_type": content_type,
                "content": text
            })

        html = response.text

        # Remove script, style, nav, footer, header tags and their content
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""

        # Extract meta description
        meta_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        description = meta_match.group(1) if meta_match else ""

        # Convert common block elements to newlines for readability
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'</p>', '\n\n', html)
        html = re.sub(r'</div>', '\n', html)
        html = re.sub(r'</li>', '\n', html)
        html = re.sub(r'</h[1-6]>', '\n\n', html)
        html = re.sub(r'<h[1-6][^>]*>', '\n## ', html)
        html = re.sub(r'<li[^>]*>', '- ', html)

        # Extract code blocks specially
        code_blocks = re.findall(
            r'<(?:pre|code)[^>]*>(.*?)</(?:pre|code)>',
            html, re.DOTALL | re.IGNORECASE
        )

        # Strip all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', html)

        # Clean up HTML entities and whitespace
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#39;', "'", text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()

        # Truncate to max_length
        if len(text) > max_length:
            text = text[:max_length] + "\n\n... [Content truncated]"

        result = {
            "status": "success",
            "url": url,
            "title": title,
            "description": description,
            "content": text
        }

        # Include code blocks if found
        if code_blocks:
            cleaned_blocks = [
                re.sub(r'<[^>]+>', '', block).strip()
                for block in code_blocks[:5]
            ]
            result["code_blocks"] = cleaned_blocks

        print(f"✅ Fetched {len(text)} chars from {url}")
        return json.dumps(result)

    except httpx.TimeoutException:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": "Request timed out. The page took too long to respond."
        })
    except httpx.HTTPStatusError as e:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": f"HTTP error {e.response.status_code}"
        })
    except Exception as e:
        print(f"❌ Fetch error: {str(e)}")
        return json.dumps({
            "status": "error",
            "url": url,
            "message": f"Failed to fetch page: {str(e)}"
        })


# ──────────────────────────────────────────────
# Container Tools
# ──────────────────────────────────────────────

async def inspect_container_structure(project_id: str) -> str:
    """Inspect the file structure in the container workspace."""
    print(f"📁 Inspecting container structure for project {project_id}")
    try:
        from project_manager import project_manager
        structure = project_manager.get_container_workspace_structure(project_id)
        
        if structure:
            print(f"✅ Retrieved container structure")
            return json.dumps({
                "status": "success",
                "project_id": project_id,
                "structure": structure
            })
        else:
            return json.dumps({
                "status": "error",
                "project_id": project_id,
                "message": "Container not found or not running. The container may not have been created yet."
            })
    except Exception as e:
        print(f"❌ Error inspecting container: {e}")
        return json.dumps({
            "status": "error",
            "project_id": project_id,
            "message": f"Failed to inspect container: {str(e)}"
        })


async def run_container_command(project_id: str, command: str) -> str:
    """Run a shell command in the container workspace."""
    print(f"🔧 Running command in container: {command}")
    try:
        from project_manager import project_manager
        result = project_manager.run_command_in_container(project_id, command)
        
        print(f"✅ Command completed with exit code {result.get('exit_code', 'unknown')}")
        return json.dumps({
            "status": "success" if result.get("success") else "error",
            "project_id": project_id,
            "command": command,
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "error": result.get("error")
        })
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return json.dumps({
            "status": "error",
            "project_id": project_id,
            "command": command,
            "message": f"Failed to run command: {str(e)}"
        })


# ──────────────────────────────────────────────
# Tool Dispatcher
# ──────────────────────────────────────────────

TOOL_HANDLERS = {
    "web_search": web_search,
    "fetch_page_content": fetch_page_content,
    "patch": patch,
    "write_file": write_file,
}


async def execute_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool call and return the result as a string."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

    try:
        return await handler(**arguments)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Tool execution failed: {str(e)}"})


# ──────────────────────────────────────────────
# Function Calling Loop (Async)
# ──────────────────────────────────────────────

async def execute_bash_script(script: str) -> str:
    """Execute a bash script dynamically inside the AI Agent container and return its output."""
    from project_manager import project_manager
    import asyncio
    import base64
    
    try:
        container = project_manager.agent_container
        
        if not container:
            try:
                container = project_manager.docker_client.containers.get("vibecoding-ai-agent")
            except Exception:
                return "Error: AI Agent container 'vibecoding-ai-agent' is not running. Cannot execute script."
                
        def run_script():
            # Base64 encode the script to avoid quoting injection issues when passing via sh -c
            encoded_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
            
            # We decode it inside the container and pipe to bash (with a 120s timeout)
            cmd = f"sh -c 'echo {encoded_script} | base64 -d | timeout 120 bash'"
            
            try:
                exit_code, output = container.exec_run(
                    cmd,
                    workdir="/project"
                )
                
                result = output.decode('utf-8', errors='replace')
                if not result.strip():
                    result = f"Script executed successfully with exit code {exit_code}."
                elif exit_code != 0:
                    result = f"Script returned non-zero exit code {exit_code}.\nOutput:\n{result}"
                    
                return result
            except Exception as inner_e:
                return f"Container execution error: {str(inner_e)}"
                
        return await asyncio.to_thread(run_script)
    except Exception as e:
        return f"Script Execution Failed: {str(e)}"


async def make_request_with_tools(
    messages: List[Dict[str, Any]],
    max_tool_rounds: int = 10,
    **kwargs
) -> Dict[str, Any]:
    """
    Make an AI API request with dynamic bash script execution capabilities.
    Instead of using proprietary OpenAI function calling, this injects instructions
    telling the LLM to output ```bash blocks to execute commands.
    This makes the agent universal and compatible with ANY LLM provider.
    """
    sys_instructions = (
        "\n\n[SYSTEM AGENT CAPABILITY]\n"
        "You act as an autonomous self-healing SWE-Agent inside a secure container.\n"
        "You have the ability to run shell scripts to gather information, modify files, test code, and configure networking.\n"
        "To perform any action, you MUST output a shell script block starting with ```bash and ending with ```.\n"
        "The system will execute your script dynamically and reply with the standard output and exit codes. Wait for the output before proceeding.\n\n"
        "[DEPLOYMENT & SELF-HEALING PROTOCOL]\n"
        "1. WRITE CODE: Generate the code for the user's request using your bash scripts to write/patch files.\n"
        "2. LOAD BALANCER/PROXY: You MUST configure Nginx to reverse proxy port 80 to your app's internal port. Write your conf to `/etc/nginx/sites-available/default`, restart Nginx (`service nginx restart`), and run your app in the background.\n"
        "3. TEST & VERIFY: You MUST write bash scripts to compile, lint, or syntax-check your code (e.g., `npm run build`, `python3 -m py_compile`).\n"
        "4. QUEUE & FIX: If your tests fail, treat it as a queue of runtime/syntax errors. Output new bash scripts to dynamically fix them one by one, and re-test continually until successful.\n"
        "5. Conclude only when tests pass and the proxy is active."
    )
    
    modified_messages = list(messages)
    found_system = False
    for msg in modified_messages:
        if msg.get("role") == "system":
            msg["content"] = str(msg.get("content", "")) + sys_instructions
            found_system = True
            break
            
    if not found_system:
        modified_messages.insert(0, {"role": "system", "content": sys_instructions.strip()})

    tool_call_log = []

    for round_num in range(max_tool_rounds):
        print(f"\n🤖 AI Request (Bash Agent round {round_num + 1})...")

        # Disable streaming for loop rounds
        kwargs["stream"] = False

        # Make the request using standard text-ompletion mode
        result = await ai_config.make_async_request(modified_messages, **kwargs)

        if "choices" not in result or len(result["choices"]) == 0:
            raise Exception("Invalid response format from AI API")

        choice = result["choices"][0]
        message = choice.get("message", {})
        content = message.get("content", "")

        # Check if the model wrote a bash script
        bash_matches = re.findall(r'```bash\n(.*?)\n```', content, re.DOTALL)

        if not bash_matches:
            # No bash scripts requested — model is done
            if tool_call_log:
                result["_tool_calls_log"] = tool_call_log
            print(f"✅ Final response received (round {round_num + 1})")
            return result

        # Process each bash block
        print(f"🔧 Model generated {len(bash_matches)} bash script(s)")

        # Add the assistant's message to conversation
        modified_messages.append(message)

        combined_output = ""
        for i, script in enumerate(bash_matches):
            script = script.strip()
            if not script:
                continue
                
            print(f"  → Executing dynamic script block {i+1}...")

            # Execute the script
            output = await execute_bash_script(script)
            combined_output += f"Output of script {i+1}:\n```\n{output}\n```\n\n"

            # Log for frontend
            result_preview = output[:300] + "..." if len(output) > 300 else output
            
            tool_call_log.append({
                "tool": "bash_script",
                "arguments": {"script": script[:100] + "..."},
                "result_preview": result_preview,
            })

        # Add script result to conversation
        modified_messages.append({
            "role": "user",
            "content": combined_output.strip()
        })

    # If we exhausted all rounds, make one final call
    print("⚠️ Max script rounds reached, making final call...")
    result = await ai_config.make_async_request(modified_messages, **kwargs)
    if tool_call_log:
        result["_tool_calls_log"] = tool_call_log
    return result
