"""
Universal AI provider abstraction.

To add a NEW provider:
  1. Create a subclass of BaseProvider in this file
  2. Implement the 4 abstract methods (get_headers, get_payload, parse_sse_chunk, parse_json_response)
  3. Add it to PROVIDER_REGISTRY at the bottom
  4. Add its env vars to .env

No other file needs to change.
"""

import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

import requests
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Base class — the universal contract every consumer depends on
# ═════════════════════════════════════════════════════════════════════════════

class BaseProvider(ABC):
    """Every AI provider must subclass this and implement the abstract methods.

    Consumers (main.py, web_tools.py, dual_agent_handler.py, …) only interact
    with the interface defined here — they never check which provider is active.

    Attributes exposed to consumers:
        name                      - provider identifier string
        base_url                  - API endpoint
        model                     - model identifier
        api_key                   - universal credential (API key, agent_id, …)
        supports_function_calling - whether OpenAI-style tool calling works
    """

    name: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    supports_function_calling: bool = False

    # Backward-compat alias so callers can use either .provider or .name
    @property
    def provider(self) -> str:
        return self.name

    # ── Abstract: subclasses MUST implement ──────────────────────────────

    @abstractmethod
    def get_headers(self) -> Dict[str, str]:
        """HTTP headers for API requests."""
        ...

    @abstractmethod
    def get_payload(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Build the request body.  Must handle the messages format internally."""
        ...

    @abstractmethod
    def parse_sse_chunk(self, line: str) -> Optional[str]:
        """Extract text content from a single SSE data line (after stripping
        the ``data: `` prefix).  Return the text fragment or ``None``."""
        ...

    @abstractmethod
    def parse_json_response(self, data: Dict) -> str:
        """Extract text content from a non-streaming JSON response body."""
        ...

    # ── Overridable: sensible defaults ───────────────────────────────────

    def is_stream_done(self, line: str) -> bool:
        """Return ``True`` if this SSE line signals end-of-stream."""
        return line.strip() == "[DONE]"

    # ── Unified request methods — consumers call these ───────────────────

    def make_request(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Synchronous request.  Always returns the standard shape:
        ``{"choices": [{"message": {"content": "…"}}]}``
        """
        headers = self.get_headers()
        payload = self.get_payload(messages, **kwargs)
        is_stream = payload.get("stream", False)

        try:
            resp = requests.post(
                self.base_url, headers=headers, json=payload,
                stream=is_stream, timeout=120,
            )
            resp.raise_for_status()

            if is_stream:
                return self._aggregate_sse_sync(resp)

            return self._wrap_json(resp.json())
        except requests.exceptions.RequestException as e:
            raise Exception(f"AI API request failed: {e}")

    async def make_async_request(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Async request (httpx).  Same return shape as ``make_request``."""
        headers = self.get_headers()
        payload = self.get_payload(messages, **kwargs)
        is_stream = payload.get("stream", False)

        try:
            if is_stream:
                return await self._aggregate_sse_async(headers, payload)

            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(self.base_url, headers=headers, json=payload)
                resp.raise_for_status()
                return self._wrap_json(resp.json())
        except httpx.TimeoutException:
            raise Exception(f"{self.name} request timed out.")
        except httpx.HTTPStatusError as e:
            # For streaming responses, we must read the content before accessing .text
            try:
                if not getattr(e.response, "_content_read", False):
                    await e.response.aread()
                error_body = e.response.text
            except Exception:
                error_body = "(Could not read error response)"
            raise Exception(f"{self.name} returned status {e.response.status_code}: {error_body}")
        except httpx.HTTPError as e:
            raise Exception(f"{self.name} networking error: {e}")

    # ── Internal helpers ─────────────────────────────────────────────────

    def _wrap_json(self, data: Dict) -> Dict[str, Any]:
        """Normalise a non-streaming JSON body into the standard shape."""
        if "choices" in data:
            return data
        content = self.parse_json_response(data)
        return {"choices": [{"message": {"content": content}}]}

    def _aggregate_sse_sync(self, response) -> Dict[str, Any]:
        content = ""
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
            if self.is_stream_done(line):
                break
            text = self.parse_sse_chunk(line)
            if text:
                content += text
        return {"choices": [{"message": {"content": content}}]}

    async def _aggregate_sse_async(self, headers, payload) -> Dict[str, Any]:
        content = ""
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", self.base_url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if self.is_stream_done(line):
                        break
                    text = self.parse_sse_chunk(line)
                    if text:
                        content += text
        return {"choices": [{"message": {"content": content}}]}

    @staticmethod
    def messages_to_prompt(messages: List[Dict]) -> str:
        """Flatten OpenAI-style messages array into a single prompt string.
        Useful for providers that accept a flat ``prompt`` field."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                content = " ".join(text_parts)
            if not content:
                continue
            tag = {"system": "[System Instructions]",
                   "user": "[User]",
                   "assistant": "[Assistant]",
                   "tool": "[Tool Result]"}.get(role, f"[{role}]")
            parts.append(f"{tag}\n{content}")
        return "\n\n".join(parts)

    @staticmethod
    def extract_images_from_messages(messages: List[Dict]) -> List[Dict]:
        """Pull image data from OpenAI-style vision messages and return them
        as Anthropic/Claude-compatible content blocks.

        Handles both ``data:`` URLs (``data:image/png;base64,…``) and plain
        HTTP URLs.  Returns a list of dicts like::

            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": "iVBOR…"}}
        """
        DATA_URL_RE = re.compile(
            r"^data:(image/[a-zA-Z+.-]+);base64,(.+)$", re.DOTALL
        )
        images: List[Dict] = []
        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "image_url":
                    continue
                url = (block.get("image_url") or {}).get("url", "")
                m = DATA_URL_RE.match(url)
                if m:
                    images.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": m.group(1),
                            "data": m.group(2),
                        },
                    })
                elif url.startswith("http"):
                    images.append({
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url,
                        },
                    })
        return images


# ═════════════════════════════════════════════════════════════════════════════
# OpenAI-compatible provider  (NVIDIA, OpenAI, Azure, any /v1/chat/completions)
# ═════════════════════════════════════════════════════════════════════════════

class OpenAIProvider(BaseProvider):
    name = "openai"
    supports_function_calling = True

    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY", "")
        if not self.api_key:
            raise ValueError("AI_API_KEY is required for openai provider")
        self.base_url = os.getenv("AI_BASE_URL", "")
        if not self.base_url:
            raise ValueError("AI_BASE_URL is required for openai provider")
        self.model = os.getenv("AI_MODEL", "")
        if not self.model:
            raise ValueError("AI_MODEL is required for openai provider")

        self.temperature = float(os.getenv("AI_TEMPERATURE", "1.0"))
        self.top_p = float(os.getenv("AI_TOP_P", "1.0"))
        self.frequency_penalty = float(os.getenv("AI_FREQUENCY_PENALTY", "0.0"))
        self.presence_penalty = float(os.getenv("AI_PRESENCE_PENALTY", "0.0"))
        self.stream = os.getenv("AI_STREAM", "false").lower() == "true"

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_payload(self, messages, **kwargs):
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.presence_penalty),
            "stream": kwargs.get("stream", self.stream),
        }
        
        # Enable tool calling if supported and provided
        if self.supports_function_calling and "tools" in kwargs and kwargs["tools"]:
            payload["tools"] = kwargs["tools"]
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
            
        return payload

    def parse_sse_chunk(self, line):
        try:
            chunk = json.loads(line)
            if "choices" in chunk and chunk["choices"]:
                return chunk["choices"][0].get("delta", {}).get("content")
        except json.JSONDecodeError:
            pass
        return None

    def parse_json_response(self, data):
        if "choices" in data and data["choices"]:
            return data["choices"][0].get("message", {}).get("content", "")
        return ""

    def _wrap_json(self, data):
        # OpenAI responses already have the right shape and may contain
        # tool_calls that callers need, so return as-is.
        return data


# ═════════════════════════════════════════════════════════════════════════════
# BournAI provider  (brn-llama.bourntec.com, Anthropic-style SSE)
# ═════════════════════════════════════════════════════════════════════════════

class BournAIProvider(BaseProvider):
    name = "bournai"
    supports_function_calling = False

    def __init__(self):
        self.base_url = os.getenv("BRN_LLAMA_URL", "https://brn-llama.bourntec.com/api/process")
        self.api_key = os.getenv("BRN_AGENT_ID", "")
        if not self.api_key:
            raise ValueError("BRN_AGENT_ID is required for bournai provider")
        self.model = os.getenv("BRN_MODEL", "BournAI")
        self.platform_id = os.getenv("BRN_PLATFORM_ID", "DSuite")
        self.max_tokens = int(os.getenv("BRN_MAX_TOKENS", "50000"))
        self.temperature = float(os.getenv("BRN_TEMPERATURE", "0.7"))
        self.stream = True

    def get_headers(self):
        return {"Content-Type": "application/json"}

    def get_payload(self, messages, **kwargs):
        system_parts = []
        non_system = []
        for msg in messages:
            if msg.get("role") == "system":
                c = msg.get("content", "")
                if isinstance(c, list):
                    c = " ".join(
                        p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                if c:
                    system_parts.append(c)
            else:
                non_system.append(msg)

        system_text = "\n\n".join(system_parts) if system_parts else ""

        images = self.extract_images_from_messages(messages)
        conversation = self.messages_to_prompt(non_system)

        if system_text:
            text_prompt = (
                f"<system>\n{system_text}\n</system>\n\n{conversation}"
            )
        else:
            text_prompt = conversation

        if images:
            prompt_content = list(images)
            prompt_content.append({"type": "text", "text": text_prompt})
        else:
            prompt_content = text_prompt

        payload = {
            "agent_id": self.api_key,
            "model": kwargs.get("model", self.model),
            "platform_id": self.platform_id,
            "stream": kwargs.get("stream", self.stream),
            "prompt": prompt_content,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        if system_text:
            payload["system"] = system_text
        return payload

    def parse_sse_chunk(self, line):
        try:
            chunk = json.loads(line)
            for part in chunk.get("content", []):
                if isinstance(part, dict) and part.get("type") == "text":
                    return part.get("text") or None
        except json.JSONDecodeError:
            pass
        return None

    def is_stream_done(self, line):
        if line.strip() == "[DONE]":
            return True
        try:
            return json.loads(line).get("stop_reason") == "end_turn"
        except (json.JSONDecodeError, AttributeError):
            return False

    def parse_json_response(self, data):
        parts = []
        for part in data.get("content", []):
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
# Provider registry — the ONLY place you touch when adding a new provider
# ═════════════════════════════════════════════════════════════════════════════

PROVIDER_REGISTRY: Dict[str, type] = {
    "openai": OpenAIProvider,
    "bournai": BournAIProvider,
}


def _is_brn_llama_enabled() -> bool:
    """Check if BRN Llama mode is active from environment."""
    use_brn = os.getenv("USE_BRN_LLAMA", "false").lower().strip()
    return use_brn in ("true", "1", "yes")


def _create_provider() -> BaseProvider:
    # Check USE_BRN_LLAMA flag first (DSuite-style)
    if _is_brn_llama_enabled():
        logger.info("🤖 AI Provider: bournai (via USE_BRN_LLAMA=true)")
        return BournAIProvider()
    
    # Fallback to AI_PROVIDER for backward compatibility
    name = os.getenv("AI_PROVIDER", "openai").lower().strip()
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown AI_PROVIDER='{name}'. Available: {available}")
    logger.info(f"🤖 AI Provider: {name}")
    return cls()


# Global singleton — every other file imports this
ai_config: BaseProvider = _create_provider()
