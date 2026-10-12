"""
Centralized LLM Gateway — routes AI calls to either BRN Llama or OpenAI-compatible APIs.

When USE_BRN_LLAMA=true in .env, ALL AI calls go through BRN Llama
(https://brn-llama.bourntec.com/api/process).

Supports multiple response formats including:
- OpenAI-style: { "choices": [{"message": {"content": "..."}}] }
- BRN Llama: { "response": "..." } or { "text": "..." }
- Anthropic-style: { "content": [{"type": "text", "text": "..."}] }
- Streaming SSE with Anthropic-format chunks
"""

import httpx
import json
import re
import logging
import contextvars
from contextlib import contextmanager
from typing import Optional, Dict, Any, AsyncGenerator

from app.core.config import settings

logger = logging.getLogger(__name__)

# Thread-safe and async-safe context variables to track user, project token, active organization, purpose, and project name
current_user_id_var = contextvars.ContextVar("current_user_id", default=None)
current_project_token_var = contextvars.ContextVar("current_project_token", default=None)
current_project_name_var = contextvars.ContextVar("current_project_name", default=None)
current_user_org_var = contextvars.ContextVar("current_user_org", default=None)
current_purpose_var = contextvars.ContextVar("current_purpose", default=None)


@contextmanager
def ai_purpose(purpose_name: str):
    """Context manager to set the AI purpose / circumstance for downstream LLM calls."""
    token = current_purpose_var.set(purpose_name)
    try:
        yield
    finally:
        current_purpose_var.reset(token)


@contextmanager
def ai_project_context(project_token: Optional[str] = None, project_name: Optional[str] = None):
    """Context manager to set the project token and project name for downstream LLM calls."""
    t_tok = current_project_token_var.set(project_token) if project_token is not None else None
    t_name = current_project_name_var.set(project_name) if project_name is not None else None
    try:
        yield
    finally:
        if t_tok is not None:
            current_project_token_var.reset(t_tok)
        if t_name is not None:
            current_project_name_var.reset(t_name)


# ── Response Extraction ────────────────────────────────────────────────────

def extract_content_from_response(data: dict) -> str:
    """
    Extract text content from any known AI response format.

    Supported formats:
    - Kimi / Proxies: data["completion"], data["assistant_message"]["content"][0]["text"]
    - OpenAI:         data["choices"][0]["message"]["content"]
    - BRN Llama:      data["response"] / data["text"] / data["content"]
    - Anthropic:      data["content"][0]["text"]
    """
    if not isinstance(data, dict):
        return ""

    # 0. Direct completion key (Kimi / proxy / custom LLM gateways)
    comp = data.get("completion")
    if comp and isinstance(comp, str) and comp.strip():
        return comp

    # 1. assistant_message (Anthropic / Bedrock / Kimi proxy format)
    asst_msg = data.get("assistant_message")
    if isinstance(asst_msg, dict):
        asst_content = asst_msg.get("content")
        if isinstance(asst_content, str) and asst_content.strip():
            return asst_content
        elif isinstance(asst_content, list):
            parts = []
            for block in asst_content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            if parts:
                return "".join(parts)

    # 2. OpenAI-style
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if content:
            return content

    # 3. BRN Llama / generic
    for key in ("response", "text", "output", "result"):
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            return val

    # 4. Anthropic-style: {"content": [{"type": "text", "text": "..."}]}
    content_list = data.get("content")
    if isinstance(content_list, list):
        parts = []
        for block in content_list:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, dict) and "text" in block:
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "".join(parts)

    # 5. Plain "content" string
    plain = data.get("content")
    if isinstance(plain, str) and plain:
        return plain

    return ""


def extract_reasoning_from_response(data: dict) -> str:
    """Extract reasoning/thinking content from OpenAI-style responses."""
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        message = choices[0].get("message", {})
        return message.get("reasoning_content", "") or ""
    return ""


# ── Payload & Header Builders ──────────────────────────────────────────────

def _build_brn_payload(
    system_prompt: str,
    user_content: str,
    model_name: str,
    stream: bool = False,
    **extra,
) -> dict:
    """Build payload for BRN Llama API."""
    prompt = f"{system_prompt}\n\n{user_content}" if system_prompt else user_content
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": stream,
        "agent_id": settings.brn_agent_id,
        "platform_id": settings.brn_platform_id,
        # "max_tokens": settings.brn_max_tokens,
        "temperature": extra.get("temperature", settings.brn_temperature),
    }
    return payload


def _build_brn_payload_from_messages(
    messages: list,
    model_name: str,
    stream: bool = False,
    **extra,
) -> dict:
    """Build BRN Llama payload from OpenAI-style messages list, setting top-level image fields if present."""
    parts = []
    found_image_url = None

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        img_val = block.get("image_url")
                        if isinstance(img_val, dict):
                            found_image_url = img_val.get("url")
                        elif isinstance(img_val, str):
                            found_image_url = img_val
        elif isinstance(content, str):
            if role == "system":
                parts.insert(0, content)
            else:
                parts.append(content)

    prompt = "\n\n".join(parts)
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": stream,
        "agent_id": settings.brn_agent_id,
        "platform_id": settings.brn_platform_id,
        "temperature": extra.get("temperature", settings.brn_temperature),
    }

    if found_image_url:
        payload["image"] = found_image_url
        payload["images"] = [found_image_url]
        payload["image_url"] = found_image_url

    return payload


def _build_openai_payload(
    messages: list,
    model_name: str,
    stream: bool = False,
    **extra,
) -> dict:
    """Build payload for OpenAI-compatible API."""
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }
    # Only add chat_template_kwargs for DeepSeek models to avoid 400 Bad Request on standard endpoints like Gemini
    if "deepseek" in model_name.lower():
        payload["chat_template_kwargs"] = {"thinking": False}

    if "temperature" in extra:
        payload["temperature"] = extra["temperature"]
    if "response_format" in extra:
        payload["response_format"] = extra["response_format"]
    if "max_tokens" in extra and extra["max_tokens"] is not None:
        payload["max_tokens"] = extra["max_tokens"]
    return payload


def _get_brn_headers() -> dict:
    return {"Content-Type": "application/json"}


def _get_openai_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


# ── Resolution Helpers ─────────────────────────────────────────────────────

def is_brn_llama_enabled() -> bool:
    """Check if BRN Llama mode is active from settings."""
    return bool(getattr(settings, "use_brn_llama", False))


def has_image_content(messages: list) -> bool:
    """Check if any message payload contains an image_url block for multimodal vision analysis."""
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
    return False


def resolve_url(api_url: Optional[str] = None) -> str:
    """Resolve the correct AI endpoint URL."""
    if is_brn_llama_enabled():
        return settings.brn_llama_url

    if api_url:
        url = api_url.strip()
    else:
        url = settings.ai_api_url

    # Normalize OpenAI-compatible URLs (non-BRN) to make sure they end with chat/completions
    if not is_brn_llama_enabled() and url != settings.brn_llama_url:
        if url and not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
            
    return url


def resolve_model(model: Optional[str] = None) -> str:
    """Resolve the correct model name."""
    if is_brn_llama_enabled():
        return settings.brn_model
    if model:
        return model
    return settings.ai_model


def resolve_key(api_key: Optional[str] = None) -> Optional[str]:
    """Resolve the API key (None for BRN Llama)."""
    if is_brn_llama_enabled():
        return None  # BRN Llama doesn't use API keys
    return api_key or settings.ai_api_key


def check_api_key(api_key: Optional[str] = None) -> bool:
    """Return True if the API key is configured (or not needed for BRN Llama)."""
    if is_brn_llama_enabled():
        return True
    key = api_key or settings.ai_api_key
    return bool(key and key != "your-api-key-here")


def check_ai_allowance(
    user_id: Optional[int] = None,
    organization_name: Optional[str] = None,
    project_token: Optional[str] = None,
    model_name: Optional[str] = None,
    messages: Optional[list] = None,
    estimated_tokens: Optional[int] = None,
    estimated_cost: Optional[float] = None,
) -> float:
    """
    Synchronously validates AI allowance using TokenOps before making the LLM call.
    For PAYG organizations, atomically reserves estimated cost in-flight.
    Raises HTTPException (402 or 403) if blocked, unauthorized, or exhausted.
    Returns the reserved cost amount (float).
    """
    reserved_cost = 0.0
    from fastapi import HTTPException
    from app.core.database import SessionLocal
    from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator
    from tokenops.services.tenant_resolver_service import TenantResolverService

    u_id = user_id or current_user_id_var.get()
    p_token = project_token or current_project_token_var.get()
    user_org = organization_name or current_user_org_var.get()

    target_tenant = None
    db = SessionLocal()
    try:
        from tokenops.services.project_token_resolver import resolve_or_ensure_project_token
        p_token, p_name = resolve_or_ensure_project_token(
            session=db,
            user_id=u_id,
            organization_name=user_org,
            candidate_project_token=p_token,
            candidate_project_name=current_project_name_var.get()
        )
        if p_token:
            current_project_token_var.set(p_token)
            if p_name:
                current_project_name_var.set(p_name)

        resolver = TenantResolverService(db)

        if p_token:
            # 1. Resolve project owner organization UUID
            try:
                project_org_id, project_org = resolver.resolve(p_token)
                target_tenant = project_org.name
            except Exception:
                if user_org:
                    active_org_id, active_org = resolver.resolve(user_org)
                    project_org_id, project_org = active_org_id, active_org
                    target_tenant = active_org.name
                else:
                    raise

            # 2. If user active organization is present in context, enforce strict UUID match
            if user_org and target_tenant != user_org:
                active_org_id, active_org = resolver.resolve(user_org)
                if active_org_id != project_org_id:
                    raise HTTPException(
                        status_code=403,
                        detail="CROSS_TENANT_PROJECT_ACCESS_DENIED"
                    )
        elif user_org:
            # Non-project request with active user organization context
            active_org_id, active_org = resolver.resolve(user_org)
            target_tenant = active_org.name
        elif u_id:
            # Authenticated user without project or active org context
            raise HTTPException(
                status_code=403,
                detail="ORGANIZATION_NOT_FOUND"
            )

        if target_tenant:
            if estimated_tokens is None and messages and isinstance(messages, list):
                total_input_chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
                estimated_tokens = max(100, total_input_chars // 4)

            orchestrator = TokenOpsOrchestrator.create(db)
            reserved_cost = orchestrator.pre_execute(
                user_id=u_id,
                organization_name=target_tenant,
                model_name=model_name,
                estimated_tokens=estimated_tokens,
                estimated_cost=estimated_cost
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check AI allowance: {e}", exc_info=True)
        raise HTTPException(status_code=403, detail="ORGANIZATION_NOT_FOUND")
    finally:
        db.close()

    return reserved_cost


def log_ai_usage(
    messages: list,
    response_text: str,
    model_name: str,
    user_id: Optional[int] = None,
    organization_name: Optional[str] = None,
    project_token: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    response_data: Optional[dict] = None,
    reserved_cost: Optional[float] = None,
    purpose: Optional[str] = None,
    project_name: Optional[str] = None,
):
    """
    Asynchronously logs AI token usage and calculations to the database using TokenOps.
    
    Extracts actual token counts from the API response payload if available (e.g. usage.input_tokens / output_tokens / prompt_tokens / completion_tokens).
    If token count is not provided by the API, computes from input messages and generated response text.
    """
    try:
        from app.core.database import SessionLocal
        from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator

        # Get values from ContextVars if not explicitly provided
        u_id = user_id or current_user_id_var.get()
        p_token = project_token or current_project_token_var.get()
        p_name = project_name or current_project_name_var.get()
        user_org = organization_name or current_user_org_var.get()
        target_tenant = user_org or p_token
        ai_purpose_val = purpose or current_purpose_var.get() or "AI Consumption"

        # 1. Extract actual token counts from API response payload if present
        if response_data and isinstance(response_data, dict):
            usage = response_data.get("usage")
            if isinstance(usage, dict):
                if prompt_tokens is None:
                    p_tok = usage.get("input_tokens") if usage.get("input_tokens") is not None else usage.get("prompt_tokens")
                    if isinstance(p_tok, int) and p_tok >= 0:
                        prompt_tokens = p_tok
                
                if completion_tokens is None:
                    c_tok = usage.get("output_tokens") if usage.get("output_tokens") is not None else usage.get("completion_tokens")
                    if isinstance(c_tok, int) and c_tok >= 0:
                        completion_tokens = c_tok

        # For streaming or endpoints without explicit usage payloads, compute from characters
        if prompt_tokens is None and messages and isinstance(messages, list):
            total_input_chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
            prompt_tokens = max(1, total_input_chars // 4)
        if completion_tokens is None and response_text:
            completion_tokens = max(1, len(str(response_text)) // 4)

        db = SessionLocal()
        try:
            from tokenops.services.project_token_resolver import resolve_or_ensure_project_token
            from tokenops.services.tenant_resolver_service import TenantResolverService

            # Strictly resolve project token and project name
            p_token, p_name = resolve_or_ensure_project_token(
                session=db,
                user_id=u_id,
                organization_name=user_org,
                candidate_project_token=p_token,
                candidate_project_name=p_name,
            )

            # Resolve tenant organization name properly
            resolver = TenantResolverService(db)
            target_tenant = user_org
            if p_token:
                try:
                    _, proj_org = resolver.resolve(p_token)
                    target_tenant = proj_org.name
                except Exception:
                    pass
            if not target_tenant and user_org:
                try:
                    _, active_org = resolver.resolve(user_org)
                    target_tenant = active_org.name
                except Exception:
                    pass

            if target_tenant:
                orchestrator = TokenOpsOrchestrator.create(db)
                orchestrator.post_execute(
                    user_id=u_id,
                    organization_name=target_tenant,
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    reserved_cost=reserved_cost,
                    purpose=ai_purpose_val,
                    project_token=p_token,
                    project_name=p_name,
                )
                logger.info(f"Logged AI Usage to TokenOps: {prompt_tokens} prompt, {completion_tokens} completion for tenant {target_tenant} (user: {u_id}, purpose: {ai_purpose_val}, project: {p_name}).")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to log AI usage via TokenOps: {e}", exc_info=True)


# ── Core Non-Streaming Call ────────────────────────────────────────────────

async def call_llm(
    messages: list,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
    retries: int = 3,
    retry_delay: float = 5.0,
    purpose: Optional[str] = None,
    project_token: Optional[str] = None,
    project_name: Optional[str] = None,
    **extra,
) -> dict:
    """
    Unified non-streaming LLM call.

    Args:
        messages: OpenAI-style messages list [{"role": ..., "content": ...}]
        api_url: Override API URL
        api_key: Override API key
        model: Override model name
        timeout: Request timeout in seconds
        retries: Number of retry attempts (1 = no retry)
        retry_delay: Seconds between retries
        **extra: Additional payload params (temperature, response_format, etc.)

    Returns:
        Raw response dict from the API (format varies per provider).
        Use extract_content_from_response() to get the text.
    """
    url = resolve_url(api_url)
    model_name = resolve_model(model)
    reserved_cost = check_ai_allowance(model_name=model_name, messages=messages)

    use_brn = is_brn_llama_enabled() or (url == settings.brn_llama_url)

    if use_brn:
        payload = _build_brn_payload_from_messages(messages, model_name, stream=False, **extra)
        headers = _get_brn_headers()
    else:
        key = resolve_key(api_key)
        payload = _build_openai_payload(messages, model_name, stream=False, **extra)
        headers = _get_openai_headers(key)

    async with httpx.AsyncClient(timeout=timeout) as client:
        last_err = None
        data = None
        for attempt in range(retries):
            try:
                if attempt > 0:
                    import asyncio
                    await asyncio.sleep(retry_delay * attempt)
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code >= 400:
                    prompt_text = str(payload.get("prompt", ""))
                    prompt_preview = prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text
                    
                    # Save full prompt to a temp file for debugging
                    import tempfile
                    try:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', prefix='brn_error_', delete=False) as f:
                            json.dump(payload, f, indent=2)
                            temp_path = f.name
                        logger.error(f"HTTPError: {response.status_code} - {response.text}\nPayload size: {len(str(payload))}\nPrompt Preview: {prompt_preview}\nFull payload saved to: {temp_path}")
                    except Exception as log_err:
                        logger.error(f"HTTPError: {response.status_code} - {response.text} - Payload size: {len(str(payload))} (Failed to save full payload: {log_err})")

                response.raise_for_status()
                data = response.json()
                
                # Log usage with reservation settlement
                try:
                    response_text = extract_content_from_response(data)
                    log_ai_usage(
                        messages,
                        response_text,
                        model_name,
                        response_data=data,
                        reserved_cost=reserved_cost,
                        purpose=purpose,
                        project_token=project_token,
                        project_name=project_name,
                    )
                except Exception as log_err:
                    logger.error(f"Failed to log AI usage inside call_llm: {log_err}")
                
                # Print raw response for debugging
                print("\n" + "="*80)
                print("RAW LLM RESPONSE (call_llm)")
                print("="*80)
                print(f"URL: {url}")
                print(f"Model: {model_name}")
                print(f"Status Code: {response.status_code}")
                print(f"Response Headers: {dict(response.headers)}")
                print("-"*80)
                print("Response Body:")
                print(json.dumps(data, indent=2))  # First 2000 chars
                print("="*80 + "\n")
                
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning(f"LLM call attempt {attempt + 1}/{retries} failed ({type(e).__name__}: {e}). Retrying in {retry_delay * (attempt + 1)}s...")
                if attempt == retries - 1:
                    break
        if last_err:
            if reserved_cost and reserved_cost > 0:
                try:
                    from app.core.database import SessionLocal
                    from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator
                    from tokenops.services.tenant_resolver_service import TenantResolverService
                    tok_or_org = project_token or current_project_token_var.get() or current_user_org_var.get()
                    if tok_or_org:
                        db = SessionLocal()
                        try:
                            resolver = TenantResolverService(db)
                            _, org = resolver.resolve(tok_or_org)
                            orchestrator = TokenOpsOrchestrator.create(db)
                            orchestrator.release_reservation(organization_name=org.name, reserved_cost=reserved_cost)
                        finally:
                            db.close()
                except Exception:
                    pass
            raise last_err

    return data


async def call_llm_and_extract(
    messages: list,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
    retries: int = 3,
    retry_delay: float = 5.0,
    purpose: Optional[str] = None,
    project_token: Optional[str] = None,
    project_name: Optional[str] = None,
    **extra,
) -> str:
    """
    Call LLM and return the extracted text content.
    Convenience wrapper around call_llm() + extract_content_from_response().
    """
    data = await call_llm(
        messages=messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
        purpose=purpose,
        project_token=project_token,
        project_name=project_name,
        **extra,
    )
    content = extract_content_from_response(data)
    
    # Print extracted content for debugging safely (preventing CP1252 crashes on Windows)
    try:
        import sys
        sys_encoding = sys.stdout.encoding or 'utf-8'
        safe_content = content.encode(sys_encoding, errors='replace').decode(sys_encoding)
        print("\n" + "="*80)
        print("EXTRACTED CONTENT (call_llm_and_extract)")
        print("="*80)
        print(f"Content Length: {len(content)} chars")
        print("-"*80)
        print("Content Preview:")
        print(safe_content)  # First 1000 chars
        print("="*80 + "\n")
    except Exception as print_err:
        logger.debug(f"Failed to safely print extracted content: {print_err}")
    
    # Strip <think> blocks from models that embed reasoning in content
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    content = re.sub(r'<think>.*', '', content, flags=re.DOTALL).strip()
    return content


# ── Core Streaming Call ────────────────────────────────────────────────────

async def call_llm_streaming(
    messages: list,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
    purpose: Optional[str] = None,
    project_token: Optional[str] = None,
    project_name: Optional[str] = None,
    user_id: Optional[int] = None,
    organization_name: Optional[str] = None,
    reserved_cost: Optional[float] = None,
) -> AsyncGenerator[str, None]:
    """
    Unified streaming LLM call.

    Yields SSE-formatted lines: "data: {...}\n\n" with normalized content chunks.
    The yielded JSON always follows OpenAI delta format:
        {"choices": [{"delta": {"content": "...", "reasoning_content": "..."}}]}

    Handles:
    - BRN Llama (non-streaming API → single chunk + DONE)
    - BRN Llama streaming with Anthropic-style response
    - OpenAI-compatible SSE streaming
    """
    url = resolve_url(api_url)
    model_name = resolve_model(model)
    u_id = user_id or current_user_id_var.get()
    u_org = organization_name or current_user_org_var.get()
    p_token = project_token or current_project_token_var.get()
    p_name = project_name or current_project_name_var.get()
    purp = purpose or current_purpose_var.get() or "AI Consumption"

    if reserved_cost is None:
        reserved_cost = check_ai_allowance(
            user_id=u_id,
            organization_name=u_org,
            project_token=p_token,
            model_name=model_name,
            messages=messages
        )
    use_brn = is_brn_llama_enabled() or (url == settings.brn_llama_url)

    client = httpx.AsyncClient(timeout=timeout)
    response_content_buffer = []

    try:
        if use_brn:
            # BRN Llama: try streaming first, fallback to non-streaming
            payload = _build_brn_payload_from_messages(messages, model_name, stream=True)
            headers = _get_brn_headers()

            try:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        resp_text = body.decode(errors='replace')
                        prompt_text = str(payload.get("prompt", ""))
                        prompt_preview = prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text
                        
                        import tempfile
                        try:
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', prefix='brn_stream_error_', delete=False) as f:
                                json.dump(payload, f, indent=2)
                                temp_path = f.name
                            logger.error(f"HTTPError (Stream Init): {response.status_code} - {resp_text}\nPayload size: {len(str(payload))}\nPrompt Preview: {prompt_preview}\nFull payload saved to: {temp_path}")
                        except Exception as log_err:
                            logger.error(f"HTTPError (Stream Init): {response.status_code} - {resp_text} - Payload size: {len(str(payload))} (Failed to save full payload: {log_err})")

                    response.raise_for_status()

                    # Check content type to determine if it's truly streaming
                    content_type = response.headers.get("content-type", "")

                    if "text/event-stream" in content_type or "stream" in content_type:
                        # True SSE stream — parse each line
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                text = _extract_streaming_chunk_text(data_json)
                                if text:
                                    chunk = {
                                        "choices": [{
                                            "delta": {
                                                "content": text,
                                                "reasoning_content": None,
                                            }
                                        }]
                                    }
                                    response_content_buffer.append(text)
                                    yield f"data: {json.dumps(chunk)}\n\n"
                            except json.JSONDecodeError:
                                continue
                        yield "data: [DONE]\n\n"
                    else:
                        # Non-streaming response body
                        body = await response.aread()
                        data = json.loads(body)
                        content = extract_content_from_response(data)
                        chunk = {
                            "choices": [{
                                "delta": {
                                    "content": content if content else None,
                                    "reasoning_content": None,
                                }
                            }]
                        }
                        if content:
                            response_content_buffer.append(content)
                        yield f"data: {json.dumps(chunk)}\n\n"
                        yield "data: [DONE]\n\n"
            except Exception as stream_err:
                # Fallback: non-streaming BRN call
                logger.warning(f"BRN streaming failed ({stream_err}), falling back to non-streaming")
                payload["stream"] = False
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code >= 400:
                    logger.error(f"HTTPError: {response.status_code} - {response.text} - Payload size: {len(str(payload))}")
                response.raise_for_status()
                data = response.json()
                content = extract_content_from_response(data)
                chunk = {
                    "choices": [{
                        "delta": {
                            "content": content if content else None,
                            "reasoning_content": None,
                        }
                    }]
                }
                if content:
                    response_content_buffer.append(content)
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

        else:
            # OpenAI-compatible SSE streaming
            key = api_key or settings.ai_api_key
            payload = _build_openai_payload(messages, model_name, stream=True)
            headers = _get_openai_headers(key)

            # State machine for <think> tags inside content
            inside_think = False
            think_buffer = ""

            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            text = _extract_streaming_chunk_text(data_json)
                            reasoning = ""

                            # OpenAI delta format
                            if "choices" in data_json and data_json["choices"]:
                                delta = data_json["choices"][0].get("delta", {})
                                raw_content = delta.get("content") or ""
                                reasoning = delta.get("reasoning_content") or ""
                            else:
                                raw_content = text or ""

                            # Handle <think> tags inside content
                            clean_content = ""
                            if raw_content:
                                if inside_think:
                                    end_idx = raw_content.find("</think>")
                                    if end_idx != -1:
                                        think_buffer += raw_content[:end_idx]
                                        reasoning += think_buffer
                                        think_buffer = ""
                                        inside_think = False
                                        clean_content = raw_content[end_idx + len("</think>"):]
                                    else:
                                        think_buffer += raw_content
                                else:
                                    start_idx = raw_content.find("<think>")
                                    if start_idx != -1:
                                        clean_content = raw_content[:start_idx]
                                        remaining = raw_content[start_idx + len("<think>"):]
                                        end_idx = remaining.find("</think>")
                                        if end_idx != -1:
                                            reasoning += remaining[:end_idx]
                                            clean_content += remaining[end_idx + len("</think>"):]
                                        else:
                                            inside_think = True
                                            think_buffer = remaining
                                    else:
                                        clean_content = raw_content

                            if clean_content or reasoning:
                                chunk = {
                                    "choices": [{
                                        "delta": {
                                            "content": clean_content if clean_content else None,
                                            "reasoning_content": reasoning if reasoning else None,
                                        }
                                    }]
                                }
                                if clean_content:
                                    response_content_buffer.append(clean_content)
                                yield f"data: {json.dumps(chunk)}\n\n"
                        except json.JSONDecodeError:
                            continue

            yield "data: [DONE]\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        await client.aclose()
        # Log AI Cost usage
        try:
            full_response_text = "".join(response_content_buffer)
            log_ai_usage(
                messages=messages,
                response_text=full_response_text,
                model_name=model_name,
                user_id=u_id,
                organization_name=u_org,
                project_token=p_token,
                project_name=p_name,
                reserved_cost=reserved_cost,
                purpose=purp,
            )
        except Exception as log_err:
            logger.error(f"Failed to log AI usage in call_llm_streaming finally block: {log_err}")


def _extract_streaming_chunk_text(data: dict) -> str:
    """
    Extract text from a single streaming chunk.

    Handles:
    - OpenAI delta: {"choices": [{"delta": {"content": "..."}}]}
    - Anthropic:    {"content": [{"type": "text", "text": "..."}]}
    - BRN plain:    {"response": "..."} / {"text": "..."}
    """
    # OpenAI delta
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        delta = choices[0].get("delta", {})
        return delta.get("content", "") or ""

    # Anthropic-style
    content_list = data.get("content")
    if isinstance(content_list, list):
        parts = []
        for block in content_list:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        if parts:
            return "".join(parts)

    # BRN plain
    for key in ("response", "text"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val

    # Plain content string
    plain = data.get("content")
    if isinstance(plain, str):
        return plain

    return ""
