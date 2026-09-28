"""LLM Client for Agent Runtime.

Connects to the Bourntec AI processing engine (https://brn-llama.bourntec.com/api/process),
supports Claude, Kimi, and DeepSeek, streams step-by-step live console logs with timestamps,
and records exact token counts directly from the AI responses without tool-based estimation.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent.model_router import ModelConfig
from infrastructure.model_profile import get_profile


def _strip_dsml(text: str) -> str:
    """Strip DeepSeek DSML markup tags from reasoning text."""
    if not text:
        return ""
    text = re.sub(r'<｜DSML｜[^>]*>', '', text)
    text = re.sub(r'<\|DSML\|function_calls?>', '', text)
    text = re.sub(r'<\|DSML\|', '', text)
    text = re.sub(r'\|>', '', text)
    text = re.sub(r'<｜', '', text)
    return text.strip()
from runtime.resource_limits import ResourceLimits


def log(msg: str) -> None:
    """Format and immediately flush live log lines to container stdout."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    try:
        print(formatted, flush=True)
    except UnicodeEncodeError:
        print(formatted.encode("ascii", errors="replace").decode("ascii"), flush=True)


@dataclass
class LLMResponse:
    content: str
    reasoning: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    model_id: str = ""
    stop_reason: str = ""
    latency_ms: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Agent Runtime LLM Client connecting to Bourntec AI Engine."""

    # Class-level sink: when the runtime sets it (once per session), EVERY
    # AI call made through this client auto-reports its exact token usage —
    # any model, any phase, any call site. No per-phase registration needed.
    _usage_sink = None

    @classmethod
    def set_usage_sink(cls, sink) -> None:
        """Register a callable receiving {model, input_tokens, output_tokens, total_tokens, ...}
        after every successful provider call. Set once per session by the orchestrator.
        """
        cls._usage_sink = sink

    def __init__(self, config: ModelConfig | None = None) -> None:
        self._config = config
        self._limits = ResourceLimits()
        self._api_url = os.environ.get("AI_API_URL", "https://brn-llama.bourntec.com/api/process")
        self._agent_id = os.environ.get("AI_AGENT_ID", "igi3yge8763t876gsd97ys97t76543sd5tt3e866e876riyueg87eyt78eh-38eh9e8sh")
        self._platform_id = os.environ.get("AI_PLATFORM_ID", "DSuite")
        self._model = (
            (config.model if config else None)
            or os.environ.get("AI_MODEL")
            or os.environ.get("MODEL_NAME", "claude")
        )
        self._stream = os.environ.get("AI_STREAM", "false").lower() == "true"
        self._thinking = os.environ.get("AI_THINKING", "true").lower() == "true"

    def complete(
        self,
        system: str = "",
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Execute a prompt against the AI processing endpoint."""
        full_prompt = prompt or ""
        if not full_prompt and messages:
            parts = []
            if system:
                parts.append(f"System: {system}")
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_blocks = [b.get("text", "") for b in content if isinstance(b, dict) and "text" in b]
                    content_str = " ".join(text_blocks)
                else:
                    content_str = str(content)
                parts.append(f"{role.capitalize()}: {content_str}")
            full_prompt = "\n\n".join(parts)
        elif system and full_prompt:
            full_prompt = f"System: {system}\n\nUser: {full_prompt}"

        return self.call_ai(full_prompt, tools=tools)

    def call_ai(
        self,
        prompt: str = "",
        *,
        conversation: list[dict[str, Any]] | None = None,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        timeout: int = 300,
        max_tokens: int | None = None,
        images: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call AI engine and extract exact token usage directly from response."""
        target_model = model or self._model

        # Safe fallback if prompt was not passed as a string or passed via conversation kwarg
        if not prompt and conversation:
            parts = []
            if system:
                parts.append(f"System: {system}")
            for msg in conversation:
                role = msg.get("role", "user")
                c = msg.get("content", "")
                if isinstance(c, list):
                    text_blocks = [b.get("text", "") for b in c if isinstance(b, dict) and "text" in b]
                    c_str = " ".join(text_blocks)
                else:
                    c_str = str(c)
                parts.append(f"{role.capitalize()}: {c_str}")
            prompt = "\n\n".join(parts)
        elif system and prompt and not prompt.startswith("System:"):
            prompt = f"System: {system}\n\nUser: {prompt}"

        # Bring-Your-Own-Model: a `custom_<id>` key means the session runs on a
        # model the user configured in the platform. The container was given the
        # user's endpoint + API key via CUSTOM_MODEL_* env vars by AgentManager,
        # so call THAT provider directly (OpenAI-compatible) instead of the proxy.
        if target_model.startswith("custom_") and os.environ.get("CUSTOM_MODEL_API_KEY"):
            return self._call_custom_provider(prompt, target_model, tools=tools, timeout=timeout)

        # Handle attached images (user uploaded mockups or preview snapshots)
        prompt_payload = prompt
        if images and len(images) > 0:
            content_blocks = [{"type": "text", "text": prompt}]
            for img in images:
                if isinstance(img, dict) and "data" in img:
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/png"),
                            "data": img["data"],
                        }
                    })
            prompt_payload = content_blocks
        else:
            # Enrich prompt with visual base64 image data from workspace if reference mockups exist
            workspace_dir = os.environ.get("WORKSPACE_PATH", "/workspace")
            try:
                import glob
                import base64
                mockup_files = sorted(glob.glob(f"{workspace_dir}/reference_mockup_*.*"))
                # Only inject image blocks if the target model actually supports vision.
                # Bedrock Converse API throws HTTP 400 Bad Request if image blocks are sent to text-only models (deepseek, kimi, etc.).
                is_target_vision = not any(
                    non_vis in target_model.lower() for non_vis in ("deepseek", "kimi", "moonshot")
                )
                if is_target_vision and mockup_files and "reference_mockup_" in prompt and "data:image/" not in prompt:
                    content_blocks = [{"type": "text", "text": prompt}]
                    for mf in mockup_files:
                        ext = mf.split(".")[-1].lower()
                        mime = "image/png"
                        if ext in ("jpg", "jpeg"):
                            mime = "image/jpeg"
                        elif ext == "webp":
                            mime = "image/webp"
                        elif ext == "svg":
                            mime = "image/svg+xml"
                        try:
                            with open(mf, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                                content_blocks.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": b64,
                                    }
                                })
                        except Exception:
                            pass
                    if len(content_blocks) > 1:
                        prompt_payload = content_blocks
            except Exception:
                pass

        # Deduplicate tools by name: AWS Bedrock Converse API rejects duplicate tool names
        deduped_tools: list[dict[str, Any]] = []
        if tools:
            seen_names: set[str] = set()
            for t in tools:
                t_name = t.get("name", "")
                if t_name and t_name not in seen_names:
                    seen_names.add(t_name)
                    deduped_tools.append(t)
                elif t_name:
                    log(f"⚠️ [Tool Dedup] Removed duplicate tool definition: '{t_name}'")

        payload = {
            "prompt": prompt_payload,
            "agent_id": self._agent_id,
            "platform_id": self._platform_id,
            "model": target_model,
            "stream": self._stream,
            "thinking": self._thinking,
            "tools": deduped_tools,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        log(f"🤖 [AI Request] Calling model '{target_model}' on {self._api_url} (timeout={timeout}s)...")
        if deduped_tools:
            log(f"   Tools registered: {len(deduped_tools)} function(s)")

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        # Retry up to 3 attempts on network / socket read timeout or HTTP 500
        last_error = None
        max_attempts = 3
        for attempt in range(max_attempts):
            start_time = time.time()
            req = urllib.request.Request(
                url=self._api_url,
                data=body_bytes,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    data = json.loads(resp.read().decode("utf-8"))
                    response = self.parse_ai_response(data, fallback_model=target_model, elapsed_ms=elapsed_ms)
                    
                    log(f"✅ [AI Response] Completed in {response.latency_ms}ms (model: {response.model})")
                    if response.reasoning:
                        log(f"💡 [Thinking/Reasoning]:\n{response.reasoning}")
                    if response.content:
                        log(f"📝 [AI Output Content]:\n{response.content}")

                    log(f"📊 [Token Usage]: in={response.input_tokens} | out={response.output_tokens} | total={response.total_tokens}")

                    # Auto-report this call's exact usage to the platform billing sink.
                    # Wrapped so telemetry can NEVER break an AI call.
                    sink = type(self)._usage_sink
                    if sink:
                        try:
                            prof = get_profile(response.model or target_model)
                            sink({
                                "model": response.model or target_model,
                                "model_id": response.model_id,
                                "input_tokens": int(response.input_tokens or 0),
                                "output_tokens": int(response.output_tokens or 0),
                                "total_tokens": int(response.total_tokens or 0),
                                "context_window": int(getattr(prof, "context_window", 100_000) or 100_000),
                                "latency_ms": int(response.latency_ms or 0),
                            })
                        except Exception as exc:
                            log(f"⚠️ [Usage] Could not report token usage: {exc}")

                    return response
            except (urllib.error.URLError, TimeoutError, Exception) as exc:
                last_error = exc
                err_detail = ""
                status_code = getattr(exc, "code", None)
                if hasattr(exc, "read"):
                    try:
                        err_detail = exc.read().decode("utf-8", errors="replace")[:400]
                    except Exception:
                        pass
                detail_msg = f" | Server body: {err_detail}" if err_detail else ""
                log(f"⚠️ [Attempt {attempt + 1}/{max_attempts}] AI request failed: {exc}{detail_msg}")
                if attempt < max_attempts - 1:
                    backoff = (attempt + 1) * 3
                    log(f"🔄 Retrying AI call in {backoff}s...")
                    time.sleep(backoff)

                    # If server returned 500 and prompt payload is large, compact context on retry
                    if status_code == 500 and isinstance(prompt_payload, str) and len(prompt_payload) > 20_000:
                        log("⚠️ [AI Retry] Compacting prompt payload to mitigate backend context/OOM overload...")
                        keep_head = 6000
                        keep_tail = 6000
                        compacted = prompt_payload[:keep_head] + "\n\n... [Middle context compacted to mitigate server memory pressure] ...\n\n" + prompt_payload[-keep_tail:]
                        payload["prompt"] = compacted
                        body_bytes = json.dumps(payload).encode("utf-8")

        raise RuntimeError(f"AI call failed: {last_error}")

    # ------------------------------------------------------------------
    # Bring-Your-Own-Model: call the user's own OpenAI-compatible provider
    # ------------------------------------------------------------------

    def _call_custom_provider(
        self,
        prompt: str,
        custom_key: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        timeout: int = 300,
    ) -> LLMResponse:
        """Call a user-configured custom model endpoint (OpenAI-compatible).

        Uses the CUSTOM_MODEL_* env vars injected by the backend control plane.
        Token usage is read from the response's `usage` block and auto-reported
        to the billing sink under the `custom_<id>` key.
        """
        base_url = os.environ.get("CUSTOM_MODEL_BASE_URL", "").strip().rstrip("/")
        api_key = os.environ.get("CUSTOM_MODEL_API_KEY", "").strip()
        model_id = (os.environ.get("CUSTOM_MODEL_ID", "") or custom_key).strip()
        if not base_url:
            raise RuntimeError(f"Custom model {custom_key} has no API base URL configured")

        # Normalize to the OpenAI chat-completions endpoint
        if base_url.endswith("/chat/completions"):
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"

        # Convert prompt (string or Anthropic-style content blocks) to OpenAI messages
        messages_content: str | list[dict[str, Any]] = prompt
        if isinstance(prompt, list):
            converted: list[dict[str, Any]] = []
            for block in prompt:
                if not isinstance(block, dict):
                    continue
                if "text" in block:
                    converted.append({"type": "text", "text": str(block["text"])})
                elif block.get("type") == "image" and isinstance(block.get("source"), dict):
                    src = block["source"]
                    media = src.get("media_type", "image/png")
                    data = src.get("data", "")
                    converted.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media};base64,{data}"},
                    })
            if converted:
                messages_content = converted
        messages: list[dict[str, Any]] = [{"role": "user", "content": messages_content}]

        body: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]

        payload_bytes = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        log(f"🤖 [AI Request] Calling custom model '{custom_key}' ({model_id}) on {endpoint} (timeout={timeout}s)...")
        if tools:
            log(f"   Tools registered: {len(tools)} function(s)")

        last_error: Exception | None = None
        for attempt in range(2):
            start_time = time.time()
            req = urllib.request.Request(
                url=endpoint,
                data=payload_bytes,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    data = json.loads(resp.read().decode("utf-8"))
                    response = self._parse_custom_response(
                        data, custom_key=custom_key, elapsed_ms=elapsed_ms
                    )

                    log(f"✅ [AI Response] Completed in {response.latency_ms}ms (model: {response.model})")
                    if response.reasoning:
                        log(f"💡 [Thinking/Reasoning]:\n{response.reasoning}")
                    if response.content:
                        log(f"📝 [AI Output Content]:\n{response.content}")

                    log(f"📊 [Token Usage]: in={response.input_tokens} | out={response.output_tokens} | total={response.total_tokens}")

                    # Auto-report this call's exact usage to the platform billing sink.
                    sink = type(self)._usage_sink
                    if sink:
                        try:
                            prof = get_profile(response.model or custom_key)
                            sink({
                                "model": response.model or custom_key,
                                "model_id": response.model_id,
                                "input_tokens": int(response.input_tokens or 0),
                                "output_tokens": int(response.output_tokens or 0),
                                "total_tokens": int(response.total_tokens or 0),
                                "context_window": int(getattr(prof, "context_window", 100_000) or 100_000),
                                "latency_ms": int(response.latency_ms or 0),
                            })
                        except Exception as exc:
                            log(f"⚠️ [Usage] Could not report token usage: {exc}")

                    return response
            except (urllib.error.URLError, TimeoutError, Exception) as exc:
                last_error = exc
                log(f"⚠️ [Attempt {attempt + 1}] Custom model call failed: {exc}")
                if attempt == 0:
                    time.sleep(2)
                    log("🔄 Retrying custom model call...")

        raise RuntimeError(f"Custom model call failed: {last_error}")

    @classmethod
    def _parse_custom_response(
        cls,
        data: dict[str, Any],
        *,
        custom_key: str,
        elapsed_ms: int = 0,
    ) -> LLMResponse:
        """Parse an OpenAI-compatible chat completion into LLMResponse."""
        usage = data.get("usage") or {}
        input_tokens = (
            usage.get("prompt_tokens")
            or usage.get("promptTokens")
            or usage.get("input_tokens")
            or usage.get("inputTokens")
            or 0
        )
        output_tokens = (
            usage.get("completion_tokens")
            or usage.get("completionTokens")
            or usage.get("output_tokens")
            or usage.get("outputTokens")
            or 0
        )
        total_tokens = (
            usage.get("total_tokens")
            or usage.get("totalTokens")
            or (input_tokens + output_tokens)
        )

        content = ""
        reasoning = ""
        tool_calls: list[dict[str, Any]] = []
        stop_reason = data.get("stop_reason") or ""
        model_name = data.get("model") or ""

        choices = data.get("choices") or []
        if choices:
            choice = choices[0]
            if isinstance(choice, dict):
                msg = choice.get("message") or {}
                if isinstance(msg, dict):
                    text = msg.get("content")
                    if isinstance(text, list):
                        text = "".join(
                            b.get("text", "") for b in text if isinstance(b, dict)
                        )
                    if text:
                        content = _strip_dsml(str(text))
                    reasoning = _strip_dsml(str(msg.get("reasoning_content") or msg.get("reasoning") or ""))
                    raw_tools = msg.get("tool_calls") or []
                    for tc in raw_tools:
                        if not isinstance(tc, dict):
                            continue
                        block = dict(tc)
                        fn = block.get("function") or {}
                        if isinstance(fn, dict):
                            fn = dict(fn)
                            args = fn.get("arguments")
                            if isinstance(args, str):
                                try:
                                    fn["arguments"] = json.loads(args)
                                except Exception:
                                    pass
                            block["function"] = fn
                        tool_calls.append(block)
                stop_reason = choice.get("finish_reason") or stop_reason

        return LLMResponse(
            content=content,
            reasoning=reasoning,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=int(total_tokens or 0),
            model=custom_key,  # keep billing attribution on the custom_<id> key
            model_id=model_name or custom_key,
            stop_reason=stop_reason,
            latency_ms=elapsed_ms,
            tool_calls=tool_calls,
            raw_response=data,
        )

    @classmethod
    def parse_ai_response(
        cls,
        data: dict[str, Any],
        fallback_model: str = "",
        elapsed_ms: int = 0,
    ) -> LLMResponse:
        """Extract content, reasoning, tools, and EXACT token metrics without calculation."""
        model_name = data.get("model") or fallback_model
        model_id = data.get("model_id") or ""
        stop_reason = data.get("stop_reason") or ""

        # Extract exact token usage directly from AI response across Claude, DeepSeek, Kimi, OpenAI
        usage = data.get("usage") or {}
        input_tokens = (
            usage.get("inputTokens")
            or usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or usage.get("promptTokens")
            or 0
        )
        output_tokens = (
            usage.get("outputTokens")
            or usage.get("output_tokens")
            or usage.get("completion_tokens")
            or usage.get("completionTokens")
            or 0
        )
        total_tokens = (
            usage.get("totalTokens")
            or usage.get("total_tokens")
            or (input_tokens + output_tokens)
        )

        # Extract latency
        metrics = data.get("metrics") or {}
        latency_ms = metrics.get("latencyMs") or elapsed_ms

        extracted_content = ""
        extracted_reasoning = ""
        tool_calls: list[dict[str, Any]] = []

        if data.get("completion") and isinstance(data["completion"], str):
            extracted_content = _strip_dsml(data["completion"])

        assistant_msg = data.get("assistant_message") or {}
        content_blocks = assistant_msg.get("content") or []

        if isinstance(content_blocks, list):
            text_parts = []
            reasoning_parts = []

            for block in content_blocks:
                if not isinstance(block, dict):
                    continue

                # Kimi reasoningContent
                if "reasoningContent" in block:
                    rc = block["reasoningContent"]
                    if isinstance(rc, dict):
                        rt = rc.get("reasoningText")
                        if isinstance(rt, dict) and "text" in rt:
                            reasoning_parts.append(_strip_dsml(rt["text"]))
                        elif isinstance(rt, str):
                            reasoning_parts.append(_strip_dsml(rt))

                # Thinking block
                if "thinking" in block:
                    th = block["thinking"]
                    if isinstance(th, str):
                        reasoning_parts.append(_strip_dsml(th))
                    elif isinstance(th, dict) and "text" in th:
                        reasoning_parts.append(_strip_dsml(th["text"]))

                # Standard text block
                if "text" in block and isinstance(block["text"], str):
                    text_parts.append(_strip_dsml(block["text"]))

                # Tool use / function calls
                if block.get("type") in ("tool_use", "function_call") or "tool_use" in block:
                    tool_calls.append(block)
                elif "function" in block:
                    tool_calls.append(block)

            if reasoning_parts:
                extracted_reasoning = "\n".join(reasoning_parts).strip()
            if not extracted_content and text_parts:
                extracted_content = "\n".join(text_parts).strip()

        if not tool_calls and "tool_calls" in data and isinstance(data["tool_calls"], list):
            tool_calls = data["tool_calls"]

        if not extracted_content:
            if "output" in data and isinstance(data["output"], str):
                extracted_content = _strip_dsml(data["output"])
            elif "response" in data and isinstance(data["response"], str):
                extracted_content = _strip_dsml(data["response"])

        return LLMResponse(
            content=extracted_content,
            reasoning=extracted_reasoning,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=model_name,
            model_id=model_id,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_response=data,
        )
