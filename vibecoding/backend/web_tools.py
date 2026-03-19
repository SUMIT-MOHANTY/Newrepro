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
    }
]

# ──────────────────────────────────────────────
# Tool Implementations
# ──────────────────────────────────────────────

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
# Tool Dispatcher
# ──────────────────────────────────────────────

TOOL_HANDLERS = {
    "web_search": web_search,
    "fetch_page_content": fetch_page_content,
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

async def make_request_with_tools(
    messages: List[Dict[str, Any]],
    max_tool_rounds: int = 10,
    **kwargs
) -> Dict[str, Any]:
    """
    Make an AI API request with tool/function calling support.
    Runs a loop: if the model returns tool_calls, execute them,
    feed results back, and let the model continue until it produces
    a final text response (no more tool_calls).

    For providers that don't support function calling, falls back to
    ``ai_config.make_async_request()`` — no provider-specific code here.

    Returns the final API response dict with the model's text answer.
    """
    if not ai_config.supports_function_calling:
        return await ai_config.make_async_request(messages, **kwargs)

    headers = ai_config.get_headers()

    # Build payload with tools
    payload = ai_config.get_payload(messages, **kwargs)
    payload["tools"] = TOOL_DEFINITIONS
    payload["tool_choice"] = "auto"
    # Disable streaming for function calling rounds
    payload["stream"] = False

    tool_call_log = []  # Track all tool calls for frontend visibility

    for round_num in range(max_tool_rounds):
        print(f"\n🤖 AI Request (round {round_num + 1})...")

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    ai_config.base_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException:
            raise Exception("AI API request timed out after 300 seconds. The generation took too long.")
        except httpx.HTTPStatusError as e:
            raise Exception(f"AI API returned error status {e.response.status_code}: {e.response.text}")
        except httpx.HTTPError as e:
            raise Exception(f"AI API networking error: {str(e)}")

        if "choices" not in result or len(result["choices"]) == 0:
            raise Exception("Invalid response format from AI API")

        choice = result["choices"][0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # Check if the model wants to call tools
        tool_calls = message.get("tool_calls")

        if not tool_calls or finish_reason == "stop":
            # No tool calls — model is done, return the final response
            if tool_call_log:
                result["_tool_calls_log"] = tool_call_log
            print(f"✅ Final response received (round {round_num + 1})")
            return result

        # Process each tool call
        print(f"🔧 Model requested {len(tool_calls)} tool call(s)")

        # Add the assistant's message (with tool_calls) to conversation
        messages.append(message)

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "unknown")
            tool_id = tc.get("id", "")

            # Parse arguments
            try:
                arguments = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}

            print(f"  → Calling tool: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]})")

            # Execute the tool (async)
            tool_result = await execute_tool_call(tool_name, arguments)

            # Log for frontend
            tool_call_log.append({
                "tool": tool_name,
                "arguments": arguments,
                "result_preview": tool_result[:300] + "..." if len(tool_result) > 300 else tool_result
            })

            # Add tool result to conversation
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": tool_result
            })

        # Update payload for next round
        payload = ai_config.get_payload(messages, **kwargs)
        payload["tools"] = TOOL_DEFINITIONS
        payload["tool_choice"] = "auto"
        payload["stream"] = False

    # If we exhausted all rounds, make one final call without tools
    print("⚠️ Max tool rounds reached, making final call without tools...")
    payload = ai_config.get_payload(messages, **kwargs)
    payload["stream"] = False

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                ai_config.base_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
        if tool_call_log:
            result["_tool_calls_log"] = tool_call_log
        return result
    except httpx.TimeoutException:
        raise Exception("AI API final request timed out after 300 seconds.")
    except httpx.HTTPStatusError as e:
        raise Exception(f"AI API final request returned status {e.response.status_code}: {e.response.text}")
    except httpx.HTTPError as e:
        raise Exception(f"AI API final networking error: {str(e)}")
