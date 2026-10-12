"""
LLM Gateway Integration Client
Wraps the lower-level centralized LLM gateway into a clean, reusable integration layer.
Handles BRN Llama, OpenAI-compatible models, token tracking context, and streaming.
"""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import os
import sys

from app.integrations.llm import llm_gateway as raw_gateway

logger = logging.getLogger(__name__)

# Re-export context managers for request-scoped metadata
ai_purpose = raw_gateway.ai_purpose
ai_project_context = raw_gateway.ai_project_context


class LLMGatewayClient:
    """
    Standardized client for communicating with large language models through the centralized gateway.
    """

    def __init__(self):
        self._raw = raw_gateway

    @property
    def is_brn_llama_enabled(self) -> bool:
        return self._raw.is_brn_llama_enabled()

    def extract_content(self, response_data: Dict[str, Any]) -> str:
        """Extract plain text / markdown content from varying provider formats."""
        return self._raw.extract_content_from_response(response_data)

    def extract_reasoning(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Extract chain-of-thought or reasoning tokens if present."""
        return self._raw.extract_reasoning_from_response(response_data)

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        purpose: Optional[str] = None,
        project_token: Optional[str] = None,
        project_name: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a completion request and extract the text response directly.
        """
        extra_kwargs = dict(kwargs)
        timeout = extra_kwargs.pop("timeout", 120.0)
        if "max_tokens" not in extra_kwargs:
            extra_kwargs["max_tokens"] = max_tokens

        with ai_purpose(purpose or "agent_execution"):
            with ai_project_context(project_token=project_token, project_name=project_name):
                return await self._raw.call_llm_and_extract(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    timeout=timeout,
                    purpose=purpose,
                    project_token=project_token,
                    project_name=project_name,
                    **extra_kwargs,
                )

    async def complete_raw(
        self,
        payload: Dict[str, Any],
        purpose: Optional[str] = None,
        project_token: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send raw payload to LLM and return the raw parsed response dictionary.
        """
        with ai_purpose(purpose or "agent_execution"):
            with ai_project_context(project_token=project_token, project_name=project_name):
                return await self._raw.call_llm(payload)

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        purpose: Optional[str] = None,
        project_token: Optional[str] = None,
        project_name: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion chunks back asynchronously as text deltas.
        """
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if model:
            payload["model"] = model

        with ai_purpose(purpose or "agent_stream"):
            with ai_project_context(project_token=project_token, project_name=project_name):
                async for chunk in self._raw.call_llm_streaming(payload):
                    yield chunk


llm_gateway_client = LLMGatewayClient()
llm_client = llm_gateway_client
