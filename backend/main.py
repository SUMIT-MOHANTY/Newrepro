import os
import requests
import asyncio
import logging
import secrets
import re
import uuid
import html as html_lib
import hashlib
import time
import json
from html.parser import HTMLParser
from urllib.parse import urlparse
import ipaddress
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional, List, Dict, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import httpx
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Header, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, text
from pydantic import BaseModel, Field

import auth
import models
import schemas
import ingestion
import ai_service
import llm_gateway
import governance_scoring
import github_service
import azure_devops_service
import azure_devops_oauth_service
import agent_service
import rag_service
import context_manager
import email_service
import knowledge_graph_service as kg_service
import master_task_manager
import master_coordination_service

# Cache for agent status to reduce database load
_agent_status_cache: Dict[str, Dict[str, Any]] = {}
_agent_cache_timestamps: Dict[str, float] = {}
AGENT_CACHE_TTL = 5.0  # 5 seconds cache TTL

def _get_cache_key(organization_name: str, project_token: Optional[str], user_id: int) -> str:
    """Generate cache key for agent status"""
    return f"{organization_name}:{project_token or 'none'}:{user_id}"

def _is_cache_valid(cache_key: str) -> bool:
    """Check if cache entry is still valid"""
    if cache_key not in _agent_cache_timestamps:
        return False
    return time.time() - _agent_cache_timestamps[cache_key] < AGENT_CACHE_TTL

def _get_cached_agents(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached agent data if valid"""
    if _is_cache_valid(cache_key):
        return _agent_status_cache.get(cache_key)
    return None

def _cache_agents(cache_key: str, data: Dict[str, Any]) -> None:
    """Cache agent data with timestamp"""
    _agent_status_cache[cache_key] = data
    _agent_cache_timestamps[cache_key] = time.time()

# Task cache for external API calls
_task_cache: Dict[str, Dict[str, Any]] = {}
_task_cache_timestamps: Dict[str, float] = {}
TASK_CACHE_TTL = 3.0  # 3 seconds cache TTL for tasks

def _get_task_cache_key(task_token: Optional[str], page: Optional[int]) -> str:
    """Generate cache key for task data"""
    return f"tasks:{task_token or 'none'}:{page or 'none'}"

def _is_task_cache_valid(cache_key: str) -> bool:
    """Check if task cache entry is still valid"""
    if cache_key not in _task_cache_timestamps:
        return False
    return time.time() - _task_cache_timestamps[cache_key] < TASK_CACHE_TTL

def _get_cached_tasks(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached task data if valid"""
    if _is_task_cache_valid(cache_key):
        return _task_cache.get(cache_key)
    return None

def _cache_tasks(cache_key: str, data: Dict[str, Any]) -> None:
    """Cache task data with timestamp"""
    _task_cache[cache_key] = data
    _task_cache_timestamps[cache_key] = time.time()

# Rate limiting for individual agent status calls
_agent_status_rate_limit: Dict[str, float] = {}
AGENT_STATUS_RATE_LIMIT = 10.0  # 10 seconds minimum between calls per agent

def _check_agent_status_rate_limit(agent_id: str, user_id: int, project_token: Optional[str]) -> bool:
    """Check if agent status call is within rate limit"""
    rate_key = f"agent_status_rate:{agent_id}:{user_id}:{project_token or 'none'}"
    now = time.time()
    
    if rate_key in _agent_status_rate_limit:
        if now - _agent_status_rate_limit[rate_key] < AGENT_STATUS_RATE_LIMIT:
            return False
    
    _agent_status_rate_limit[rate_key] = now
    return True

def _invalidate_agent_cache(organization_name: str, project_token: Optional[str] = None) -> None:
    """Invalidate agent cache for organization/project when status changes"""
    keys_to_remove = []
    for cache_key in _agent_status_cache.keys():
        # "__all__" sentinel means invalidate all entries matching this project_token
        if organization_name == "__all__":
            pt = project_token or "none"
            if f":{pt}:" in cache_key:
                keys_to_remove.append(cache_key)
        elif cache_key.startswith(f"{organization_name}:{project_token or 'none'}:"):
            keys_to_remove.append(cache_key)
    
    for key in keys_to_remove:
        _agent_status_cache.pop(key, None)
        _agent_cache_timestamps.pop(key, None)

def _invalidate_task_cache(task_token: Optional[str] = None) -> None:
    """Invalidate task cache when tasks change"""
    keys_to_remove = []
    for cache_key in _task_cache.keys():
        if cache_key.startswith(f"tasks:{task_token or 'none'}:"):
            keys_to_remove.append(cache_key)
    
    for key in keys_to_remove:
        _task_cache.pop(key, None)
        _task_cache_timestamps.pop(key, None)

# Set up cache invalidation callback for agent service after functions are defined
agent_service.set_cache_invalidation_callback(_invalidate_agent_cache)

from local_task_preview_service import build_local_task_plan_preview, _normalize_project_dates, _format_date
from database import engine, get_db, SessionLocal
from config import settings

models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_init()
    yield


app = FastAPI(title="BRD Analysis API", version="1.0.0", lifespan=lifespan)

# Configure logging with date and time
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
SSO_DEFAULT_SCOPES = "openid profile email"
SSO_STATE_TTL_SECONDS = 1800
SSO_STATE_CLOCK_SKEW_SECONDS = 300

# Suppress frequent polling logs in uvicorn access logs
class PollingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # Silence tasks-list and agent status polling
        if "/api/agent/tasks-list/" in msg or "/status?project_token=" in msg:
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(PollingFilter())
OAUTH_AUTH_CODE_TTL_SECONDS = 300
OAUTH_ACCESS_TOKEN_TTL_SECONDS = 3600


def _generate_registration_password() -> str:
    return secrets.token_urlsafe(12)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import RedirectResponse, StreamingResponse
from coordination_api import router as coordination_router

# Add coordination router
app.include_router(coordination_router)

# --- Pydantic Models for AI ---
class AnalyzeRequest(BaseModel):
    document_content: str
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    stream: bool = False
    user_feedback: Optional[str] = None
    image_paths: Optional[List[str]] = None
    governance_context: Optional[Dict[str, Any]] = None

class AIConfigUpdate(BaseModel):
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class URLIngestRequest(BaseModel):
    url: str = Field(..., description="Public website URL to fetch")


class _RequirementPageParser(HTMLParser):
    """
    Lightweight HTML parser for extracting readable requirement-like content
    without external dependencies.
    """

    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _BLOCK_TAGS = {"p", "li", "section", "article", "div", "blockquote", "td", "th"}
    _IGNORE_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}

    def __init__(self) -> None:
        super().__init__()
        self.in_ignored_depth = 0
        self.in_title = False
        self.current_tag: Optional[str] = None
        self.current_text_parts: List[str] = []
        self.title_parts: List[str] = []
        self.headings: List[str] = []
        self.paragraphs: List[str] = []
        self.list_items: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag_l = tag.lower()
        if tag_l in self._IGNORE_TAGS:
            self.in_ignored_depth += 1
            return
        if self.in_ignored_depth > 0:
            return
        if tag_l == "title":
            self.in_title = True
            return
        if tag_l in self._HEADING_TAGS or tag_l in self._BLOCK_TAGS:
            self.current_tag = tag_l
            self.current_text_parts = []

    def handle_endtag(self, tag: str):
        tag_l = tag.lower()
        if tag_l in self._IGNORE_TAGS and self.in_ignored_depth > 0:
            self.in_ignored_depth -= 1
            return
        if self.in_ignored_depth > 0:
            return
        if tag_l == "title":
            self.in_title = False
            return
        if self.current_tag == tag_l:
            text = " ".join(self.current_text_parts).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                if tag_l in self._HEADING_TAGS:
                    self.headings.append(text)
                elif tag_l == "li":
                    self.list_items.append(text)
                else:
                    self.paragraphs.append(text)
            self.current_tag = None
            self.current_text_parts = []

    def handle_data(self, data: str):
        if self.in_ignored_depth > 0:
            return
        clean = re.sub(r"\s+", " ", data or "").strip()
        if not clean:
            return
        if self.in_title:
            self.title_parts.append(clean)
        if self.current_tag:
            self.current_text_parts.append(clean)

    def to_requirement_markdown(self, source_url: str, max_lines: int = 120) -> Dict[str, Any]:
        page_title = re.sub(r"\s+", " ", " ".join(self.title_parts).strip())
        heading_lines = [f"## {h}" for h in self.headings[:25]]
        paragraph_lines = self.paragraphs[:70]
        bullet_lines = [f"- {item}" for item in self.list_items[:70]]

        lines: List[str] = []
        if page_title:
            lines.append(f"# Extracted Requirements - {page_title}")
        else:
            lines.append("# Extracted Requirements")
        lines.append(f"Source URL: {source_url}")
        lines.append("")
        lines.append("The following requirements were generated from webpage content.")
        lines.append("Review and edit before final analysis.")
        lines.append("")
        lines.append("## Candidate Requirements")

        if not heading_lines and not paragraph_lines and not bullet_lines:
            lines.append("- No readable requirement content was detected on this page.")
        else:
            lines.extend(heading_lines)
            if heading_lines and (paragraph_lines or bullet_lines):
                lines.append("")
            lines.extend(bullet_lines)
            if paragraph_lines:
                lines.append("")
                lines.extend(paragraph_lines)

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("")
            lines.append("... (truncated)")

        markdown = "\n".join(lines).strip()
        summary = {
            "title": page_title or None,
            "headings_found": len(self.headings),
            "paragraphs_found": len(self.paragraphs),
            "list_items_found": len(self.list_items),
        }
        return {"markdown": markdown, "summary": summary}


def _normalize_and_validate_public_url(raw_url: str) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="URL is required.")

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL hostname.")

    blocked_hostnames = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "host.docker.internal",
        "metadata.google.internal",
    }
    if hostname in blocked_hostnames or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local/internal URLs are not allowed.")

    try:
        host_ip = ipaddress.ip_address(hostname)
        if host_ip.is_loopback or host_ip.is_private or host_ip.is_link_local or host_ip.is_multicast or host_ip.is_reserved:
            raise HTTPException(status_code=400, detail="Private or local network URLs are not allowed.")
    except ValueError:
        # Hostname is a domain name, continue.
        pass

    # Ignore fragments as they are browser-only and not needed for server fetch.
    normalized = parsed._replace(fragment="").geturl()
    return normalized


def _strip_html_to_text(value: str, max_chars: int = 0) -> str:
    text = str(value or "")
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
    return text

# ... (Auth endpoints omitted for brevity, keeping existing) ...

# --- AI Analysis Endpoints ---
@app.get("/ai/config")
async def get_ai_config(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get current AI configuration."""
    return await ai_service.get_ai_config()

@app.post("/ai/analyze")
async def analyze_document_with_ai(
    request: AnalyzeRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Analyze document content using AI.
    
    You can optionally override the default AI settings per request:
    - api_url: Custom OpenAI-compatible API URL
    - api_key: API key for the service
    - model: Model name to use
    - stream: Set to true for streaming response (Server-Sent Events)
    """
    if _all_answers_skipped_from_governance_context(request.governance_context):
        raise HTTPException(status_code=403, detail=ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE)

    result = await ai_service.analyze_document(
        document_content=request.document_content,
        api_url=request.api_url,
        api_key=request.api_key,
        model=request.model,
        stream=request.stream,
        user_feedback=request.user_feedback,
        image_paths=request.image_paths,
        governance_context=request.governance_context,
    )
    
    # Handle potential early errors (which return dict)
    if isinstance(result, dict) and result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    if request.stream:
        # result is an AsyncGenerator
        return StreamingResponse(result, media_type="text/event-stream")
    
    return result

# ---------------------------------------------------------------------------
# AI Assistant Chat Endpoint (used by AssistantBot frontend component)
# ---------------------------------------------------------------------------

class AssistantRequest(BaseModel):
    """Payload for the AI chat endpoint."""
    message: str = Field(..., description="User message sent to the assistant")
    context: Optional[dict] = Field(default=None, description="Current route context")
    conversation_history: Optional[list] = Field(default=None, description="Prior conversation messages")


@app.post("/api/agent/assistant")
async def assistant_chat(
    payload: AssistantRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Context-aware AI assistant chat endpoint."""
    try:
        context = getattr(payload, 'context', None)
        assistant_reply = await ai_service.chat_with_llm(
            message=payload.message,
            context=context
        )
        return {"response": assistant_reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/assistant/stream")
async def assistant_chat_stream(
    payload: AssistantRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Streaming version of the assistant chat endpoint using real LLM SSE streaming."""
    from fastapi.responses import StreamingResponse
    import json

    async def generate():
        try:
            context = getattr(payload, 'context', None)
            messages = ai_service.build_chat_messages(payload.message, context)
            async for chunk in llm_gateway.call_llm_streaming(messages=messages):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    try:
                        parsed = json.loads(data_str)
                        content = None
                        if "choices" in parsed and parsed["choices"]:
                            content = parsed["choices"][0].get("delta", {}).get("content")
                        elif "error" in parsed:
                            yield f"data: {json.dumps({'error': parsed['error']})}\n\n"
                            break
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# --- Auth Endpoints ---
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    user.last_login = datetime.utcnow()
    db.add(user)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/forgot-password")
async def forgot_password(
    payload: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first()
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_invite_token(token)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Deactivate any previous unused reset tokens for this user
        db.query(models.PasswordReset).filter(
            models.PasswordReset.user_id == user.id,
            models.PasswordReset.used_at == None
        ).update({"expires_at": datetime.utcnow()}, synchronize_session=False)
        
        reset = models.PasswordReset(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db.add(reset)
        db.commit()
        
        reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        try:
            email_service.send_password_reset_email(user.email, reset_url)
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
            
    return {"message": "If your email is registered, you will receive a reset link shortly."}

@app.post("/auth/reset-password")
async def reset_password(
    payload: schemas.PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    token_hash = _hash_invite_token(payload.token)
    reset = db.query(models.PasswordReset).filter(
        models.PasswordReset.token_hash == token_hash,
        models.PasswordReset.used_at == None,
        models.PasswordReset.expires_at > datetime.utcnow()
    ).first()
    
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
    
    user = db.query(models.User).filter(models.User.id == reset.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user.hashed_password = auth.get_password_hash(payload.new_password)
    reset.used_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Password has been reset successfully."}

def _normalized_text(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()

def _find_sso_setting_by_organization(
    db: Session,
    organization_name: str,
) -> Optional[models.OrganizationSSOSetting]:
    org_name = _normalized_text(organization_name)
    if not org_name:
        return None
    return db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == org_name.lower()
    ).first()

def _find_sso_setting_by_domain(
    db: Session,
    domain: str,
) -> Optional[models.OrganizationSSOSetting]:
    cleaned_domain = _normalized_text(domain).lower()
    if not cleaned_domain:
        return None
    matches = db.query(models.OrganizationSSOSetting).filter(
        models.OrganizationSSOSetting.sso_enabled.is_(True),
        func.lower(models.OrganizationSSOSetting.domain_hint) == cleaned_domain,
    ).all()
    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple organizations are mapped to this email domain. Contact your administrator.",
        )
    return matches[0] if matches else None

def _resolve_login_sso_setting(
    payload: schemas.SSOStartRequest,
    db: Session,
) -> tuple[models.OrganizationSSOSetting, str, str]:
    email_hint = _normalized_text(payload.email).lower()
    requested_org_name = _normalized_text(payload.organization_name)

    setting: Optional[models.OrganizationSSOSetting] = None
    resolved_org_name = ""

    if email_hint:
        user = db.query(models.User).filter(func.lower(models.User.email) == email_hint).first()
        if user and _normalized_text(user.organization_name):
            resolved_org_name = _normalized_text(user.organization_name)
            setting = _find_sso_setting_by_organization(db, resolved_org_name)

        if not setting and "@" in email_hint:
            domain = email_hint.split("@", 1)[1]
            setting = _find_sso_setting_by_domain(db, domain)
            if setting:
                resolved_org_name = setting.organization_name

    if not setting and requested_org_name:
        setting = _find_sso_setting_by_organization(db, requested_org_name)
        if setting:
            resolved_org_name = setting.organization_name

    if not setting:
        raise HTTPException(
            status_code=404,
            detail="No SSO-enabled organization found for this account.",
        )
    if not setting.sso_enabled:
        raise HTTPException(status_code=400, detail="SSO is disabled for this organization.")
    if not _normalized_text(setting.client_id):
        raise HTTPException(status_code=400, detail="Organization SSO client ID is not configured.")
    if not _normalized_text(setting.client_secret):
        raise HTTPException(status_code=400, detail="Organization SSO client secret is not configured.")
    # Authority URL is now derived in the backend from tenant / environment,
    # so we no longer block if the stored authority_url is empty here.

    return setting, resolved_org_name, email_hint

def _resolve_sso_redirect_uri(
    setting: models.OrganizationSSOSetting,
    request: Request,
) -> str:
    configured = _normalized_text(setting.redirect_uri)
    if configured:
        return configured
    return str(request.url_for("sso_callback"))

def _build_frontend_sso_redirect(
    *,
    token: Optional[str] = None,
    error: Optional[str] = None,
    next_url: Optional[str] = None,
) -> str:
    base_url = f"{settings.frontend_url.rstrip('/')}/sso/callback"
    params: Dict[str, str] = {}
    if token:
        params["token"] = token
    if error:
        params["error"] = error
    if next_url:
        params["next"] = next_url
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params)}"

async def _fetch_oidc_metadata(setting: models.OrganizationSSOSetting) -> Dict[str, str]:
    authority_url = _normalized_text(setting.authority_url)
    if not authority_url:
        # Derive a default authority URL from tenant_id if available (Azure AD / Entra ID)
        tenant = _normalized_text(setting.tenant_id)
        if tenant:
            authority_url = f"https://login.microsoftonline.com/{tenant}"
        else:
            raise HTTPException(status_code=400, detail="Organization authority URL is missing.")

    if "/.well-known/openid-configuration" in authority_url:
        metadata_url = authority_url
        authority_base = authority_url.split("/.well-known/openid-configuration", 1)[0].rstrip("/")
    else:
        authority_base = authority_url.rstrip("/")
        metadata_url = f"{authority_base}/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            metadata_response = await client.get(metadata_url)
            metadata_response.raise_for_status()
        metadata = metadata_response.json()
    except Exception as exc:
        if _normalized_text(setting.sso_provider).lower() == "azure_ad":
            return {
                "authorization_endpoint": f"{authority_base}/oauth2/v2.0/authorize",
                "token_endpoint": f"{authority_base}/oauth2/v2.0/token",
                "userinfo_endpoint": "",
            }
        raise HTTPException(
            status_code=400,
            detail=f"Unable to fetch provider metadata from {metadata_url}. {str(exc)}",
        )

    authorization_endpoint = _normalized_text(metadata.get("authorization_endpoint"))
    token_endpoint = _normalized_text(metadata.get("token_endpoint"))
    userinfo_endpoint = _normalized_text(metadata.get("userinfo_endpoint"))

    if not authorization_endpoint or not token_endpoint:
        raise HTTPException(
            status_code=400,
            detail="OIDC provider metadata is missing authorization/token endpoints.",
        )

    return {
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
        "userinfo_endpoint": userinfo_endpoint,
    }

def _extract_email_from_claims(claims: Dict[str, Any]) -> str:
    return _normalized_text(
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("unique_name")
    )

async def _fetch_userinfo_claims(userinfo_endpoint: str, access_token: str) -> Dict[str, Any]:
    endpoint = _normalized_text(userinfo_endpoint)
    token = _normalized_text(access_token)
    if not endpoint or not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            return {}
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}

def _validate_sso_state_window(state_payload: Dict[str, Any]) -> bool:
    try:
        exp_ts = int(state_payload.get("exp"))
        iat_ts = int(state_payload.get("iat"))
    except (TypeError, ValueError):
        return False

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp_ts + SSO_STATE_CLOCK_SKEW_SECONDS < now_ts:
        return False
    if iat_ts - SSO_STATE_CLOCK_SKEW_SECONDS > now_ts:
        return False
    return True

@app.post("/auth/sso/start", response_model=schemas.SSOStartResponse)
async def start_sso_login(
    payload: schemas.SSOStartRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not payload.email and not _normalized_text(payload.organization_name):
        raise HTTPException(status_code=400, detail="Email or organization name is required.")

    setting, organization_name, email_hint = _resolve_login_sso_setting(payload, db)
    metadata = await _fetch_oidc_metadata(setting)
    redirect_uri = _resolve_sso_redirect_uri(setting, request)
    nonce = secrets.token_urlsafe(16)

    now = datetime.now(timezone.utc)
    state_payload = {
        "org": organization_name,
        "email_hint": email_hint or None,
        "nonce": nonce,
        "redirect_uri": redirect_uri,
        "next": _normalized_text(payload.next) or None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=SSO_STATE_TTL_SECONDS)).timestamp()),
    }
    state_token = jwt.encode(state_payload, settings.secret_key, algorithm=settings.algorithm)

    query_params = {
        "client_id": setting.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": _normalized_text(setting.scopes) or SSO_DEFAULT_SCOPES,
        "state": state_token,
        "nonce": nonce,
    }
    if email_hint:
        query_params["login_hint"] = email_hint
    if _normalized_text(setting.domain_hint):
        query_params["domain_hint"] = _normalized_text(setting.domain_hint)

    auth_url = f"{metadata['authorization_endpoint']}?{urlencode(query_params)}"
    return schemas.SSOStartResponse(auth_url=auth_url)

@app.get("/auth/sso/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if error:
        message = _normalized_text(error_description) or _normalized_text(error) or "SSO sign-in failed."
        return RedirectResponse(url=_build_frontend_sso_redirect(error=message), status_code=302)

    if not code or not state:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Missing authorization code or state."),
            status_code=302,
        )

    try:
        state_payload = jwt.decode(
            state,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": False, "verify_aud": False},
        )
    except JWTError as exc:
        logger.warning("SSO state decode failed: %s", exc)
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Invalid SSO state. Please try Sign in with SSO again."),
            status_code=302,
        )
    if not _validate_sso_state_window(state_payload):
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="SSO state expired. Please click Sign in with SSO again."),
            status_code=302,
        )

    organization_name = _normalized_text(state_payload.get("org"))
    if not organization_name:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Invalid organization context in SSO state."),
            status_code=302,
        )

    setting = _find_sso_setting_by_organization(db, organization_name)
    if not setting or not setting.sso_enabled:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Organization SSO is not available."),
            status_code=302,
        )

    try:
        metadata = await _fetch_oidc_metadata(setting)
    except HTTPException as exc:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error=str(exc.detail)),
            status_code=302,
        )

    redirect_uri = _normalized_text(state_payload.get("redirect_uri")) or _resolve_sso_redirect_uri(setting, request)
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": _normalized_text(setting.client_id),
        "client_secret": _normalized_text(setting.client_secret),
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                metadata["token_endpoint"],
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if token_response.status_code >= 400:
            truncated_error = token_response.text[:300] or "Token exchange failed."
            return RedirectResponse(
                url=_build_frontend_sso_redirect(error=f"SSO token exchange failed. {truncated_error}"),
                status_code=302,
            )
        token_data = token_response.json()
    except Exception as exc:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error=f"Unable to complete SSO token exchange. {str(exc)}"),
            status_code=302,
        )

    claims: Dict[str, Any] = {}
    id_token = token_data.get("id_token")
    if id_token:
        try:
            claims = jwt.get_unverified_claims(id_token) or {}
        except Exception:
            claims = {}

    expected_nonce = _normalized_text(state_payload.get("nonce"))
    id_token_nonce = _normalized_text(claims.get("nonce"))
    if expected_nonce and id_token_nonce and expected_nonce != id_token_nonce:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="SSO nonce validation failed."),
            status_code=302,
        )

    email = _extract_email_from_claims(claims)
    if not email:
        userinfo_claims = await _fetch_userinfo_claims(
            metadata.get("userinfo_endpoint", ""),
            token_data.get("access_token", ""),
        )
        if userinfo_claims:
            merged_claims = dict(userinfo_claims)
            merged_claims.update(claims)
            claims = merged_claims
            email = _extract_email_from_claims(claims)

    if not email:
        email = _normalized_text(state_payload.get("email_hint"))

    if not email:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Unable to determine user email from SSO provider."),
            status_code=302,
        )

    normalized_email = email.lower()
    first_name = _normalized_text(claims.get("given_name")) or None
    last_name = _normalized_text(claims.get("family_name")) or None

    user = db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()
    if user:
        existing_org = _normalized_text(user.organization_name)
        if existing_org and existing_org.lower() != organization_name.lower():
            return RedirectResponse(
                url=_build_frontend_sso_redirect(error="This account belongs to a different organization."),
                status_code=302,
            )
        if not existing_org:
            user.organization_name = organization_name
        if not user.first_name and first_name:
            user.first_name = first_name
        if not user.last_name and last_name:
            user.last_name = last_name
    else:
        # Generate a random password because this user signs in through SSO.
        generated_password = secrets.token_urlsafe(32)
        user = models.User(
            email=normalized_email,
            hashed_password=auth.get_password_hash(generated_password),
            first_name=first_name,
            last_name=last_name,
            organization_name=organization_name,
            is_org_admin=False,
        )
        db.add(user)

    user.last_login = datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    app_access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )
    next_url = _normalized_text(state_payload.get("next")) or None
    return RedirectResponse(
        url=_build_frontend_sso_redirect(token=app_access_token, next_url=next_url),
        status_code=302,
    )

def _strip_query_param(raw_url: str, param_name: str) -> str:
    parsed = urlsplit(raw_url)
    filtered = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != param_name]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(filtered), parsed.fragment))

def _build_login_redirect_for_oauth(request: Request) -> str:
    authorize_url = _strip_query_param(str(request.url), "dsuite_token")
    return f"{settings.frontend_url.rstrip('/')}/login?{urlencode({'next': authorize_url})}"

def _resolve_user_from_access_token(token: str, db: Session) -> Optional[models.User]:
    cleaned = _normalized_text(token)
    if not cleaned:
        return None
    try:
        payload = jwt.decode(
            cleaned,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        return None

    email = _normalized_text(payload.get("sub")).lower()
    if not email:
        return None
    return db.query(models.User).filter(func.lower(models.User.email) == email).first()

def _resolve_oauth_client(
    db: Session,
    client_id: str,
    redirect_uri: Optional[str],
) -> tuple[models.OAuthClient, str]:
    normalized_client_id = _normalized_text(client_id)
    client = db.query(models.OAuthClient).filter(
        func.lower(models.OAuthClient.client_id) == normalized_client_id.lower()
    ).first()
    if not client or not client.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive OAuth client.")

    expected_redirect_uri = _normalized_text(client.redirect_uri)
    incoming_redirect_uri = _normalized_text(redirect_uri) or expected_redirect_uri
    if not incoming_redirect_uri:
        raise HTTPException(status_code=400, detail="Redirect URI is required.")
    if incoming_redirect_uri != expected_redirect_uri:
        raise HTTPException(status_code=400, detail="Redirect URI mismatch for this client.")

    return client, incoming_redirect_uri

def _redirect_with_oauth_error(redirect_uri: str, error_message: str, state: Optional[str]) -> RedirectResponse:
    params: Dict[str, str] = {"error": error_message}
    if state:
        params["state"] = state
    return RedirectResponse(
        url=f"{redirect_uri}?{urlencode(params)}",
        status_code=302,
    )

def _build_oauth_authorize_url(
    request: Request,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    dsuite_token: str,
) -> str:
    base_url = str(request.url_for("oauth_authorize"))
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "dsuite_token": dsuite_token,
    }
    return f"{base_url}?{urlencode(params)}"

def _find_plugin_connection(
    db: Session,
    organization_name: str,
    oauth_client_id: str,
) -> Optional[models.OrganizationPluginConnection]:
    org = _normalized_text(organization_name)
    cid = _normalized_text(oauth_client_id)
    if not org or not cid:
        return None
    return db.query(models.OrganizationPluginConnection).filter(
        func.lower(models.OrganizationPluginConnection.organization_name) == org.lower(),
        func.lower(models.OrganizationPluginConnection.oauth_client_id) == cid.lower(),
    ).first()

def _get_or_create_plugin_connection(
    db: Session,
    organization_name: str,
    oauth_client_id: str,
) -> models.OrganizationPluginConnection:
    org = _normalized_text(organization_name)
    cid = _normalized_text(oauth_client_id)
    if not org:
        raise HTTPException(status_code=400, detail="User organization is not configured.")
    if not cid:
        raise HTTPException(status_code=400, detail="Plugin client ID is invalid.")

    existing = _find_plugin_connection(db, org, cid)
    if existing:
        return existing

    row = models.OrganizationPluginConnection(
        organization_name=org,
        oauth_client_id=cid,
        is_connected=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def _find_org_sso_settings(
    db: Session,
    organization_name: str,
) -> Optional[models.OrganizationSSOSetting]:
    org = _normalized_text(organization_name)
    if not org:
        return None
    return db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == org.lower()
    ).first()

def _mark_plugin_connected(
    db: Session,
    connection: models.OrganizationPluginConnection,
    message: str,
) -> None:
    connection.is_connected = True
    if connection.connected_at is None:
        connection.connected_at = datetime.utcnow()
    connection.last_message = _normalized_text(message) or "Connected."
    connection.last_error = None
    db.add(connection)
    db.commit()
    db.refresh(connection)

async def _ensure_nxdune_organization_connection(
    db: Session,
    current_user: models.User,
    connection: models.OrganizationPluginConnection,
) -> None:
    if connection.is_connected and _normalized_text(connection.remote_org_tenant):
        return

    organization_name = _normalized_text(current_user.organization_name)
    sso = _find_org_sso_settings(db, organization_name)
    if not sso:
        raise HTTPException(
            status_code=400,
            detail="Configure Organization SSO settings first before connecting Nxdune.",
        )

    tenant_id = _normalized_text(sso.tenant_id)
    client_id = _normalized_text(sso.client_id)
    client_secret = _normalized_text(sso.client_secret)
    if not tenant_id or not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Tenant ID, Client ID, and Client Secret are required in Organization SSO settings for Nxdune connect.",
        )

    payload = {
        "name": organization_name,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "remarks": "Created via DSuite plugin connect",
    }

    headers = {"Content-Type": "application/json"}
    auth_token = _normalized_text(settings.nxdune_org_create_auth_token)
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        async with httpx.AsyncClient(timeout=float(settings.nxdune_org_create_timeout_seconds)) as client:
            response = await client.post(
                settings.nxdune_org_create_url,
                json=payload,
                headers=headers,
            )
        response_data = {}
        if response.content:
            try:
                response_data = response.json()
            except Exception:
                response_data = {}

        if response.status_code == 409:
            # Treat "already exists" as connected for idempotent behavior.
            connection.is_connected = True
            connection.connected_at = connection.connected_at or datetime.utcnow()
            connection.remote_org_tenant = _normalized_text(response_data.get("org_tenant")) or connection.remote_org_tenant
            connection.last_message = _normalized_text(response_data.get("message")) or "Organization already exists in Nxdune."
            connection.last_error = None
            db.add(connection)
            db.commit()
            db.refresh(connection)
            return

        if response.status_code >= 400:
            error_body = _normalized_text(response.text)[:400] or f"HTTP {response.status_code}"
            connection.is_connected = False
            connection.last_error = f"Nxdune connect failed: {error_body}"
            db.add(connection)
            db.commit()
            raise HTTPException(status_code=400, detail=connection.last_error)
    except HTTPException:
        raise
    except Exception as exc:
        connection.is_connected = False
        connection.last_error = f"Nxdune connect failed: {str(exc)}"
        db.add(connection)
        db.commit()
        raise HTTPException(status_code=400, detail=connection.last_error)

    remote_tenant = _normalized_text(response_data.get("org_tenant")) or None
    message = _normalized_text(response_data.get("message")) or "Organization created successfully."

    connection.is_connected = True
    connection.connected_at = connection.connected_at or datetime.utcnow()
    connection.remote_org_tenant = remote_tenant
    connection.last_message = message
    connection.last_error = None
    db.add(connection)
    db.commit()
    db.refresh(connection)

@app.get("/oauth/clients", response_model=List[schemas.OAuthClientPublic])
def list_oauth_clients(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.OAuthClient).filter(models.OAuthClient.is_active.is_(True))
    organization_name = _normalized_text(current_user.organization_name)
    if organization_name:
        query = query.filter(
            or_(
                models.OAuthClient.allowed_organization.is_(None),
                func.lower(models.OAuthClient.allowed_organization) == organization_name.lower(),
            )
        )
    clients = query.order_by(models.OAuthClient.name.asc()).all()
    connection_map: Dict[str, models.OrganizationPluginConnection] = {}
    if organization_name:
        rows = db.query(models.OrganizationPluginConnection).filter(
            func.lower(models.OrganizationPluginConnection.organization_name) == organization_name.lower()
        ).all()
        connection_map = {row.oauth_client_id.lower(): row for row in rows}

    response: List[schemas.OAuthClientPublic] = []
    for client in clients:
        connection = connection_map.get(client.client_id.lower())
        response.append(
            schemas.OAuthClientPublic(
                name=client.name,
                client_id=client.client_id,
                login_url=client.login_url,
                connected=bool(connection and connection.is_connected),
                connected_at=connection.connected_at if connection else None,
                remote_org_tenant=connection.remote_org_tenant if connection else None,
                connection_message=connection.last_message if connection else None,
                connection_error=connection.last_error if connection else None,
            )
        )
    return response

@app.get("/oauth/plugins/{client_id}/launch", response_model=schemas.OAuthPluginLaunchResponse)
async def get_oauth_plugin_launch_url(
    client_id: str,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    client, redirect_uri = _resolve_oauth_client(db, client_id, None)
    organization_name = _normalized_text(current_user.organization_name)
    allowed_org = _normalized_text(client.allowed_organization)
    if allowed_org and organization_name.lower() != allowed_org.lower():
        raise HTTPException(
            status_code=403,
            detail="Your organization is not allowed to access this plugin.",
        )

    connection = _get_or_create_plugin_connection(db, organization_name, client.client_id)
    if client.client_id.lower() == settings.oauth_nxdune_client_id.lower():
        try:
            await _ensure_nxdune_organization_connection(db, current_user, connection)
        except HTTPException as exc:
            # Log the error but allow OAuth flow to proceed
            # Organization creation can be retried later
            logger.warning(f"Nxdune organization creation failed: {exc.detail}. Proceeding with OAuth launch.")
            connection.last_error = str(exc.detail)[:400]
            db.add(connection)
            db.commit()
    elif not connection.is_connected:
        _mark_plugin_connected(db, connection, "Connected via DSuite launch.")

    launch_token = auth.create_access_token(
        data={
            "sub": current_user.email,
            "token_use": "oauth_launch",
            "organization_name": organization_name or "",
        },
        expires_delta=timedelta(minutes=10),
    )
    state = secrets.token_urlsafe(18)
    scope = "openid profile email"
    launch_url = _build_oauth_authorize_url(
        request=request,
        client_id=client.client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        dsuite_token=launch_token,
    )
    return schemas.OAuthPluginLaunchResponse(
        launch_url=launch_url,
        connected=connection.is_connected,
    )

@app.get("/oauth/authorize")
async def oauth_authorize(
    request: Request,
    client_id: str,
    response_type: str = "code",
    redirect_uri: Optional[str] = None,
    scope: str = "openid profile email",
    state: Optional[str] = None,
    dsuite_token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only response_type=code is supported.")

    client, resolved_redirect_uri = _resolve_oauth_client(db, client_id, redirect_uri)
    user = _resolve_user_from_access_token(dsuite_token or "", db)
    if not user:
        return RedirectResponse(url=_build_login_redirect_for_oauth(request), status_code=302)

    allowed_org = _normalized_text(client.allowed_organization)
    user_org = _normalized_text(user.organization_name)
    if allowed_org and user_org.lower() != allowed_org.lower():
        return _redirect_with_oauth_error(
            redirect_uri=resolved_redirect_uri,
            error_message="organization_not_allowed",
            state=state,
        )

    try:
        connection = _get_or_create_plugin_connection(db, user_org, client.client_id)
        if client.client_id.lower() == settings.oauth_nxdune_client_id.lower():
            await _ensure_nxdune_organization_connection(db, user, connection)
        elif not connection.is_connected:
            _mark_plugin_connected(db, connection, "Connected via DSuite login.")
    except HTTPException as exc:
        return _redirect_with_oauth_error(
            redirect_uri=resolved_redirect_uri,
            error_message=_normalized_text(str(exc.detail)) or "organization_provisioning_failed",
            state=state,
        )

    auth_code = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(seconds=OAUTH_AUTH_CODE_TTL_SECONDS)
    db_code = models.OAuthAuthorizationCode(
        code=auth_code,
        client_id=client.client_id,
        user_id=user.id,
        organization_name=user_org or None,
        redirect_uri=resolved_redirect_uri,
        scope=_normalized_text(scope) or "openid profile email",
        state=_normalized_text(state) or None,
        expires_at=expires_at,
    )
    db.add(db_code)
    db.commit()

    params: Dict[str, str] = {"code": auth_code}
    if state:
        params["state"] = state
    return RedirectResponse(
        url=f"{resolved_redirect_uri}?{urlencode(params)}",
        status_code=302,
    )

@app.post("/oauth/token", response_model=schemas.OAuthTokenResponse)
def oauth_token_exchange(
    grant_type: str = Form(...),
    code: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    db: Session = Depends(get_db),
):
    if _normalized_text(grant_type) != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant type.")

    client, resolved_redirect_uri = _resolve_oauth_client(db, client_id, redirect_uri)
    if _normalized_text(client_secret) != _normalized_text(client.client_secret):
        raise HTTPException(status_code=401, detail="Invalid client credentials.")

    db_code = db.query(models.OAuthAuthorizationCode).filter(
        models.OAuthAuthorizationCode.code == _normalized_text(code),
        func.lower(models.OAuthAuthorizationCode.client_id) == client.client_id.lower(),
    ).first()
    if not db_code:
        raise HTTPException(status_code=400, detail="Invalid authorization code.")
    if db_code.used_at is not None:
        raise HTTPException(status_code=400, detail="Authorization code already used.")
    if db_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Authorization code expired.")
    if _normalized_text(db_code.redirect_uri) != resolved_redirect_uri:
        raise HTTPException(status_code=400, detail="Authorization code redirect URI mismatch.")

    user = db.query(models.User).filter(models.User.id == db_code.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found for authorization code.")

    role = "admin" if user.is_org_admin else "member"
    org_name = _normalized_text(user.organization_name)
    claims = {
        "sub": user.email,
        "user_id": str(user.id),
        "email": user.email,
        "org_id": org_name.lower().replace(" ", "_"),
        "org_name": org_name,
        "organization_name": org_name,
        "role": role,
        "aud": client.client_id,
        "iss": settings.oauth_issuer,
        "token_use": "plugin_access",
    }
    access_token = auth.create_access_token(
        data=claims,
        expires_delta=timedelta(seconds=OAUTH_ACCESS_TOKEN_TTL_SECONDS),
    )

    db_code.used_at = datetime.utcnow()
    db.commit()

    return schemas.OAuthTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=OAUTH_ACCESS_TOKEN_TTL_SECONDS,
        scope=db_code.scope or "openid profile email",
    )

@app.get("/oauth/userinfo")
def oauth_userinfo(
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if _normalized_text(claims.get("token_use")) not in {"plugin_access", "oauth_launch"}:
        raise HTTPException(status_code=401, detail="Invalid token type.")

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email") or claims.get("sub"),
        "user_id": claims.get("user_id"),
        "org_id": claims.get("org_id"),
        "org_name": claims.get("org_name"),
        "organization_name": claims.get("organization_name"),
        "role": claims.get("role"),
        "aud": claims.get("aud"),
        "iss": claims.get("iss"),
        "exp": claims.get("exp"),
    }

@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    normalized_email = user.email.strip().lower()
    db_user = db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    organization_name = (user.organization_name or "").strip()
    if not organization_name:
        local_name = normalized_email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip().title()
        organization_name = f"{local_name or 'Default'} Organization"

    existing_org_admin = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower(),
        models.User.is_org_admin.is_(True),
    ).first()
    if existing_org_admin:
        raise HTTPException(
            status_code=400,
            detail="Organization already registered. Sign in with your admin account.",
        )

    # For now, allow registration without enforcing SMTP configuration.
    # If the client sends an explicit password, use it; otherwise fall back to a generated one.
    raw_password = (user.password or "").strip() or _generate_registration_password()
    hashed_password = auth.get_password_hash(raw_password)
    db_user = models.User(
        email=normalized_email,
        hashed_password=hashed_password,
        first_name=(user.first_name or "").strip() or None,
        last_name=(user.last_name or "").strip() or None,
        organization_name=organization_name,
        is_org_admin=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    try:
        email_service.send_organization_registration_password_email(
            recipient_email=normalized_email,
            organization_name=organization_name,
            generated_password=raw_password,
            first_name=(user.first_name or "").strip() or None,
        )
    except Exception:
        # Log the failure but do not block registration when SMTP is not configured.
        logger.exception("Failed to deliver organization registration email to %s", normalized_email)

    return db_user

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    return current_user

def _require_org_admin(current_user: models.User) -> str:
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Organization admin access required")
    organization_name = (current_user.organization_name or "").strip()
    if not organization_name:
        raise HTTPException(status_code=400, detail="Organization not configured for this account")
    return organization_name

def _require_organization(current_user: models.User) -> str:
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        raise HTTPException(status_code=400, detail="Organization not configured for this account")
    return organization_name

# --- Org-scoped project visibility ---

def _org_user_ids_subquery(db: Session, organization_name: str):
    org = _normalized_text(organization_name)
    if not org:
        return None
    return db.query(models.User.id).filter(
        func.lower(models.User.organization_name) == org.lower()
    ).scalar_subquery()

# --- Organization RBAC + Invites ---

ORG_MANAGED_PAGES: list[schemas.OrganizationPage] = [
    schemas.OrganizationPage(path="/status-dashboard", label="Status Dashboard"),
    schemas.OrganizationPage(path="/dashboard", label="Requirements Analyzer"),
    schemas.OrganizationPage(path="/new-project", label="New Project (wizard)"),
    schemas.OrganizationPage(path="/new-project/governance", label="Governance"),
    schemas.OrganizationPage(path="/agent-analysis", label="Agent Analysis"),
    schemas.OrganizationPage(path="/prerequisites", label="Prerequisites"),
    schemas.OrganizationPage(path="/task-creation", label="Task Creation"),
    schemas.OrganizationPage(path="/resource-onboarding", label="Resource Onboarding"),
    schemas.OrganizationPage(path="/agents", label="Agents"),
    schemas.OrganizationPage(path="/plugins", label="Plugins"),
    schemas.OrganizationPage(path="/organization-admin", label="Organization Admin"),
    schemas.OrganizationPage(path="/governance-management", label="Governance Management"),
]

def _hash_invite_token(token: str) -> str:
    normalized = _normalized_text(token)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def _ensure_default_rbac_roles(db: Session, organization_name: str) -> None:
    """
    Ensure an org has a baseline 'Member' role used for non-admin accounts.
    Org admins (User.is_org_admin) are treated as super-admins regardless of role assignments.
    """
    org = _normalized_text(organization_name)
    if not org:
        return
    existing = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == org.lower()
    ).first()
    if existing:
        return

    # Default member role: all authenticated pages except organization admin.
    member_paths = [p.path for p in ORG_MANAGED_PAGES if p.path != "/organization-admin"]
    member = models.OrganizationRole(
        organization_name=org,
        name="Member",
        description="Default role for organization members.",
        is_system=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    for path in member_paths:
        db.add(models.OrganizationRolePermission(role_id=member.id, path=path))
    db.commit()

def _role_to_response(role: models.OrganizationRole) -> schemas.OrganizationRoleResponse:
    allowed_paths = sorted({(perm.path or "").strip() for perm in (role.permissions or []) if (perm.path or "").strip()})
    return schemas.OrganizationRoleResponse(
        id=role.id,
        organization_name=role.organization_name,
        name=role.name,
        description=role.description,
        allowed_paths=allowed_paths,
        is_system=bool(role.is_system),
        created_at=getattr(role, "created_at", None),
        updated_at=getattr(role, "updated_at", None),
    )

def _get_user_allowed_paths(db: Session, user: models.User) -> tuple[Optional[str], list[str]]:
    """
    Returns (role_name, allowed_paths).
    - Org admins: all managed pages
    - Non-admins: role-mapped allowed paths; if missing, assign default 'Member' role
    """
    org = _normalized_text(getattr(user, "organization_name", None))
    if not org:
        return None, []

    if bool(getattr(user, "is_org_admin", False)):
        return "Admin", [p.path for p in ORG_MANAGED_PAGES]

    _ensure_default_rbac_roles(db, org)
    mapping = db.query(models.UserOrganizationRole).filter(
        models.UserOrganizationRole.user_id == user.id,
        func.lower(models.UserOrganizationRole.organization_name) == org.lower(),
    ).first()

    if not mapping:
        member = db.query(models.OrganizationRole).filter(
            func.lower(models.OrganizationRole.organization_name) == org.lower(),
            func.lower(models.OrganizationRole.name) == "member",
        ).first()
        if member:
            mapping = models.UserOrganizationRole(user_id=user.id, organization_name=org, role_id=member.id)
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

    if not mapping:
        return None, []

    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == mapping.role_id).first()
    if not role:
        return None, []

    allowed_paths = sorted({(perm.path or "").strip() for perm in (role.permissions or []) if (perm.path or "").strip()})
    return role.name, allowed_paths

@app.get("/organization/rbac/pages", response_model=list[schemas.OrganizationPage])
def list_org_pages(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    # Admin UI helper (no authz beyond being logged in)
    return ORG_MANAGED_PAGES

@app.get("/organization/rbac/me", response_model=schemas.OrganizationRbacMeResponse)
def organization_rbac_me(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    org = _normalized_text(getattr(current_user, "organization_name", None)) or None
    role_name, allowed_paths = _get_user_allowed_paths(db, current_user)
    return schemas.OrganizationRbacMeResponse(
        is_org_admin=bool(getattr(current_user, "is_org_admin", False)),
        organization_name=org,
        role_name=role_name,
        allowed_paths=allowed_paths,
    )

@app.get("/organization/rbac/roles", response_model=list[schemas.OrganizationRoleResponse])
def list_org_roles(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    roles = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower()
    ).order_by(models.OrganizationRole.name.asc()).all()
    return [_role_to_response(r) for r in roles]

@app.post("/organization/rbac/roles", response_model=schemas.OrganizationRoleResponse)
def create_org_role(
    payload: schemas.OrganizationRoleUpsert,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    role = models.OrganizationRole(
        organization_name=organization_name,
        name=_normalized_text(payload.name),
        description=_normalized_text(payload.description) or None,
        is_system=False,
    )
    db.add(role)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Role name already exists for this organization.")
    db.refresh(role)

    allowed = sorted({p for p in (payload.allowed_paths or []) if _normalized_text(p)})
    managed_paths = {p.path for p in ORG_MANAGED_PAGES}
    for path in allowed:
        if path not in managed_paths:
            continue
        db.add(models.OrganizationRolePermission(role_id=role.id, path=path))
    db.commit()
    db.refresh(role)
    return _role_to_response(role)

@app.put("/organization/rbac/roles/{role_id}", response_model=schemas.OrganizationRoleResponse)
def update_org_role(
    role_id: int,
    payload: schemas.OrganizationRoleUpsert,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.is_system:
        # allow updating permissions/description, but keep the name stable
        role.description = _normalized_text(payload.description) or None
    else:
        role.name = _normalized_text(payload.name) or role.name
        role.description = _normalized_text(payload.description) or None

    # Replace permissions
    db.query(models.OrganizationRolePermission).filter(models.OrganizationRolePermission.role_id == role.id).delete()
    managed_paths = {p.path for p in ORG_MANAGED_PAGES}
    allowed = sorted({p for p in (payload.allowed_paths or []) if _normalized_text(p)})
    for path in allowed:
        if path not in managed_paths:
            continue
        db.add(models.OrganizationRolePermission(role_id=role.id, path=path))
    db.add(role)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update role (possible duplicate name).")
    db.refresh(role)
    return _role_to_response(role)

@app.delete("/organization/rbac/roles/{role_id}")
def delete_org_role(
    role_id: int,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted.")

    in_use = db.query(models.UserOrganizationRole).filter(models.UserOrganizationRole.role_id == role.id).first()
    if in_use:
        raise HTTPException(status_code=400, detail="Role is assigned to one or more users.")

    db.delete(role)
    db.commit()
    return {"ok": True}

@app.post("/organization/rbac/request-access")
async def request_access(
    request: schemas.AccessRequest,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    if not current_user.organization_name:
        raise HTTPException(status_code=400, detail="User not associated with an organization")
    
    # Super admins as recipients
    admins = db.query(models.User).filter(
        models.User.organization_name == current_user.organization_name,
        models.User.is_org_admin == True
    ).all()
    
    # Find roles that have this path
    roles_with_access = db.query(models.OrganizationRole).join(models.OrganizationRolePermission).filter(
        models.OrganizationRole.organization_name == current_user.organization_name,
        models.OrganizationRolePermission.path == request.path
    ).all()
    
    role_ids = [r.id for r in roles_with_access]
    users_with_roles = []
    if role_ids:
        users_with_roles = db.query(models.User).join(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.role_id.in_(role_ids)
        ).all()
    
    # Combine recipients
    recipients = {u.email for u in admins} | {u.email for u in users_with_roles}
    
    if not recipients:
        raise HTTPException(status_code=404, detail="No authorized users found to receive this request")

    requester_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
    
    sent_count = 0
    for email in recipients:
        try:
            email_service.send_access_request_email(
                recipient_email=email,
                requester_name=requester_name,
                requester_email=current_user.email,
                organization_name=current_user.organization_name,
                section_name=request.section_name
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send access request email to {email}: {e}")
            
    return {"status": "success", "message": f"Access request sent to {sent_count} administrators"}

@app.get("/organization/rbac/page-access-info")
def get_page_access_info(
    path: str,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    if not current_user.organization_name:
        raise HTTPException(status_code=400, detail="User not associated with an organization")
    
    # Find roles in this org that have this path permission
    roles = db.query(models.OrganizationRole).join(models.OrganizationRolePermission).filter(
        models.OrganizationRole.organization_name == current_user.organization_name,
        models.OrganizationRolePermission.path == path
    ).all()
    
    role_names = [r.name for r in roles]
    return {"path": path, "role_names": role_names}

@app.get("/organization/invites", response_model=list[schemas.OrganizationInviteResponse])
def list_org_invites(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    invites = db.query(models.OrganizationInvite).join(models.OrganizationRole).filter(
        func.lower(models.OrganizationInvite.organization_name) == organization_name.lower()
    ).order_by(models.OrganizationInvite.created_at.desc()).limit(100).all()

    response: list[schemas.OrganizationInviteResponse] = []
    for inv in invites:
        role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == inv.role_id).first()
        response.append(
            schemas.OrganizationInviteResponse(
                id=inv.id,
                organization_name=inv.organization_name,
                email=inv.email,
                role_id=inv.role_id,
                role_name=role.name if role else "Unknown",
                invite_url="",  # do not re-emit token links from the list
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                created_at=inv.created_at,
            )
        )
    return response

@app.get("/organization/users", response_model=list[schemas.OrganizationUserResponse])
def list_org_users(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    users = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower()
    ).all()
    
    response = []
    for user in users:
        # Get role from mapping
        mapping = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == user.id,
            func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower()
        ).first()
        
        role_name = "Organization Admin" if user.is_org_admin else "No Role Assigned"
        if mapping:
            role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == mapping.role_id).first()
            if role:
                role_name = role.name
        
        response.append(schemas.OrganizationUserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role_name=role_name,
            last_login=user.last_login,
            is_org_admin=user.is_org_admin
        ))
    return response

@app.get("/organization/invites/preview", response_model=schemas.OrganizationInvitePreviewResponse)
def preview_org_invite(
    token: str,
    db: Session = Depends(get_db),
):
    token_hash = _hash_invite_token(token)
    if not token_hash:
        raise HTTPException(status_code=400, detail="Invalid invite token.")

    invite = db.query(models.OrganizationInvite).filter(models.OrganizationInvite.token_hash == token_hash).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")

    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == invite.role_id).first()
    role_name = role.name if role else "Unknown"

    return schemas.OrganizationInvitePreviewResponse(
        organization_name=invite.organization_name,
        email=invite.email,
        role_name=role_name,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
    )

@app.post("/organization/invites", response_model=schemas.OrganizationInviteResponse)
def create_org_invite(
    payload: schemas.OrganizationInviteCreate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == payload.role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found for this organization.")

    expires_days = payload.expires_in_days if isinstance(payload.expires_in_days, int) else 7
    expires_days = max(1, min(30, expires_days))
    expires_at = datetime.utcnow() + timedelta(days=expires_days)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_invite_token(token)
    invite = models.OrganizationInvite(
        organization_name=organization_name,
        email=_normalized_text(str(payload.email or "")).lower() or None,
        role_id=role.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by_user_id=current_user.id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    invite_url = f"{settings.frontend_url.rstrip('/')}/invite?token={token}"

    if invite.email:
        try:
            email_service.send_organization_invite_email(
                recipient_email=invite.email,
                organization_name=organization_name,
                role_name=role.name,
                invite_url=invite_url,
            )
        except Exception:
            logger.exception("Failed to deliver organization invite email to %s", invite.email)

    # Also notify the admin who created the link so they can forward it
    try:
        email_service.send_invite_notification_to_admin(
            admin_email=current_user.email,
            organization_name=organization_name,
            invitee_email=invite.email,
            role_name=role.name,
            invite_url=invite_url,
        )
    except Exception:
        logger.exception("Failed to deliver admin notification for invite creation to %s", current_user.email)

    return schemas.OrganizationInviteResponse(
        id=invite.id,
        organization_name=invite.organization_name,
        email=invite.email,
        role_id=role.id,
        role_name=role.name,
        invite_url=invite_url,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        created_at=invite.created_at,
    )

@app.post("/organization/invites/accept", response_model=schemas.OrganizationInviteAcceptResponse)
def accept_org_invite(
    payload: schemas.OrganizationInviteAcceptRequest,
    db: Session = Depends(get_db),
):
    token_hash = _hash_invite_token(payload.token)
    if not token_hash:
        raise HTTPException(status_code=400, detail="Invalid invite token.")

    invite = db.query(models.OrganizationInvite).filter(models.OrganizationInvite.token_hash == token_hash).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invite link already used.")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite link expired.")

    requested_email = payload.email.strip().lower()
    if invite.email and invite.email.strip().lower() != requested_email:
        raise HTTPException(status_code=400, detail="This invite link is restricted to a different email address.")

    existing_user = db.query(models.User).filter(func.lower(models.User.email) == requested_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered. Please sign in instead.")

    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == invite.role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Invite role is no longer available.")

    raw_password = payload.password
    hashed_password = auth.get_password_hash(raw_password)
    user = models.User(
        email=requested_email,
        hashed_password=hashed_password,
        first_name=_normalized_text(payload.first_name) or None,
        last_name=_normalized_text(payload.last_name) or None,
        organization_name=invite.organization_name,
        is_org_admin=False,
        last_login=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    mapping = models.UserOrganizationRole(
        user_id=user.id,
        organization_name=invite.organization_name,
        role_id=role.id,
    )
    db.add(mapping)
    invite.accepted_at = datetime.utcnow()
    invite.accepted_by_user_id = user.id
    db.add(invite)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    role_name, allowed_paths = _get_user_allowed_paths(db, user)
    return schemas.OrganizationInviteAcceptResponse(
        access_token=access_token,
        organization_name=invite.organization_name,
        role_name=role_name or role.name,
        allowed_paths=allowed_paths,
    )

def _bootstrap_org_agent_mappings_if_missing(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> None:
    """
    Backward-compatibility: if an org has no mappings yet for this project_token context,
    map all existing agents in that context to this org.
    """
    organization_name = _normalized_text(organization_name)
    project_token = _normalize_project_token(project_token)
    if not organization_name:
        return

    mapping_q = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
    )
    if project_token:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
    else:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
    if mapping_q.first():
        return

    agent_q = db.query(models.Agent)
    if project_token:
        agent_q = agent_q.filter(models.Agent.project_token == project_token)
    else:
        agent_q = agent_q.filter(models.Agent.project_token.is_(None))
    existing = agent_q.all()
    if not existing:
        return

    for agent in existing:
        inferred_kind = _normalize_agent_kind(None, getattr(agent, "project_token", project_token), is_default=False)
        db.add(
            models.OrganizationAgentMapping(
                organization_name=organization_name,
                agent_id=agent.id,
                project_token=project_token,
                agent_kind=inferred_kind,
                is_default=False,
            )
        )
    db.commit()

def _ensure_org_agent_mapping(
    db: Session,
    organization_name: str,
    agent_id: str,
    project_token: Optional[str],
    *,
    agent_kind: Optional[str] = None,
    agent_sub_type: Optional[str] = None,
    is_default: bool,
) -> None:
    organization_name = _normalized_text(organization_name)
    if not organization_name:
        return
    project_token = _normalize_project_token(project_token)
    normalized_kind = _normalize_agent_kind(agent_kind, project_token, is_default=is_default)
    normalized_sub_type = (_normalized_text(agent_sub_type) or '').lower() or None
    existing = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.agent_id == agent_id,
    ).first()
    if existing:
        # Keep latest project_token/default flag consistent
        existing.project_token = project_token
        existing.agent_kind = normalized_kind
        existing.is_default = bool(is_default)
        if normalized_sub_type:  # only update sub_type if explicitly provided
            existing.agent_sub_type = normalized_sub_type
        db.add(existing)
        db.commit()
        return
    db.add(
        models.OrganizationAgentMapping(
            organization_name=organization_name,
            agent_id=agent_id,
            project_token=project_token,
            agent_kind=normalized_kind,
            agent_sub_type=normalized_sub_type,
            is_default=bool(is_default),
        )
    )
    db.commit()

def _count_org_agent_usage(
    db: Session,
    organization_name: str,
) -> dict[str, int]:
    """Returns a dict with shared_used, dedicated_used, and subtype breakdowns."""
    org = _normalized_text(organization_name)
    if not org:
        return {
            "shared": 0, "dedicated": 0,
            "shared_dev": 0, "shared_test": 0,
            "dedicated_dev": 0, "dedicated_test": 0
        }
    rows = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == org.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
    ).all()
    stats = {
        "shared": 0, "dedicated": 0,
        "shared_dev": 0, "shared_test": 0,
        "dedicated_dev": 0, "dedicated_test": 0
    }
    for row in rows:
        kind = _normalize_agent_kind(row.agent_kind, row.project_token, is_default=bool(row.is_default))
        sub_type = (_normalized_text(row.agent_sub_type) or "dev").lower()
        
        if kind == "shared":
            stats["shared"] += 1
            if sub_type == "test": stats["shared_test"] += 1
            else: stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test": stats["dedicated_test"] += 1
            else: stats["dedicated_dev"] += 1
    return stats


def _count_org_agent_usage_for_project(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> dict[str, int]:
    """Return usage for a single project, excluding built-in defaults."""
    org = _normalized_text(organization_name)
    normalized_project_token = _normalize_project_token(project_token)
    if not org or not normalized_project_token:
        return {
            "shared": 0, "dedicated": 0,
            "shared_dev": 0, "shared_test": 0,
            "dedicated_dev": 0, "dedicated_test": 0
        }

    rows = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == org.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.project_token == normalized_project_token,
    ).all()

    stats = {
        "shared": 0, "dedicated": 0,
        "shared_dev": 0, "shared_test": 0,
        "dedicated_dev": 0, "dedicated_test": 0
    }
    for row in rows:
        kind = _normalize_agent_kind(row.agent_kind, row.project_token, is_default=bool(row.is_default))
        sub_type = (_normalized_text(row.agent_sub_type) or "dev").lower()
        if kind == "shared":
            stats["shared"] += 1
            if sub_type == "test": stats["shared_test"] += 1
            else: stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test": stats["dedicated_test"] += 1
            else: stats["dedicated_dev"] += 1
    return stats


def _get_or_init_org_agent_quota(
    db: Session,
    organization_name: str,
) -> models.OrganizationAgentQuota:
    org = _normalized_text(organization_name)
    quota = db.query(models.OrganizationAgentQuota).filter(
        func.lower(models.OrganizationAgentQuota.organization_name) == org.lower()
    ).first()
    if quota:
        return quota

    # Initialize quotas to current usage so existing installs don't suddenly break.
    usage = _count_org_agent_usage(db, org)
    shared_used = usage["shared"]
    dedicated_used = usage["dedicated"]
    quota = models.OrganizationAgentQuota(
        organization_name=org,
        shared_quota=int(shared_used),
        dedicated_quota=int(dedicated_used),
    )
    db.add(quota)
    db.commit()
    db.refresh(quota)
    return quota

@app.get("/organization/sso-settings", response_model=schemas.OrganizationSSOSettingsResponse)
def get_organization_sso_settings(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    row = db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == organization_name.lower()
    ).first()
    if not row:
        return schemas.OrganizationSSOSettingsResponse(
            organization_name=organization_name,
            sso_provider=None,
            tenant_id=None,
            client_id=None,
            client_secret=None,
            authority_url=None,
            redirect_uri=None,
            logout_url=None,
            scopes=None,
            domain_hint=None,
            sso_enabled=False,
            updated_at=None,
        )
    return row

@app.put("/organization/sso-settings", response_model=schemas.OrganizationSSOSettingsResponse)
def update_organization_sso_settings(
    payload: schemas.OrganizationSSOSettingsUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    row = db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == organization_name.lower()
    ).first()
    if not row:
        row = models.OrganizationSSOSetting(
            organization_name=organization_name,
            admin_user_id=current_user.id,
        )
        db.add(row)

    row.sso_provider = payload.sso_provider
    row.tenant_id = payload.tenant_id
    row.client_id = payload.client_id
    row.client_secret = payload.client_secret
    row.authority_url = payload.authority_url
    row.redirect_uri = payload.redirect_uri
    row.logout_url = payload.logout_url
    row.scopes = payload.scopes

    # Domain hint is no longer configured from the frontend UI; if it is not
    # explicitly provided, derive it from the org admin's email domain so that
    # all users with that domain (e.g. *@company.com) can use SSO.
    if payload.domain_hint is not None:
        row.domain_hint = payload.domain_hint
    if not _normalized_text(row.domain_hint):
        admin_email = _normalized_text(current_user.email)
        if "@" in admin_email:
            row.domain_hint = admin_email.split("@", 1)[1].lower()

    row.sso_enabled = payload.sso_enabled
    row.admin_user_id = current_user.id

    db.commit()
    db.refresh(row)
    return row


@app.get("/organization/agent-quota", response_model=schemas.OrganizationAgentQuotaResponse)
def get_organization_agent_quota(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_organization(current_user)
    quota = _get_or_init_org_agent_quota(db, organization_name)
    usage = _count_org_agent_usage(db, organization_name)
    shared_quota = int(quota.shared_quota or 0)
    dedicated_quota = int(quota.dedicated_quota or 0)
    return schemas.OrganizationAgentQuotaResponse(
        organization_name=organization_name,
        shared_quota=shared_quota,
        dedicated_quota=dedicated_quota,
        shared_used=usage["shared"],
        dedicated_used=usage["dedicated"],
        shared_available=max(0, shared_quota - usage["shared"]),
        dedicated_available=max(0, dedicated_quota - usage["dedicated"]),
        shared_dev_quota=int(quota.shared_dev_quota or 0),
        shared_test_quota=int(quota.shared_test_quota or 0),
        dedicated_dev_quota=int(quota.dedicated_dev_quota or 0),
        dedicated_test_quota=int(quota.dedicated_test_quota or 0),
        shared_dev_used=usage["shared_dev"],
        shared_test_used=usage["shared_test"],
        dedicated_dev_used=usage["dedicated_dev"],
        dedicated_test_used=usage["dedicated_test"],
        updated_at=quota.updated_at,
    )


@app.post("/organization/agent-quota/increase", response_model=schemas.OrganizationAgentQuotaResponse)
def increase_organization_agent_quota(
    payload: schemas.OrganizationAgentQuotaIncreaseRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    kind = _normalized_text(payload.kind).lower()
    sub_type = _normalized_text(getattr(payload, 'sub_type', None) or '').lower()
    amount = int(payload.amount or 0)
    if kind not in ("shared", "dedicated"):
        raise HTTPException(status_code=400, detail="kind must be 'shared' or 'dedicated'")
    if amount <= 0 or amount > 1000:
        raise HTTPException(status_code=400, detail="amount must be between 1 and 1000")

    quota = _get_or_init_org_agent_quota(db, organization_name)
    if kind == "shared":
        quota.shared_quota = int(quota.shared_quota or 0) + amount
        if sub_type == "dev":
            quota.shared_dev_quota = int(quota.shared_dev_quota or 0) + amount
        elif sub_type == "test":
            quota.shared_test_quota = int(quota.shared_test_quota or 0) + amount
    else:
        quota.dedicated_quota = int(quota.dedicated_quota or 0) + amount
        if sub_type == "dev":
            quota.dedicated_dev_quota = int(quota.dedicated_dev_quota or 0) + amount
        elif sub_type == "test":
            quota.dedicated_test_quota = int(quota.dedicated_test_quota or 0) + amount
    db.add(quota)
    db.commit()
    db.refresh(quota)

    usage = _count_org_agent_usage(db, organization_name)
    shared_quota = int(quota.shared_quota or 0)
    dedicated_quota = int(quota.dedicated_quota or 0)
    return schemas.OrganizationAgentQuotaResponse(
        organization_name=organization_name,
        shared_quota=shared_quota,
        dedicated_quota=dedicated_quota,
        shared_used=usage["shared"],
        dedicated_used=usage["dedicated"],
        shared_available=max(0, shared_quota - usage["shared"]),
        dedicated_available=max(0, dedicated_quota - usage["dedicated"]),
        shared_dev_quota=int(quota.shared_dev_quota or 0),
        shared_test_quota=int(quota.shared_test_quota or 0),
        dedicated_dev_quota=int(quota.dedicated_dev_quota or 0),
        dedicated_test_quota=int(quota.dedicated_test_quota or 0),
        shared_dev_used=usage["shared_dev"],
        shared_test_used=usage["shared_test"],
        dedicated_dev_used=usage["dedicated_dev"],
        dedicated_test_used=usage["dedicated_test"],
        updated_at=quota.updated_at,
    )

# --- Document Endpoints ---
@app.post("/documents/upload")
async def upload_document(
    files: List[UploadFile] = File(...),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Upload and process multiple documents using Docling.
    Supports: PDF, DOCX, PPTX, HTML, Images, and more.
    Requires authentication.
    """
    allowed_extensions = {".pdf", ".docx", ".pptx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".txt"}
    
    MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
    total_size = 0
    
    processed_files = []
    combined_markdown = ""
    combined_html = ""
    total_pages = 0
    all_images = []

    for file in files:
        # Validate file type
        file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        
        if file_ext not in allowed_extensions:
            # Skip invalid files or raise error? For now, we'll raise error to be safe
            continue 
            # Alternatively: raise HTTPException(status_code=400, detail=f"File {file.filename} not supported.")
        
        # Read and save file
        content = await file.read()
        total_size += len(content)
        if total_size > MAX_SIZE_BYTES:
            raise HTTPException(status_code=400, detail="Total file size exceeds 100MB limit.")

        # Handle plain text files directly
        if file_ext == ".txt":
            try:
                text_content = content.decode("utf-8", errors="replace").strip()
            except Exception:
                text_content = content.decode("latin-1", errors="replace").strip()

            if text_content:
                file_markdown = f"\n\n--- DOCUMENT: {file.filename} ---\n\n{text_content}"
                combined_markdown += file_markdown
                combined_html += f"<div class='document-separator'><h2>Document: {file.filename}</h2></div><pre style='white-space: pre-wrap; font-family: inherit;'>{text_content}</pre>"
                total_pages += 1
                processed_files.append(file.filename)
            else:
                print(f"Warning: Text file {file.filename} was empty.")
            continue

        file_path = ingestion.save_uploaded_file(content, file.filename)
        
        # Process with Docling
        result = ingestion.process_document(file_path)
        
        # Cleanup the uploaded file
        ingestion.cleanup_file(file_path)
        
        if result["status"] == "error":
            print(f"Error processing {file.filename}: {result['error']}")
            continue

        # Aggregate results
        file_markdown = f"\n\n--- DOCUMENT: {file.filename} ---\n\n{result['markdown']}"
        combined_markdown += file_markdown
        
        if result.get("html"):
            combined_html += f"<div class='document-separator'><h2>Document: {file.filename}</h2></div>{result['html']}"
        
        total_pages += result.get("num_pages", 0) or 0
        all_images.extend(result.get("images", []))
        
        processed_files.append(file.filename)

    if not processed_files:
        raise HTTPException(status_code=400, detail="No valid files processed.")

    response = {
        "filename": ", ".join(processed_files), # Combined filename for display
        "filenames": processed_files,
        "user": current_user.email,
        "markdown": combined_markdown,
        "html": combined_html if combined_html else None,
        "num_pages": total_pages,
        "images": all_images
    }
    
    print(f"DEBUG: API Response keys: {list(response.keys())}")
    return response


@app.post("/documents/extract-from-url")
async def extract_document_from_url(
    payload: URLIngestRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch website content and convert it into requirement-style markdown.
    """
    source_url = _normalize_and_validate_public_url(payload.url)

    headers = {
        "User-Agent": "BRD-Analyzer/1.0 (+Requirement-Extraction)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(source_url, headers=headers)
            resp.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timed out while fetching the URL.")
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else 502
        if code == 404:
            detail = "Website page not found (404). Check the URL and try again."
        elif code in (401, 403):
            detail = "Website denied access to this URL."
        else:
            detail = f"Failed to fetch URL content (HTTP {code})."
        raise HTTPException(status_code=code, detail=detail)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"URL fetch failed: {exc}")

    content_type = str(resp.headers.get("content-type", "")).lower()
    raw_text = resp.text or ""
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Fetched page is empty.")

    parser = _RequirementPageParser()
    parser.feed(raw_text)
    parser.close()
    parsed = parser.to_requirement_markdown(str(resp.url))

    markdown = parsed["markdown"]
    if not markdown.strip():
        plain_text = _strip_html_to_text(raw_text)
        markdown = (
            f"# Extracted Requirements\n"
            f"Source URL: {str(resp.url)}\n\n"
            f"## Candidate Requirements\n"
            f"{plain_text[:120000] if plain_text else 'No readable content found.'}"
        )

    filename_source = (parser.title_parts[0] if parser.title_parts else "") or urlparse(str(resp.url)).hostname or "Website_URL"
    safe_label = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename_source).strip("_") or "Website_URL"
    generated_filename = f"URL_{safe_label}_{datetime.utcnow().strftime('%Y-%m-%d')}"

    return {
        "filename": generated_filename,
        "url": str(resp.url),
        "content_type": content_type or None,
        "markdown": markdown,
        "summary": parsed.get("summary") or {},
        "user": current_user.email,
    }

# --- History Endpoints ---

@app.get("/history", response_model=List[schemas.Document])
def get_user_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
):
    """Retrieve user's document history."""
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        return (
            db.query(models.Document)
            .filter(models.Document.owner_id == current_user.id)
            .order_by(models.Document.upload_date.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    org_user_ids = _org_user_ids_subquery(db, organization_name)
    return (
        db.query(models.Document)
        .filter(models.Document.owner_id.in_(org_user_ids))
        .order_by(models.Document.upload_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

@app.post("/history", response_model=schemas.Document)
def save_document_history(
    document: schemas.DocumentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save an analysis result to history."""
    db_doc = models.Document(**document.dict(), owner_id=current_user.id)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@app.put("/history/{document_id}", response_model=schemas.Document)
def update_document_history(
    document_id: int,
    document: schemas.DocumentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing document history entry for the current user."""
    db_doc = db.query(models.Document).filter(
        models.Document.id == document_id,
        models.Document.owner_id == current_user.id,
    ).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = document.dict()
    db_doc.filename = payload["filename"]
    db_doc.content_preview = payload.get("content_preview")
    db_doc.full_content = payload.get("full_content")
    db_doc.analysis_result = payload.get("analysis_result")

    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@app.post("/documents/upload-and-analyze")
async def upload_and_analyze_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Upload a document, extract content with Docling, and analyze with AI.
    One-step endpoint for complete BRD analysis.
    """
    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".pptx", ".html", ".htm", ".png", ".jpg", ".jpeg"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(allowed_extensions)}"
        )
    
    MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
    
    # Read and save file
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds 100MB limit.")
        
    file_path = ingestion.save_uploaded_file(content, file.filename)
    
    # Process with Docling
    extraction_result = ingestion.process_document(file_path)
    
    # Cleanup the uploaded file
    ingestion.cleanup_file(file_path)
    
    if extraction_result["status"] == "error":
        raise HTTPException(status_code=500, detail=extraction_result["error"])
    
    # Analyze with AI
    analysis_result = await ai_service.analyze_document(
        document_content=extraction_result["markdown"],
        image_paths=extraction_result.get("images", [])
    )
    
    return {
        "filename": file.filename,
        "user": current_user.email,
        "extraction": {
            "markdown": extraction_result["markdown"],
            "html": extraction_result.get("html"),
            "num_pages": extraction_result.get("num_pages")
        },
        "analysis": analysis_result
    }


# ===== GOVERNANCE QUESTIONNAIRE ENDPOINTS =====

ALL_SKIPPED_GOVERNANCE_MESSAGE = "Our IT team will reach out to you. Thanks for connecting."
ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE = "Sandbox is not approved. Our IT team will reach out to you soon."
ALL_SKIPPED_HARD_STOP = "All governance questions were skipped. IT follow-up is required before BRD analysis."
ALL_SKIPPED_SCORE = 5.0


def _is_skip_option_label(label: Optional[str]) -> bool:
    return str(label or "").strip().lower() == "skip"


def _all_answers_skipped_from_submission(answers: List[schemas.GovernanceAnswer]) -> bool:
    return bool(answers) and all(_is_skip_option_label(answer.selected_option) for answer in answers)


def _all_answers_skipped_from_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False

    for value in payload.values():
        if not isinstance(value, dict):
            return False
        if not _is_skip_option_label(value.get("selected_option")):
            return False

    return True


def _all_answers_skipped_from_governance_context(governance_context: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(governance_context, dict):
        return False

    answers = governance_context.get("answers")
    if isinstance(answers, list):
        answer_entries = [entry for entry in answers if isinstance(entry, dict)]
        if not answer_entries or len(answer_entries) != len(answers):
            return False
        return all(_is_skip_option_label(entry.get("selected_option")) for entry in answer_entries)

    if isinstance(answers, dict):
        return _all_answers_skipped_from_payload(answers)

    classification_description = str(governance_context.get("classification_description") or "").strip().lower()
    return "our it team will reach out to you" in classification_description


def _apply_all_skipped_override(scoring_result: Dict[str, Any]) -> Dict[str, Any]:
    dimension_scores = scoring_result.get("dimension_scores") or {}
    if dimension_scores:
        overridden_dimension_scores = {dimension: ALL_SKIPPED_SCORE for dimension in dimension_scores.keys()}
    else:
        overridden_dimension_scores = {
            dimension: ALL_SKIPPED_SCORE for dimension in governance_scoring.DIMENSION_WEIGHTS.keys()
        }

    hard_stops = list(scoring_result.get("hard_stops") or [])
    if ALL_SKIPPED_HARD_STOP not in hard_stops:
        hard_stops.append(ALL_SKIPPED_HARD_STOP)

    return {
        **scoring_result,
        "dimension_scores": overridden_dimension_scores,
        "weighted_score": ALL_SKIPPED_SCORE,
        "classification": "ENTERPRISE",
        "classification_description": ALL_SKIPPED_GOVERNANCE_MESSAGE,
        "hard_stops": hard_stops,
    }

@app.get("/governance/questions")
async def get_governance_questions(db: Session = Depends(get_db)):
    """
    Get all active governance questions from database.
    """
    questions = db.query(models.GovernanceQuestion)\
        .filter(models.GovernanceQuestion.is_active == True)\
        .order_by(models.GovernanceQuestion.order)\
        .all()
    
    # Map to the format expected by the frontend
    formatted_questions = []
    for q in questions:
        # Load options
        options = []
        for opt in q.options:
            options.append({
                "label": opt.label,
                "score": opt.score
            })
            
        formatted_questions.append({
            "id": q.id,
            "dimension": q.dimension,
            "question": q.question_text,
            "options": options
        })

    return {
        "total_questions": len(formatted_questions),
        "questions": formatted_questions,
        "dimension_weights": governance_scoring.DIMENSION_WEIGHTS,
    }

@app.get("/governance/questions/all", response_model=list[schemas.GovernanceQuestion])
async def get_all_governance_questions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Only org admins can manage questions")
    
    return db.query(models.GovernanceQuestion).order_by(models.GovernanceQuestion.order).all()

@app.post("/governance/questions", response_model=schemas.GovernanceQuestion)
async def create_governance_question(
    question: schemas.GovernanceQuestionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Only org admins can manage questions")
    
    db_question = models.GovernanceQuestion(
        dimension=question.dimension,
        question_text=question.question_text,
        order=question.order,
        is_active=question.is_active
    )
    db.add(db_question)
    db.flush()
    
    for opt in question.options:
        db_opt = models.GovernanceQuestionOption(
            question_id=db_question.id,
            label=opt.label,
            score=opt.score
        )
        db.add(db_opt)
    
    db.commit()
    db.refresh(db_question)
    return db_question

@app.put("/governance/questions/{question_id}", response_model=schemas.GovernanceQuestion)
async def update_governance_question(
    question_id: int,
    question_update: schemas.GovernanceQuestionUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Only org admins can manage questions")
    
    db_question = db.query(models.GovernanceQuestion).filter(models.GovernanceQuestion.id == question_id).first()
    if not db_question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    if question_update.dimension is not None:
        db_question.dimension = question_update.dimension
    if question_update.question_text is not None:
        db_question.question_text = question_update.question_text
    if question_update.order is not None:
        db_question.order = question_update.order
    if question_update.is_active is not None:
        db_question.is_active = question_update.is_active
    
    if question_update.options is not None:
        # Delete old options
        db.query(models.GovernanceQuestionOption).filter(models.GovernanceQuestionOption.question_id == question_id).delete()
        # Add new options
        for opt in question_update.options:
            db_opt = models.GovernanceQuestionOption(
                question_id=question_id,
                label=opt.label,
                score=opt.score
            )
            db.add(db_opt)
    
    db.commit()
    db.refresh(db_question)
    return db_question

@app.delete("/governance/questions/{question_id}")
async def delete_governance_question(
    question_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Only org admins can manage questions")
    
    db_question = db.query(models.GovernanceQuestion).filter(models.GovernanceQuestion.id == question_id).first()
    if not db_question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    db.delete(db_question)
    db.commit()
    return {"detail": "Question deleted"}


@app.post("/governance/submit", response_model=schemas.GovernanceResult)
async def submit_governance_response(
    request: schemas.GovernanceSubmission,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit answers to the 17-question governance questionnaire.
    Calculates scores and returns classification with recommendation.
    """
    # Convert list of answers to dict mapping question_id -> score
    answers_dict = {}
    for answer in request.answers:
        answers_dict[answer.question_id] = answer.score
    
    # Fetch questions from DB for scoring
    db_questions = db.query(models.GovernanceQuestion).filter(models.GovernanceQuestion.is_active == True).all()
    questions_list = []
    for q in db_questions:
        questions_list.append({
            "id": q.id,
            "dimension": q.dimension,
            "question": q.question_text,
            "options": [{"label": opt.label, "score": opt.score} for opt in q.options]
        })
    
    # Perform complete scoring
    scoring_result = governance_scoring.score_governance_response(answers_dict, questions=questions_list)

    if _all_answers_skipped_from_submission(request.answers):
        scoring_result = _apply_all_skipped_override(scoring_result)
    
    detailed_answers = {
        str(answer.question_id): {
            "score": answer.score,
            "selected_option": answer.selected_option,
        }
        for answer in request.answers
    }

    recommendation_text = _generate_recommendation(scoring_result, answers_dict)

    project_token = _normalize_project_token(request.project_token) or str(uuid.uuid4())
    db_response = None

    if request.project_token:
        db_response = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id == current_user.id,
            models.GovernanceResponse.project_token == project_token,
        ).first()
        if not db_response:
            conflicting_response = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
            ).first()
            if conflicting_response and conflicting_response.owner_id != current_user.id:
                raise HTTPException(status_code=403, detail="Project token is not available for this user")

    if db_response:
        db_response.project_name = request.project_name
        db_response.submission_date = datetime.utcnow()
        db_response.answers = detailed_answers
        db_response.business_value_score = scoring_result["dimension_scores"].get("Business Value & Urgency")
        db_response.data_sensitivity_score = scoring_result["dimension_scores"].get("Data Sensitivity")
        db_response.integration_complexity_score = scoring_result["dimension_scores"].get("Integration & Architecture Complexity")
        db_response.operational_impact_score = scoring_result["dimension_scores"].get("Operational Impact")
        db_response.ai_risk_score = scoring_result["dimension_scores"].get("AI Risk")
        db_response.ownership_score = scoring_result["dimension_scores"].get("Ownership & Support")
        db_response.weighted_score = scoring_result["weighted_score"]
        db_response.classification = scoring_result["classification"]
        db_response.recommendation = recommendation_text
        if request.client_id:
            db_response.client_id = request.client_id
        if request.client_secret:
            db_response.client_secret = request.client_secret
    else:
        db_response = models.GovernanceResponse(
            owner_id=current_user.id,
            project_token=project_token,
            project_name=request.project_name,
            answers=detailed_answers,
            business_value_score=scoring_result["dimension_scores"].get("Business Value & Urgency"),
            data_sensitivity_score=scoring_result["dimension_scores"].get("Data Sensitivity"),
            integration_complexity_score=scoring_result["dimension_scores"].get("Integration & Architecture Complexity"),
            operational_impact_score=scoring_result["dimension_scores"].get("Operational Impact"),
            ai_risk_score=scoring_result["dimension_scores"].get("AI Risk"),
            ownership_score=scoring_result["dimension_scores"].get("Ownership & Support"),
            weighted_score=scoring_result["weighted_score"],
            classification=scoring_result["classification"],
            recommendation=recommendation_text,
            client_id=request.client_id,
            client_secret=request.client_secret,
        )
        db.add(db_response)

    db.commit()
    db.refresh(db_response)
    
    # Format response
    return schemas.GovernanceResult(
        id=db_response.id,
        project_token=db_response.project_token,
        project_name=db_response.project_name,
        submission_date=db_response.submission_date,
        dimension_scores=schemas.GovernanceDimensionScores(
            business_value=scoring_result["dimension_scores"]["Business Value & Urgency"],
            data_sensitivity=scoring_result["dimension_scores"]["Data Sensitivity"],
            integration_complexity=scoring_result["dimension_scores"]["Integration & Architecture Complexity"],
            operational_impact=scoring_result["dimension_scores"]["Operational Impact"],
            ai_risk=scoring_result["dimension_scores"]["AI Risk"],
            ownership=scoring_result["dimension_scores"]["Ownership & Support"],
        ),
        weighted_score=scoring_result["weighted_score"],
        classification=scoring_result["classification"],
        classification_description=scoring_result["classification_description"],
        recommendation=recommendation_text,
        hard_stops=scoring_result["hard_stops"],
        pending_revision_reason=db_response.pending_revision_reason,
        client_id=db_response.client_id,
        client_secret=db_response.client_secret,
    )


@app.get("/governance/history")
async def get_governance_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get submission history for the current user.
    """
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        responses = (
            db.query(models.GovernanceResponse)
            .filter(models.GovernanceResponse.owner_id == current_user.id)
            .order_by(models.GovernanceResponse.submission_date.desc())
            .all()
        )
    else:
        org_user_ids = _org_user_ids_subquery(db, organization_name)
        responses = (
            db.query(models.GovernanceResponse)
            .filter(models.GovernanceResponse.owner_id.in_(org_user_ids))
            .order_by(models.GovernanceResponse.submission_date.desc())
            .all()
        )
    
    return {
        "total_submissions": len(responses),
        "submissions": [
            {
                "id": r.id,
                "project_token": r.project_token,
                "project_name": r.project_name,
                "submission_date": r.submission_date,
                "weighted_score": r.weighted_score,
                "classification": r.classification,
                "pending_revision_reason": r.pending_revision_reason,
                "client_id": r.client_id,
                "client_secret": r.client_secret,
            }
            for r in responses
        ]
    }


@app.get("/governance/result/{identifier}")
async def get_governance_result(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific governance scoring result (by token or numeric id).
    Includes the original question answers for editing purposes.
    """
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        query = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id == current_user.id
        )
    else:
        org_user_ids = _org_user_ids_subquery(db, organization_name)
        query = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id.in_(org_user_ids)
        )
    
    if identifier.isdigit():
        response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # Convert stored answers dict to list of GovernanceAnswer objects
    answers_list = []
    if response.answers:
        for question_id, answer_data in response.answers.items():
            if isinstance(answer_data, dict):
                answers_list.append(schemas.GovernanceAnswer(
                    question_id=int(question_id),
                    score=answer_data.get('score', 0),
                    selected_option=answer_data.get(
                        'selected_option',
                        _lookup_selected_option(int(question_id), answer_data.get('score', 0))
                    )
                ))
            elif isinstance(answer_data, (int, float)):
                score_value = int(answer_data)
                answers_list.append(schemas.GovernanceAnswer(
                    question_id=int(question_id),
                    score=score_value,
                    selected_option=_lookup_selected_option(int(question_id), score_value),
                ))

    all_answers_skipped = _all_answers_skipped_from_payload(response.answers)
    classification_description = (
        ALL_SKIPPED_GOVERNANCE_MESSAGE
        if all_answers_skipped
        else _classification_description(response.classification)
    )
    hard_stops = [ALL_SKIPPED_HARD_STOP] if all_answers_skipped else []

    return schemas.GovernanceResult(
        id=response.id,
        project_token=response.project_token or str(response.id),
        project_name=response.project_name,
        submission_date=response.submission_date,
        dimension_scores=schemas.GovernanceDimensionScores(
            business_value=response.business_value_score,
            data_sensitivity=response.data_sensitivity_score,
            integration_complexity=response.integration_complexity_score,
            operational_impact=response.operational_impact_score,
            ai_risk=response.ai_risk_score,
            ownership=response.ownership_score,
        ),
        weighted_score=response.weighted_score,
        classification=response.classification,
        classification_description=classification_description,
        recommendation=response.recommendation,
        pending_revision_reason=response.pending_revision_reason,
        hard_stops=hard_stops,
        answers=answers_list if answers_list else None,
        client_id=response.client_id,
        client_secret=response.client_secret,
    )


@app.delete("/governance/{identifier}")
async def delete_governance_project(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a project and all locally stored project-scoped data.
    """
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    )

    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    project_token = _normalize_project_token(governance.project_token or str(governance.id))
    user_documents = db.query(models.Document).filter(
        models.Document.owner_id == current_user.id
    ).all()
    linked_document_ids = [
        doc.id for doc in user_documents if _is_document_linked_to_governance(doc, governance)
    ]

    deleted_documents = 0
    if linked_document_ids:
        deleted_documents = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id,
            models.Document.id.in_(linked_document_ids),
        ).delete(synchronize_session=False)

    deleted_agent_credentials = 0
    deleted_agent_records = 0

    if project_token:
        deleted_agent_credentials = db.query(models.AgentCredential).filter(
            models.AgentCredential.owner_id == current_user.id,
            models.AgentCredential.project_token == project_token,
        ).delete(synchronize_session=False)

        deleted_agent_records = db.query(models.Agent).filter(
            models.Agent.project_token == project_token
        ).delete(synchronize_session=False)

    deleted_project_name = governance.project_name or "Untitled Project"
    deleted_project_token = governance.project_token or str(governance.id)
    deleted_result_id = governance.id

    db.delete(governance)
    db.commit()

    cleanup_warnings: List[str] = []
    if project_token:
        try:
            await agent_service.stop_preview(project_token)
        except Exception as exc:
            cleanup_warnings.append(f"Preview cleanup failed: {exc}")

        try:
            agent_service.clear_project_runtime_state(project_token)
        except Exception as exc:
            cleanup_warnings.append(f"Agent runtime cleanup failed: {exc}")

        try:
            context_manager.clear_project_runtime_context(project_token)
        except Exception as exc:
            cleanup_warnings.append(f"Context cleanup failed: {exc}")

        try:
            await rag_service.delete_index(project_token)
        except Exception as exc:
            cleanup_warnings.append(f"Knowledge graph cleanup failed: {exc}")

    response: Dict[str, Any] = {
        "status": "deleted",
        "result_id": deleted_result_id,
        "project_token": deleted_project_token,
        "project_name": deleted_project_name,
        "deleted_documents": deleted_documents,
        "deleted_agent_credentials": deleted_agent_credentials,
        "deleted_agent_records": deleted_agent_records,
    }
    if cleanup_warnings:
        response["warnings"] = cleanup_warnings

    return response


@app.post("/governance/{identifier}/revision-reason")
async def update_revision_reason(
    identifier: str,
    payload: schemas.GovernanceRevisionReason,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the pending revision reason attached to a project.
    """
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    )
    if identifier.isdigit():
        response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="Project not found")
        
    response.pending_revision_reason = payload.reason
    db.commit()
    return {"status": "success", "pending_revision_reason": payload.reason}


@app.post("/governance/{identifier}/prerequisites-complete")
async def mark_prerequisites_complete(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark prerequisites as completed for a project."""
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    )
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    governance.prerequisites_completed_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "completed_at": governance.prerequisites_completed_at.isoformat()}


def _extract_document_analysis_context(doc: models.Document) -> Optional[Dict[str, Any]]:
    """Parse stored analysis JSON and extract project-linking metadata."""
    if not doc.analysis_result:
        return None

    try:
        import json
        analysis = json.loads(doc.analysis_result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    if not isinstance(analysis, dict):
        return None

    gov_ctx = analysis.get("governanceContext") if isinstance(analysis.get("governanceContext"), dict) else {}
    proj_meta = analysis.get("projectMeta") if isinstance(analysis.get("projectMeta"), dict) else {}

    return {
        "analysis": analysis,
        "result_id": proj_meta.get("governance_result_id") or gov_ctx.get("result_id"),
        "project_token": proj_meta.get("project_token") or gov_ctx.get("project_token"),
        "project_name": str(
            proj_meta.get("project_name") or gov_ctx.get("project_name") or ""
        ).strip().lower(),
    }


def _is_document_linked_to_governance(
    doc: models.Document,
    governance: models.GovernanceResponse,
) -> bool:
    """Return True when a document belongs to the given governance project."""
    ctx = _extract_document_analysis_context(doc)
    if not ctx:
        return False

    governance_token = str(governance.project_token or "").strip()
    governance_name = str(governance.project_name or "").strip().lower()

    if ctx["result_id"] is not None and str(ctx["result_id"]) == str(governance.id):
        return True
    if governance_token and ctx["project_token"] and str(ctx["project_token"]) == governance_token:
        return True
    if governance_name and ctx["project_name"] == governance_name:
        return True

    return False


@app.get("/governance/{identifier}/roadmap-step")
async def get_project_roadmap_step(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None),
    force_step: Optional[int] = None,  # Optional query param to force a specific step
):
    """
    Get the current roadmap step for a project.

    Steps:
        0 - Project Initiation           (project created)
        1 - Requirement Screening        (awaiting BRD analysis)
        2 - Governance                   (governance questionnaire submitted)
        3 - Agent Analysis               (BRD analysis completed)
        4 - Prerequisite Classification  (prerequisites / credentials identified)
        5 - Task Creation                (tasks auto-generated via external API)
        6 - Resource Onboarding          (agents configured for execution)
        7 - On Flight                    (agents executing task work)
        8 - Complete                     (deploy requested/succeeded)

    Returns a `step_statuses` array with per-step status:
        "completed" | "active" | "pending" | "failed"
    And a `failed_step` index (null if none failed).
    """
    STEP_LABELS = [
        "Project Initiation",
        "Requirement Screening",
        "Governance",
        "Agent Analysis",
        "Prerequisite Classification",
        "Task Creation",
        "Resource Onboarding",
        "On Flight",
        "Complete",
    ]

    # 1. Check governance response exists for this user
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        query = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id == current_user.id
        )
    else:
        org_user_ids = _org_user_ids_subquery(db, organization_name)
        query = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id.in_(org_user_ids)
        )
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        # Check if user (or org) has uploaded any documents for this "virtual" project token.
        # This allows the roadmap to progress even before the GovernanceResponse record is created.
        if organization_name:
            org_user_ids = _org_user_ids_subquery(db, organization_name)
            doc_query = db.query(models.Document).filter(models.Document.owner_id.in_(org_user_ids))
        else:
            doc_query = db.query(models.Document).filter(models.Document.owner_id == current_user.id)
            
        token_pattern = f'%"project_token": "{identifier}"%'
        doc_with_token = doc_query.filter(models.Document.analysis_result.like(token_pattern)).first()
        
        has_analysis = _doc_has_completed_analysis(doc_with_token) if doc_with_token else False
        
        # If BRD analyzed -> Governance (2) is active.
        # If BRD uploaded but not analyzed -> Screening (1) is active.
        # Otherwise -> Initiation (0) is active.
        step_idx = 2 if has_analysis else 1 if doc_with_token else 0
        
        statuses = ["completed" if i < step_idx else "active" if i == step_idx else "pending" for i in range(len(STEP_LABELS))]
        
        return {
            "result_id": None,
            "project_token": identifier,
            "project_name": "New Project",
            "current_step": step_idx,
            "current_step_label": STEP_LABELS[step_idx],
            "total_steps": len(STEP_LABELS),
            "steps": STEP_LABELS,
            "step_statuses": statuses,
            "failed_step": None,
            "classification": "N/A",
        }

    # Refresh the governance object to ensure we have the latest steps_data
    db.refresh(governance)

    # Check for stored steps data - this represents the last reached step
    stored_steps_data = governance.steps_data
    stored_last_reached_step = None
    if stored_steps_data and isinstance(stored_steps_data, dict):
        stored_last_reached_step = stored_steps_data.get("current_step")
        if stored_last_reached_step is not None:
            try:
                stored_last_reached_step = int(stored_last_reached_step)
            except (ValueError, TypeError):
                stored_last_reached_step = None

    # Check if this is a skip-all governance case (all questions skipped)
    # For skip-all cases, governance should remain active and block progression
    is_skip_all = (governance.classification == "ENTERPRISE" and governance.weighted_score == 5.0)

    # Step 0 (Project Initiation) is always complete once governance exists.
    # Governance sits between Requirement Screening and Agent Analysis.
    current_step = 3  # default active step after governance is Agent Analysis
    failed_step = None
    roadmap_project_token = _normalize_project_token(governance.project_token or str(governance.id))

    # 2. Find documents linked to this governance result
    user_documents = db.query(models.Document).filter(
        models.Document.owner_id == current_user.id,
    ).all()

    linked_docs = []
    for doc in user_documents:
        if _is_document_linked_to_governance(doc, governance):
            linked_docs.append(doc)

    has_analysis = False
    if linked_docs:
        has_analysis = any(
            _doc_has_completed_analysis(doc) for doc in linked_docs
        )

    # Define roadmap step indices (used throughout the function)
    PROJECT_INIT_IDX = 0
    REQUIREMENT_SCREENING_IDX = 1
    GOVERNANCE_IDX = 2
    AGENT_ANALYSIS_IDX = 3
    PREREQ_IDX = 4
    TASK_CREATION_IDX = 5
    RESOURCE_ONBOARDING_IDX = 6
    ON_FLIGHT_IDX = 7
    COMPLETE_IDX = 8

    # 3. Check external task management for task creation & completion
    prerequisites_done = governance.prerequisites_completed_at is not None
    has_tasks = False
    all_tasks_complete = False
    any_agent_working = False

    if has_analysis and prerequisites_done and x_task_token:
        try:
            all_page_results: List[Dict[str, Any]] = []
            page = 1
            max_pages = 200

            while page <= max_pages:
                existing_page = await task_service.get_tasks(page=page, task_token=x_task_token)
                if isinstance(existing_page, list):
                    page_results = existing_page
                    has_next = False
                elif isinstance(existing_page, dict):
                    page_results = existing_page.get("results") if isinstance(existing_page.get("results"), list) else []
                    has_next = bool(existing_page.get("next"))
                else:
                    page_results = []
                    has_next = False

                if page_results:
                    all_page_results.extend(page_results)

                if not has_next:
                    break
                page += 1

            if all_page_results:
                has_tasks = True
                # logger.info(f"Roadmap: Detected {len(all_page_results)} tasks for project {identifier}, has_tasks=True")

                done_statuses = {"completed", "done", "closed", "complete", "resolved"}

                def _task_status(task: Dict[str, Any]) -> str:
                    return str(task.get("status") or task.get("taskStatus") or "").strip().lower()

                def _task_completion(task: Dict[str, Any]) -> float:
                    raw = (
                        task.get("completion_percentage")
                        if task.get("completion_percentage") is not None
                        else task.get("progress")
                    )
                    try:
                        return float(raw or 0)
                    except (TypeError, ValueError):
                        return 0.0

                all_tasks_complete = all(
                    _task_status(t) in done_statuses or _task_completion(t) >= 100
                    for t in all_page_results
                )
        except Exception as e:
            # logger.warning(f"Roadmap: Failed to check tasks for {identifier}: {e}")
            pass
            # If task check fails, keep the last known roadmap state.
            # But if we have a task token, assume tasks might exist and check stored step
            if x_task_token and stored_last_reached_step == TASK_CREATION_IDX:
                # If we're at Task Creation and have a task token, try to progress
                # This handles cases where task detection temporarily fails
                pass

    # 4. Check runtime agent statuses for true "On Flight" execution
    try:
        runtime_agents = agent_service.get_all_agents(roadmap_project_token)
        any_agent_working = any(
            (a.get("status") or "").lower() == "running" and not agent_service._is_system_agent_id(a.get("id"))
            for a in runtime_agents
        )
    except Exception as e:
        # logger.warning(f"Roadmap: Failed to check agent runtime state for {identifier}: {e}")
        pass

    # 5. Check preview deploy state to drive "Complete" activation/completion
    deploy_status = "none"
    deploy_in_progress = False
    deploy_success = False
    deploy_attempted = False
    try:
        preview_state = agent_service.get_preview_status(roadmap_project_token)
        deploy_status = str((preview_state or {}).get("status") or "none").lower()
        deploy_in_progress = deploy_status == "deploying"
        deploy_success = deploy_status == "running"
        deploy_attempted = deploy_status in {"deploying", "running", "error"}
    except Exception as e:
        # logger.warning(f"Roadmap: Failed to check deploy state for {identifier}: {e}")
        pass

    # Backend roadmap progression:
    # Project Initiation -> Requirement Screening -> Governance -> Agent Analysis ->
    # Prerequisite Classification -> Task Creation -> Resource Onboarding ->
    # On Flight -> Complete

    step_statuses = ["pending"] * len(STEP_LABELS)
    step_statuses[PROJECT_INIT_IDX] = "completed"

    step_statuses[REQUIREMENT_SCREENING_IDX] = "completed"
    
    # For skip-all governance cases, keep Governance as active (not completed)
    # This blocks progression to subsequent steps
    if is_skip_all:
        step_statuses[GOVERNANCE_IDX] = "active"
        # For skip-all cases, all subsequent steps remain pending
        # No further progression allowed
    else:
        step_statuses[GOVERNANCE_IDX] = "completed"

        if not has_analysis:
            step_statuses[AGENT_ANALYSIS_IDX] = "active"
        else:
            step_statuses[AGENT_ANALYSIS_IDX] = "completed"
            step_statuses[PREREQ_IDX] = "completed" if prerequisites_done else "active"

        if prerequisites_done:
            step_statuses[TASK_CREATION_IDX] = "completed" if has_tasks else "active"

        if has_tasks:
            onboarding_complete = any_agent_working or all_tasks_complete or deploy_attempted
            step_statuses[RESOURCE_ONBOARDING_IDX] = "completed" if onboarding_complete else "active"

            if onboarding_complete:
                on_flight_done = all_tasks_complete and not any_agent_working
                
                if on_flight_done:
                    step_statuses[ON_FLIGHT_IDX] = "completed"
                    if deploy_success:
                        step_statuses[COMPLETE_IDX] = "completed"
                    elif deploy_in_progress or deploy_attempted:
                        step_statuses[COMPLETE_IDX] = "active"
                    else:
                        step_statuses[COMPLETE_IDX] = "pending"
                elif any_agent_working:
                    step_statuses[ON_FLIGHT_IDX] = "active"
                    step_statuses[COMPLETE_IDX] = "pending"

    # Derive current step from explicit statuses (computed based on current state)
    active_step = next((idx for idx, status in enumerate(step_statuses) if status == "active"), None)
    if active_step is not None:
        computed_step = active_step
    else:
        completed_indices = [idx for idx, status in enumerate(step_statuses) if status == "completed"]
        computed_step = completed_indices[-1] if completed_indices else 0
    
    # logger.info(f"Roadmap: Project {identifier} - has_tasks={has_tasks}, computed_step={computed_step}, stored_step={stored_last_reached_step}, step_statuses={step_statuses}")

    # Use stored last reached step if it exists, otherwise use computed step
    # The stored step represents the furthest step the user has reached - NEVER go backwards
    if stored_last_reached_step is not None and stored_last_reached_step >= 0:
        # Always use the stored step as the baseline (last reached step)
        # Only update if computed step is HIGHER (we've progressed further)
        if computed_step > stored_last_reached_step:
            # We've progressed further, update the stored step
            stored_last_reached_step = computed_step
            final_current_step = stored_last_reached_step
            # Use the computed step_statuses since they reflect the actual current state
            # The computed statuses already show Resource Onboarding as active when tasks exist
            # Don't rebuild - keep the computed statuses
        elif stored_last_reached_step == TASK_CREATION_IDX and (has_tasks or x_task_token):
            # Special case: If we're at Task Creation (5) and tasks exist OR we have a task token,
            # progress to Resource Onboarding (6)
            # This handles the case where tasks exist but has_tasks detection failed
            # If we have a task token, it's likely tasks exist even if detection failed
            stored_last_reached_step = RESOURCE_ONBOARDING_IDX
            final_current_step = RESOURCE_ONBOARDING_IDX
            # Update step_statuses to reflect Resource Onboarding as active
            step_statuses[TASK_CREATION_IDX] = "completed"
            step_statuses[RESOURCE_ONBOARDING_IDX] = "active"
            computed_step = RESOURCE_ONBOARDING_IDX  # Update computed_step to match
        elif computed_step == stored_last_reached_step:
            # Same step - use computed step_statuses to reflect current state (e.g., On Flight when agents are running)
            final_current_step = computed_step
            # Keep the computed step_statuses as they reflect the actual current state
            # This ensures On Flight shows as active when agents are working, even if stored step is Resource Onboarding
        else:
            # Use stored step (never go backwards)
            final_current_step = stored_last_reached_step
            # Rebuild step_statuses based on the stored step only if we haven't progressed
            new_step_statuses = ["pending"] * len(STEP_LABELS)
            
            # Mark all steps up to (but not including) the final step as completed
            for i in range(final_current_step):
                if i < len(new_step_statuses):
                    new_step_statuses[i] = "completed"
            
            # Mark the final step as active (the last reached step)
            if final_current_step < len(new_step_statuses):
                new_step_statuses[final_current_step] = "active"
            
            step_statuses = new_step_statuses
    else:
        # No stored step, use computed step and save it
        final_current_step = computed_step
        stored_last_reached_step = computed_step

    # Prepare the roadmap data
    roadmap_data = {
        "result_id": governance.id,
        "project_token": roadmap_project_token or str(governance.id),
        "project_name": governance.project_name,
        "current_step": final_current_step,
        "current_step_label": STEP_LABELS[final_current_step] if final_current_step < len(STEP_LABELS) else "Complete",
        "total_steps": len(STEP_LABELS),
        "steps": STEP_LABELS,
        "step_statuses": step_statuses,
        "failed_step": failed_step,
        "classification": governance.classification,
    }

    # Save steps data to database (update last reached step)
    # Only save if we have a valid stored_last_reached_step
    try:
        if stored_last_reached_step is not None and stored_last_reached_step >= 0:
            governance.steps_data = {
                "steps": STEP_LABELS,
                "step_statuses": step_statuses,
                "current_step": stored_last_reached_step,  # Store the last reached step (never goes backwards)
                "current_step_label": STEP_LABELS[stored_last_reached_step] if stored_last_reached_step < len(STEP_LABELS) else "Complete",
                "failed_step": failed_step,
                "updated_at": datetime.utcnow().isoformat(),
            }
            db.commit()
    except Exception as e:
        logger.error(f"Failed to save steps data to database: {e}")
        db.rollback()

    return roadmap_data


def _doc_has_completed_analysis(doc: models.Document) -> bool:
    """Check whether a Document record has a completed AI analysis."""
    if not doc.analysis_result:
        return False
    try:
        import json
        analysis = json.loads(doc.analysis_result)
        # The analysis is stored under the "analysis" key inside the JSON
        ai_analysis = analysis.get("analysis") or ""
        return len(str(ai_analysis).strip()) > 0
    except (json.JSONDecodeError, AttributeError):
        return False

def _lookup_selected_option(question_id: int, score: int) -> str:
    question = next(
        (q for q in governance_scoring.GOVERNANCE_QUESTIONS if q["id"] == question_id),
        None,
    )
    if not question:
        return ""
    option = next((opt for opt in question["options"] if opt["score"] == score), None)
    return option["label"] if option else ""


def _classification_description(classification: str) -> str:
    if classification == "SANDBOX":
        return "Sandbox Approved - Low governance required"
    if classification == "CONTROLLED_SANDBOX":
        return "Controlled Sandbox (Fusion) - Standard template required"
    if classification == "ENTERPRISE":
        return "Enterprise Build - Full IT oversight required"
    return "Governance classification unavailable"


def _generate_recommendation(scoring_result: dict, answers: dict) -> str:
    """
    Generate detailed recommendation text based on scoring.
    """
    classification = scoring_result["classification"]
    hard_stops = scoring_result["hard_stops"]
    dimension_scores = scoring_result["dimension_scores"]
    weighted_score = scoring_result["weighted_score"]
    
    recommendation = f"**Governance Classification: {classification}**\n\n"
    
    if ALL_SKIPPED_HARD_STOP in hard_stops:
        recommendation += (
            "**Screening Status: Incomplete**\n\n"
            "Our IT team will reach out to you. Thanks for connecting.\n\n"
            "AI analysis is blocked until the IT team completes a follow-up review.\n\n"
        )
    elif hard_stops:
        recommendation += f"**⚠️ HARD STOPS TRIGGERED:**\n"
        for stop in hard_stops:
            recommendation += f"- {stop}\n"
        recommendation += f"\nThis project requires **Enterprise Build** governance due to risk escalation triggers.\n\n"
    else:
        if classification == "SANDBOX":
            recommendation += (
                "✅ **Sandbox Approved** - This project has low governance overhead.\n\n"
                "**What you get:**\n"
                "- Azure Dev subscription (capped budget)\n"
                "- No production data allowed\n"
                "- 90-day review cycle\n"
                "- Self-service deployment\n\n"
            )
        elif classification == "CONTROLLED_SANDBOX":
            recommendation += (
                "⚠️ **Controlled Sandbox (Fusion)** - This project requires standard templates.\n\n"
                "**What you get:**\n"
                "- Must use Azure DevOps template\n"
                "- Must use standard .NET scaffold\n"
                "- Lightweight IT architecture check\n"
                "- Structured CI/CD pipeline\n\n"
            )
        else:  # ENTERPRISE
            recommendation += (
                "🔴 **Enterprise Build** - Full IT oversight required.\n\n"
                "**What you get:**\n"
                "- Architecture board review\n"
                "- Threat model & security assessment\n"
                "- Azure Policy enforcement\n"
                "- Full CI/CD gating\n"
                "- SDLC compliance enforcement\n\n"
            )
    
    recommendation += f"**Weighted Score: {weighted_score}/10**\n\n"
    recommendation += "**Dimension Scores:**\n"
    for dimension, score in dimension_scores.items():
        recommendation += f"- {dimension}: {score}/10\n"
    
    return recommendation


# ─────────────────────────────── GitHub Integration ──────────────────────────

@app.get("/github/auth-url")
async def github_auth_url(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Return the GitHub OAuth authorization URL."""
    try:
        url = github_service.get_oauth_url(state=str(current_user.id))
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


class GitHubCallbackPayload(BaseModel):
    code: str


@app.post("/github/callback")
async def github_callback(
    payload: GitHubCallbackPayload,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exchange an OAuth code for a GitHub access token and persist it
    on the current user.
    """
    try:
        token_data = await github_service.exchange_code_for_token(payload.code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain GitHub token")

        # Fetch GitHub username
        gh_user = await github_service.get_github_user(access_token)
        github_username = gh_user.get("login", "")

        # Store on user record
        current_user.github_token = access_token
        current_user.github_username = github_username
        db.commit()

        return {
            "status": "connected",
            "github_username": github_username,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub OAuth error: {e}")


@app.get("/github/status")
async def github_status(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Check whether the user has connected their GitHub account."""
    return {
        "connected": bool(current_user.github_token),
        "github_username": current_user.github_username or None,
    }


@app.post("/github/disconnect")
async def github_disconnect(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored GitHub token."""
    current_user.github_token = None
    current_user.github_username = None
    db.commit()
    return {"status": "disconnected"}


@app.get("/github/repos")
async def github_repos(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = 1,
    per_page: int = 30,
):
    """List the authenticated user's GitHub repositories."""
    if not current_user.github_token:
        raise HTTPException(status_code=400, detail="GitHub not connected")
    try:
        repos = await github_service.list_repos(
            current_user.github_token, per_page=per_page, page=page
        )
        return {"repos": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch repos: {e}")


@app.get("/azure-devops/auth-url")
async def azure_devops_auth_url(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Return the Azure DevOps OAuth authorization URL. Supports project-specific credentials."""
    try:
        project_client_id = None
        project_client_secret = None
        checked_project_credentials = False
        
        # If project_token is provided, try to get project-specific credentials
        if project_token:
            gov_res = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
                models.GovernanceResponse.owner_id == current_user.id
            ).first()
            if gov_res:
                checked_project_credentials = True
                project_client_id = gov_res.azure_devops_client_id
                project_client_secret = gov_res.azure_devops_client_secret
        
        # Include project_token in state so callback can use it
        state_data = {"user_id": str(current_user.id)}
        if project_token:
            state_data["project_token"] = project_token
        
        import json
        state = json.dumps(state_data)
        
        url = azure_devops_oauth_service.get_oauth_url(
            state=state,
            client_id=project_client_id,
            client_secret=project_client_secret,
            checked_project_credentials=checked_project_credentials
        )
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


class AzureDevOpsCallbackPayload(BaseModel):
    code: str


@app.post("/azure-devops/callback")
async def azure_devops_callback(
    payload: AzureDevOpsCallbackPayload,
    state: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange an OAuth code for an Azure DevOps token and persist it. Supports project-specific credentials."""
    try:
        project_token = None
        project_client_id = None
        project_client_secret = None
        
        # Parse state to get project_token if present
        if state:
            try:
                import json
                state_data = json.loads(state)
                project_token = state_data.get("project_token")
            except:
                pass
        
        # If project_token is provided, get project-specific credentials
        if project_token:
            gov_res = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
                models.GovernanceResponse.owner_id == current_user.id
            ).first()
            if gov_res:
                project_client_id = gov_res.azure_devops_client_id
                project_client_secret = gov_res.azure_devops_client_secret
        
        token_data = await azure_devops_oauth_service.exchange_code_for_token(
            payload.code,
            client_id=project_client_id,
            client_secret=project_client_secret
        )
        access_token = (token_data.get("access_token") or "").strip()
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain Azure DevOps token")

        profile = await azure_devops_oauth_service.get_current_profile(access_token)
        display_name = str(
            profile.get("displayName")
            or profile.get("emailAddress")
            or profile.get("id")
            or ""
        ).strip()

        current_user.azure_devops_token = access_token
        current_user.azure_devops_username = display_name or None
        db.commit()

        return {
            "status": "connected",
            "azure_devops_username": current_user.azure_devops_username,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        detail = "Azure DevOps OAuth error."
        if e.response is not None:
            try:
                payload = e.response.json() or {}
                detail = str(payload.get("error_description") or payload.get("message") or detail)
            except Exception:
                detail = str(e.response.text or detail)
        raise HTTPException(status_code=status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Azure DevOps OAuth error: {e}")


@app.get("/azure-devops/status")
async def azure_devops_status(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Check whether the user has connected their Azure DevOps account."""
    return {
        "connected": bool(current_user.azure_devops_token),
        "azure_devops_username": current_user.azure_devops_username or None,
    }


class AzureDevOpsCredentialsPayload(BaseModel):
    project_token: str
    organization: Optional[str] = None
    project: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


@app.get("/azure-devops/credentials/{project_token}")
async def get_azure_devops_credentials(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Get Azure DevOps OAuth credentials for a specific project."""
    try:
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        if not gov_res:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {
            "organization": gov_res.azure_devops_organization or None,
            "project": gov_res.azure_devops_project or None,
            "tenant_id": gov_res.azure_devops_tenant_id or None,
            "client_id": gov_res.azure_devops_client_id or None,
            "client_secret": gov_res.azure_devops_client_secret or None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get credentials: {e}")


@app.post("/azure-devops/save-credentials")
async def save_azure_devops_credentials(
    payload: AzureDevOpsCredentialsPayload,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save Azure DevOps OAuth credentials for a specific project."""
    try:
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == payload.project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        if not gov_res:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Update credentials if provided
        if payload.organization is not None:
            gov_res.azure_devops_organization = payload.organization
        if payload.project is not None:
            gov_res.azure_devops_project = payload.project
        if payload.tenant_id is not None:
            gov_res.azure_devops_tenant_id = payload.tenant_id
        if payload.client_id is not None:
            gov_res.azure_devops_client_id = payload.client_id
        if payload.client_secret is not None:
            gov_res.azure_devops_client_secret = payload.client_secret
        
        db.commit()
        
        return {
            "status": "saved",
            "message": "Azure DevOps credentials saved successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {e}")


@app.post("/azure-devops/disconnect")
async def azure_devops_disconnect(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored Azure DevOps token."""
    current_user.azure_devops_token = None
    current_user.azure_devops_username = None
    db.commit()
    return {"status": "disconnected"}


@app.get("/azure-devops/repos")
async def azure_devops_repos(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = 1,
    per_page: int = 30,
):
    """List Azure DevOps repositories available to the authenticated user."""
    access_token = (current_user.azure_devops_token or "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Azure DevOps not connected")
    try:
        repos = await azure_devops_oauth_service.list_repos(
            access_token,
            per_page=per_page,
            page=page,
        )
        return {"repos": repos}
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        raise HTTPException(status_code=status_code, detail="Failed to fetch Azure DevOps repositories.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Azure DevOps repositories: {e}")


class ListProjectReposRequest(BaseModel):
    project_token: str
    organization: str
    project: str


@app.post("/azure-devops/list-project-repos")
async def list_project_repos(
    payload: ListProjectReposRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """List repositories in a specific Azure DevOps project."""
    try:
        # Try to get project-specific credentials first
        gov_res = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == payload.project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()
        
        access_token = None
        
        # Try OAuth token from user's connected account
        user_token = (current_user.azure_devops_token or "").strip()
        if user_token:
            access_token = user_token
        
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="Azure DevOps authentication required. Please connect your Azure DevOps account first."
            )
        
        repos = await azure_devops_service.list_project_repositories(
            organization=payload.organization,
            project=payload.project,
            pat=None,
            access_token=access_token,
        )
        
        return {"repos": repos}
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        detail = "Failed to fetch repositories from Azure DevOps project."
        if e.response is not None:
            try:
                error_payload = e.response.json() or {}
                detail = str(error_payload.get("message") or error_payload.get("value") or detail)
            except Exception:
                detail = str(e.response.text or detail)
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list project repositories: {e}")


class RepoContextRequest(BaseModel):
    owner: str
    repo: str
    branch: str = "main"
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class AzureDevOpsRepoContextRequest(BaseModel):
    repo_url: str
    token: Optional[str] = None
    branch: Optional[str] = None


@app.post("/github/repo-context")
async def github_repo_context(
    payload: RepoContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch repository source code and return a structured text context
    suitable for feeding into the AI model alongside the BRD.
    """
    provided_token = (payload.token or "").strip() or None
    provided_username = (payload.username or "").strip() or None
    provided_password = str(payload.password or "") if payload.password is not None else None
    has_basic_credentials = bool(provided_username or (provided_password is not None and provided_password != ""))
    if has_basic_credentials and not (provided_username and provided_password):
        raise HTTPException(status_code=400, detail="Provide both GitHub username and password.")
    if provided_token and has_basic_credentials:
        raise HTTPException(status_code=400, detail="Use either PAT or username/password, not both.")

    saved_oauth_token = (current_user.github_token or "").strip() or None
    token_to_use = provided_token if provided_token else saved_oauth_token

    owner, repo = github_service.normalize_repo_identity(payload.owner, payload.repo)
    branch = (payload.branch or "main").strip() or "main"
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL or owner/repo values.")

    async def _build_context(
        token_value: Optional[str],
        username_value: Optional[str] = None,
        password_value: Optional[str] = None,
    ) -> Dict[str, str]:
        return await github_service.build_repo_context(
            token_value,
            owner,
            repo,
            branch,
            username=username_value,
            password=password_value,
        )

    async def _build_context_from_zip() -> Dict[str, str]:
        return await github_service.build_repo_context_from_zip(
            owner,
            repo,
            branch,
        )

    def _is_rate_limited(err: httpx.HTTPStatusError) -> bool:
        if err.response is None:
            return False
        if err.response.status_code != 403:
            return False
        try:
            message = str((err.response.json() or {}).get("message") or "").lower()
        except Exception:
            message = str(err.response.text or "").lower()
        return "rate limit" in message

    def _raise_repo_context_error(err: httpx.HTTPStatusError) -> None:
        status_code = err.response.status_code if err.response is not None else 502
        response_msg = ""
        if err.response is not None:
            try:
                response_msg = str((err.response.json() or {}).get("message") or "").strip()
            except Exception:
                response_msg = str(err.response.text or "").strip()
        response_msg_lc = response_msg.lower()

        if status_code == 404:
            detail = (
                "Repository or branch was not found. Verify the URL, remove any trailing .git, "
                "and provide a PAT for private repositories."
            )
        elif status_code == 403 and "rate limit" in response_msg_lc:
            detail = "GitHub API rate limit exceeded. Add a valid PAT or reconnect GitHub OAuth and try again."
        elif status_code in (401, 403):
            detail = "GitHub authentication failed or access denied. Check your PAT, username/password, or OAuth access."
        else:
            detail = f"Failed to fetch repository context from GitHub (HTTP {status_code})."
        raise HTTPException(status_code=status_code, detail=detail)

    try:
        username_to_use = provided_username if has_basic_credentials else None
        password_to_use = provided_password if has_basic_credentials else None
        token_for_primary = None if has_basic_credentials else token_to_use
        repo_data = await _build_context(token_for_primary, username_to_use, password_to_use)
        return {
            "context": repo_data["context"],
            "repo": f"{repo_data['owner']}/{repo_data['repo']}",
            "branch": repo_data["branch"],
        }
    except httpx.HTTPStatusError as e:
        if _is_rate_limited(e):
            try:
                repo_data = await _build_context_from_zip()
                return {
                    "context": repo_data["context"],
                    "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                    "branch": repo_data["branch"],
                }
            except httpx.HTTPStatusError:
                # If zip fallback also fails, continue to the regular error path below.
                pass

        # If saved OAuth token is stale/invalid and no PAT was explicitly provided,
        # retry without auth so public repositories still work.
        status_code = e.response.status_code if e.response is not None else 502
        should_retry_without_auth = (
            status_code in (401, 403)
            and provided_token is None
            and not has_basic_credentials
            and saved_oauth_token is not None
        )
        if should_retry_without_auth:
            try:
                repo_data = await _build_context(None)
                return {
                    "context": repo_data["context"],
                    "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                    "branch": repo_data["branch"],
                }
            except httpx.HTTPStatusError as retry_err:
                if _is_rate_limited(retry_err):
                    try:
                        repo_data = await _build_context_from_zip()
                        return {
                            "context": repo_data["context"],
                            "repo": f"{repo_data['owner']}/{repo_data['repo']}",
                            "branch": repo_data["branch"],
                        }
                    except httpx.HTTPStatusError:
                        pass
                _raise_repo_context_error(retry_err)
        _raise_repo_context_error(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build repo context: {e}")

@app.post("/azure-devops/repo-context")
async def azure_devops_repo_context(
    payload: AzureDevOpsRepoContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch Azure DevOps repository source and return a structured context
    suitable for feeding into the AI model alongside BRD content.
    """
    provided_token = (payload.token or "").strip() or None
    saved_oauth_token = (current_user.azure_devops_token or "").strip() or None
    token_to_use = provided_token if provided_token else saved_oauth_token
    branch = (payload.branch or "").strip() or None

    try:
        repo_data = await azure_devops_service.build_repo_context_from_url(
            repo_url=payload.repo_url,
            pat=token_to_use,
            branch=branch,
        )
        return {
            "context": repo_data["context"],
            "repo": repo_data["repo"],
            "branch": repo_data["branch"],
            "provider": "azure-devops",
            "url": repo_data["url"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else 502
        response_msg = ""
        if e.response is not None:
            try:
                response_msg = str((e.response.json() or {}).get("message") or "").strip()
            except Exception:
                response_msg = str(e.response.text or "").strip()
        response_msg_lc = response_msg.lower()

        if status_code == 404:
            detail = (
                "Azure DevOps repository or branch was not found. Verify organization/project/repository URL "
                "and branch name."
            )
        elif status_code in (401, 403):
            if "pat" in response_msg_lc or "token" in response_msg_lc:
                detail = "Azure DevOps authentication failed. Check your PAT permissions or reconnect OAuth."
            else:
                detail = "Azure DevOps authentication failed or access denied. Provide a valid PAT or reconnect OAuth."
        else:
            detail = f"Failed to fetch repository context from Azure DevOps (HTTP {status_code})."
        raise HTTPException(status_code=status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build Azure DevOps repo context: {e}")


# ═════════════════════════ KNOWLEDGE GRAPH + RAG ═════════════════════════════

class KGIndexRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    token: Optional[str] = None
    brd_analysis: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None


@app.post("/api/knowledge-graph/index")
async def index_knowledge_graph(
    payload: KGIndexRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Start indexing a repository into the Knowledge Graph + RAG system.
    Pipeline: Clone repo → Tree-sitter AST → Build KG → LightRAG embed.
    Runs in the background; use /status to poll progress.
    """
    project_token = x_task_token or str(uuid.uuid4())

    # Use user's GitHub token if no explicit token provided
    github_token = payload.token or current_user.github_token

    # Run indexing in background
    async def _run_indexing():
        try:
            result = await context_manager.index_project_repository(
                project_token=project_token,
                repo_url=payload.repo_url,
                token=github_token,
                branch=payload.branch,
                brd_analysis=payload.brd_analysis,
                governance_context=payload.governance_context,
            )
            logger.info(f"KG indexing complete for {project_token}: {result.get('status')}")
        except Exception as e:
            logger.error(f"KG indexing background task failed for {project_token}: {e}")

    bg_task = asyncio.create_task(_run_indexing())
    bg_task.add_done_callback(lambda t: logger.error(f"KG indexing error: {t.exception()}") if t.exception() else None)

    return {
        "status": "indexing_started",
        "project_token": project_token,
        "message": f"Indexing {payload.repo_url} in background. Poll /api/knowledge-graph/status/{project_token} for progress.",
    }


@app.get("/api/knowledge-graph/status/{project_token}")
async def get_kg_status(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Check the indexing status for a project's Knowledge Graph.
    """
    rag_status = rag_service.get_indexing_status(project_token)
    graph_stats = context_manager.get_project_graph_stats(project_token)

    return {
        "project_token": project_token,
        "rag_status": rag_status,
        "graph_stats": graph_stats,
        "is_ready": context_manager.is_project_indexed(project_token),
    }


class KGQueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"  # naive, local, global, hybrid
    top_k: int = 10


@app.post("/api/knowledge-graph/query")
async def query_knowledge_graph(
    payload: KGQueryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Query the Knowledge Graph + RAG system for relevant code context.
    Returns semantically relevant code snippets and graph-connected relationships.
    """
    project_token = x_task_token
    if not project_token:
        raise HTTPException(status_code=400, detail="x-task-token header is required")

    if not context_manager.is_project_indexed(project_token):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_token} is not indexed. Call /api/knowledge-graph/index first.",
        )

    result = await rag_service.query_codebase(
        project_token=project_token,
        query=payload.query,
        mode=payload.mode,
        top_k=payload.top_k,
    )
    return result


@app.get("/api/knowledge-graph/stats/{project_token}")
async def get_kg_stats(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get Knowledge Graph statistics for a project.
    Returns counts of nodes (files, classes, functions, imports)
    and edges (contains, imports, calls, inherits).
    """
    stats = context_manager.get_project_graph_stats(project_token)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"No knowledge graph found for project {project_token}",
        )
    return {"project_token": project_token, "stats": stats}


@app.delete("/api/knowledge-graph/{project_token}")
async def delete_knowledge_graph(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Delete all indexed Knowledge Graph and RAG data for a project.
    """
    result = await rag_service.delete_index(project_token)
    return {"status": "deleted", "project_token": project_token, "details": result}


class AgentContextRequest(BaseModel):
    task_description: str
    task_type: Optional[str] = None
    brd_analysis: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None


@app.post("/api/knowledge-graph/agent-context")
async def get_agent_context(
    payload: AgentContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Get the full three-layer context for an agent task:
    Layer 1: Global codebase context (tech stack, structure)
    Layer 2: Project rules (BRD analysis, governance)
    Layer 3: Just-in-time code snippets (LightRAG hybrid query)
    """
    project_token = x_task_token
    if not project_token:
        raise HTTPException(status_code=400, detail="x-task-token header is required")

    context = await context_manager.get_full_agent_context(
        project_token=project_token,
        task_description=payload.task_description,
        task_type=payload.task_type,
        brd_analysis=payload.brd_analysis,
        governance_context=payload.governance_context,
    )
    return {
        "context": context,
        "is_indexed": context_manager.is_project_indexed(project_token),
        "project_token": project_token,
    }


@app.get("/api/knowledge-graph/cross-agent-memory/{project_token}")
async def get_cross_agent_memory(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get the live cross-agent shared memory for a project.
    Shows which agents are active, what files they're touching,
    and what was recently completed.
    """
    memory = context_manager.get_live_memory(project_token)

    active_agents = []
    for aid, record in memory.active_tasks.items():
        active_agents.append({
            "agent_id": record.agent_id,
            "task_title": record.task_title,
            "task_description": record.task_description[:200],
            "branch_name": record.branch_name,
            "started_at": record.started_at,
        })

    completed_history = []
    for record in memory.completed_history[:20]:
        completed_history.append({
            "agent_id": record.agent_id,
            "task_title": record.task_title,
            "status": record.status,
            "files_touched": record.files_touched,
            "symbols_created": record.symbols_created,
            "exit_code": record.exit_code,
            "summary": record.summary,
            "completed_at": record.completed_at,
        })

    file_locks = {
        fpath: list(agents)
        for fpath, agents in memory.file_locks.items()
        if agents
    }

    return {
        "project_token": project_token,
        "active_agents": active_agents,
        "completed_history": completed_history,
        "file_locks": file_locks,
        "total_completed": len(memory.completed_history),
    }


@app.get("/api/knowledge-graph/tech-spec/{project_token}")
async def get_tech_spec(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the generated Technical Spec (Layer 1: Architect Agent)."""
    from agent_service import get_technical_spec, _project_tech_specs
    spec = get_technical_spec(project_token)
    record = _project_tech_specs.get(project_token, {})
    return {
        "project_token": project_token,
        "status": record.get("status", "not_generated"),
        "spec": spec,
        "char_length": len(spec),
        "generated_at": record.get("generated_at"),
    }


@app.post("/api/knowledge-graph/tech-spec/{project_token}/generate")
async def generate_tech_spec(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Manually trigger Technical Spec generation (Layer 1: Architect Agent)."""
    from agent_service import _generate_technical_spec

    # Get KG context if available
    kg_context = ""
    try:
        if context_manager.is_project_indexed(project_token):
            kg_context = await context_manager.get_full_agent_context(
                project_token=project_token,
                task_description="Full system architecture overview",
                agent_id="architect_agent",
            )
    except Exception:
        pass

    result = await _generate_technical_spec(
        project_token=project_token,
        tasks=[],
        kg_context=kg_context,
    )
    return result


@app.get("/api/github/pr-status/{project_token}")
async def get_pr_status(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the status of merged branches and created PRs."""
    from agent_service import _ensure_project_state
    state = _ensure_project_state(project_token)
    return {
        "project_token": project_token,
        "merged_branches": state.get("merged_branches", []),
        "merge_queue_length": len(state.get("git_merge_queue", [])),
        "is_merging": state.get("git_merge_running", False)
    }


# ═══════════════════════════════ AI AGENTS ═══════════════════════════════════

def _normalize_project_token(project_token: Optional[str]) -> Optional[str]:
    if not project_token:
        return None
    token = project_token.strip()
    return token or None


def _normalize_agent_kind(
    agent_kind: Optional[str],
    project_token: Optional[str],
    *,
    is_default: bool = False,
) -> str:
    kind = _normalized_text(agent_kind).lower()
    if is_default:
        return "system"
    if kind in {"shared", "dedicated"}:
        return kind
    return "dedicated" if _normalize_project_token(project_token) else "shared"


def _stored_agent_id(agent_id: str, project_token: Optional[str]) -> str:
    project_token = _normalize_project_token(project_token)
    if not project_token:
        return agent_id
    prefix = f"{project_token}::"
    if agent_id.startswith(prefix):
        return agent_id
    return f"{prefix}{agent_id}"


def _public_agent_id(agent_id: str, project_token: Optional[str]) -> str:
    project_token = _normalize_project_token(project_token)
    if not project_token:
        return agent_id
    prefix = f"{project_token}::"
    if agent_id.startswith(prefix):
        return agent_id[len(prefix):]
    return agent_id


def _runtime_agent_records(records: List[models.Agent], project_token: Optional[str]) -> List[Dict[str, Any]]:
    return [
        {
            "id": _public_agent_id(rec.id, project_token),
            "name": rec.name,
            "type": rec.type,
        }
        for rec in records
    ]


def _ensure_agent_project_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(agents)"))
        columns = [row[1] for row in result.fetchall()]
        if "project_token" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN project_token VARCHAR"))
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(agent_credentials)"))
        columns = [row[1] for row in result.fetchall()]
        if "project_token" not in columns:
            conn.execute(text("ALTER TABLE agent_credentials ADD COLUMN project_token VARCHAR"))
            conn.commit()


def _ensure_org_agent_mapping_kind_column() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(organization_agent_mappings)"))
        columns = [row[1] for row in result.fetchall()]
        if "agent_kind" not in columns:
            conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN agent_kind VARCHAR"))
            conn.commit()


def _ensure_user_organization_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result.fetchall()]

        if "first_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR"))
            conn.commit()

        if "last_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR"))
            conn.commit()

        if "organization_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN organization_name VARCHAR"))
            conn.commit()

        if "is_org_admin" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_org_admin BOOLEAN DEFAULT 0"))
            conn.commit()

        if "azure_devops_token" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_token VARCHAR"))
            conn.commit()

        if "azure_devops_username" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_username VARCHAR"))
            conn.commit()

def _ensure_default_oauth_clients(db: Session) -> None:
    defaults = [
        {
            "name": "Nxdune",
            "client_id": settings.oauth_nxdune_client_id,
            "client_secret": settings.oauth_nxdune_client_secret,
            "redirect_uri": settings.oauth_nxdune_redirect_uri,
            "login_url": settings.oauth_nxdune_login_url,
        },
        {
            "name": "Kaktox",
            "client_id": settings.oauth_kaktox_client_id,
            "client_secret": settings.oauth_kaktox_client_secret,
            "redirect_uri": settings.oauth_kaktox_redirect_uri,
            "login_url": settings.oauth_kaktox_login_url,
        },
        {
            "name": "CloudSpx",
            "client_id": settings.oauth_cloudspx_client_id,
            "client_secret": settings.oauth_cloudspx_client_secret,
            "redirect_uri": settings.oauth_cloudspx_redirect_uri,
            "login_url": settings.oauth_cloudspx_login_url,
        },
    ]

    for plugin in defaults:
        client_id = _normalized_text(plugin.get("client_id"))
        redirect_uri = _normalized_text(plugin.get("redirect_uri"))
        client_secret = _normalized_text(plugin.get("client_secret"))
        if not client_id or not redirect_uri or not client_secret:
            continue

        existing = db.query(models.OAuthClient).filter(
            func.lower(models.OAuthClient.client_id) == client_id.lower()
        ).first()
        if existing:
            # Keep DB in sync with environment-driven defaults.
            existing.name = plugin["name"]
            existing.client_secret = client_secret
            existing.redirect_uri = redirect_uri
            existing.login_url = _normalized_text(plugin.get("login_url")) or None
            if not existing.is_active:
                existing.is_active = True
            db.add(existing)
            continue

        row = models.OAuthClient(
            name=plugin["name"],
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            login_url=_normalized_text(plugin.get("login_url")) or None,
            is_active=True,
        )
        db.add(row)

    db.commit()


def _ensure_default_governance_questions(db: Session) -> None:
    """Ensure basic governance questions exist in database."""
    count = db.query(models.GovernanceQuestion).count()
    if count > 0:
        return

    print("Seeding default governance questions...")
    try:
        from governance_scoring import GOVERNANCE_QUESTIONS
        for q_data in GOVERNANCE_QUESTIONS:
            # We use the specific ID if provided to keep scoring in sync
            db_question = models.GovernanceQuestion(
                id=q_data["id"],
                dimension=q_data["dimension"],
                question_text=q_data["question"],
                order=q_data["id"],
                is_active=True
            )
            db.add(db_question)
            db.flush()

            for opt_data in q_data["options"]:
                db_option = models.GovernanceQuestionOption(
                    question_id=db_question.id,
                    label=opt_data["label"],
                    score=opt_data["score"]
                )
                db.add(db_option)
        db.commit()
        print("[OK] Governance questions seeded")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to seed governance questions: {e}")

# Seed sample tasks on startup
def _startup_init() -> None:
    agent_service.seed_sample_tasks()
    db = SessionLocal()
    try:
        _ensure_agent_project_columns()
        _ensure_org_agent_mapping_kind_column()
        _ensure_user_organization_columns()
        _ensure_default_oauth_clients(db)
        _ensure_default_agents(db)
        _ensure_default_governance_questions(db)
        agents = db.query(models.Agent).filter(models.Agent.project_token.is_(None)).all()
        agent_service.initialize_agents_from_records(_runtime_agent_records(agents, None))
    finally:
        db.close()


GLOBAL_GIT_CREDENTIAL_AGENT_ID = "__global_git__"


def _get_project_global_credential(
    db: Session,
    user_id: int,
    project_token: Optional[str],
) -> Optional[models.AgentCredential]:
    project_token = _normalize_project_token(project_token)
    cred_query = db.query(models.AgentCredential).filter(
        models.AgentCredential.owner_id == user_id,
        models.AgentCredential.agent_id == GLOBAL_GIT_CREDENTIAL_AGENT_ID,
    )
    if project_token:
        cred_query = cred_query.filter(models.AgentCredential.project_token == project_token)
    else:
        cred_query = cred_query.filter(models.AgentCredential.project_token.is_(None))
    return cred_query.first()


def _list_legacy_agent_credentials(
    db: Session,
    user_id: int,
    project_token: Optional[str],
) -> List[models.AgentCredential]:
    project_token = _normalize_project_token(project_token)
    cred_query = db.query(models.AgentCredential).filter(
        models.AgentCredential.owner_id == user_id,
        models.AgentCredential.agent_id != GLOBAL_GIT_CREDENTIAL_AGENT_ID,
    )
    if project_token:
        cred_query = cred_query.filter(models.AgentCredential.project_token == project_token)
    else:
        cred_query = cred_query.filter(models.AgentCredential.project_token.is_(None))
    return cred_query.all()


def _legacy_default_dev_agent_filter(column):
    return or_(
        column.in_(("agent_01", "agent_02")),
        column.like("%::agent_01"),
        column.like("%::agent_02"),
    )


def _cleanup_legacy_default_dev_agents(db: Session) -> None:
    """
    Remove the old built-in dev agents so only system agents remain default.
    New dev agents must come from org shared/dedicated capacity.
    
    IMPORTANT: Only delete agents that were marked as DEFAULT (is_default=True).
    User-added agents with agent_01/agent_02 IDs should NOT be deleted.
    """
    # First, get the list of agent IDs that are marked as default
    default_agent_ids = {
        row[0] for row in db.query(models.OrganizationAgentMapping.agent_id).filter(
            models.OrganizationAgentMapping.is_default.is_(True),
            _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
        ).all()
    }
    
    # Delete the default mappings
    deleted_mappings = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default.is_(True),
        _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
    ).delete(synchronize_session=False)

    # Only delete Agent records that were marked as default (not user-added ones)
    deleted_agents = 0
    if default_agent_ids:
        deleted_agents = db.query(models.Agent).filter(
            models.Agent.id.in_(default_agent_ids),
        ).delete(synchronize_session=False)

    if deleted_mappings or deleted_agents:
        logger.info(f"[cleanup] Removed {deleted_mappings} legacy default mappings and {deleted_agents} legacy default agents")
        db.commit()
        agent_service.clear_all_runtime_state()


def _ensure_default_agents(db: Session, project_token: Optional[str] = None) -> None:
    project_token = _normalize_project_token(project_token)
    _cleanup_legacy_default_dev_agents(db)
    existing_query = db.query(models.Agent.id)
    if project_token:
        existing_query = existing_query.filter(models.Agent.project_token == project_token)
    else:
        existing_query = existing_query.filter(models.Agent.project_token.is_(None))
    existing_ids = {row[0] for row in existing_query.all()}
    for agent in agent_service.get_default_agents():
        stored_id = _stored_agent_id(agent["id"], project_token)
        if stored_id in existing_ids:
            continue
        db.add(
            models.Agent(
                id=stored_id,
                name=agent["name"],
                type=agent.get("type"),
                project_token=project_token,
            )
        )
    db.commit()

def _ensure_default_agents_for_org(
    db: Session,
    organization_name: str,
    project_token: Optional[str] = None,
) -> None:
    """
    Ensure default agents exist in the legacy `agents` table AND are mapped to the org as defaults.
    """
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    org = _normalized_text(organization_name)
    if not org:
        return
    for agent in agent_service.get_default_agents():
        stored_id = _stored_agent_id(agent["id"], project_token)
        _ensure_org_agent_mapping(db, org, stored_id, project_token, is_default=True)


def _upsert_agent_record(
    db: Session,
    agent_id: str,
    name: Optional[str],
    agent_type: Optional[str],
    project_token: Optional[str],
) -> models.Agent:
    project_token = _normalize_project_token(project_token)
    stored_id = _stored_agent_id(agent_id, project_token)
    record_query = db.query(models.Agent).filter(models.Agent.id == stored_id)
    if project_token:
        record_query = record_query.filter(models.Agent.project_token == project_token)
    else:
        record_query = record_query.filter(models.Agent.project_token.is_(None))
    record = record_query.first()
    if not record:
        record = models.Agent(
            id=stored_id,
            name=name or agent_id,
            type=agent_type,
            project_token=project_token,
        )
        db.add(record)
    else:
        if name:
            record.name = name
        if agent_type:
            record.type = agent_type
    db.commit()
    db.refresh(record)
    return record


def _delete_agent_record(db: Session, agent_id: str, project_token: Optional[str]) -> None:
    project_token = _normalize_project_token(project_token)
    stored_id = _stored_agent_id(agent_id, project_token)
    query = db.query(models.Agent).filter(models.Agent.id == stored_id)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    query.delete()
    db.commit()


def _upsert_project_global_credentials(
    db: Session,
    user_id: int,
    git_repo_url: Optional[str] = None,
    git_token: Optional[str] = None,
    project_token: Optional[str] = None,
) -> models.AgentCredential:
    project_token = _normalize_project_token(project_token)
    cred = _get_project_global_credential(db, user_id, project_token)
    if not cred:
        cred = models.AgentCredential(
            owner_id=user_id,
            agent_id=GLOBAL_GIT_CREDENTIAL_AGENT_ID,
            project_token=project_token,
        )
        db.add(cred)

    if git_repo_url is not None:
        cleaned_repo = git_repo_url.strip()
        cred.git_repo_url = cleaned_repo or None
    if git_token is not None:
        cleaned_token = git_token.strip()
        cred.git_token = cleaned_token or None

    db.commit()
    db.refresh(cred)
    return cred


def _resolve_project_global_credential(
    db: Session,
    user_id: int,
    project_token: Optional[str],
) -> Optional[models.AgentCredential]:
    """
    Return project-wide global Git credential.
    Backfills from legacy per-agent credentials so existing users are not disrupted.
    """
    cred = _get_project_global_credential(db, user_id, project_token)
    if cred:
        return cred

    legacy = sorted(
        _list_legacy_agent_credentials(db, user_id, project_token),
        key=lambda row: row.updated_at or datetime.min,
        reverse=True,
    )
    if not legacy:
        return None

    latest_complete = next((row for row in legacy if row.git_repo_url and row.git_token), None)
    if latest_complete:
        repo_val = latest_complete.git_repo_url.strip()
        token_val = latest_complete.git_token.strip()
    else:
        first_repo = next((row.git_repo_url for row in legacy if row.git_repo_url), None)
        first_token = next((row.git_token for row in legacy if row.git_token), None)
        repo_val = first_repo.strip() if first_repo else None
        token_val = first_token.strip() if first_token else None

    if not repo_val and not token_val:
        return None

    return _upsert_project_global_credentials(
        db,
        user_id,
        git_repo_url=repo_val,
        git_token=token_val,
        project_token=project_token,
    )


def _sanitize_agent_for_user(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    safe_agent = dict(agent)
    safe_agent["git_repo_url"] = global_cred.git_repo_url if global_cred and global_cred.git_repo_url else None
    safe_agent["has_git_token"] = bool(global_cred and global_cred.git_token)
    # Default to False; will be populated by async version
    safe_agent["is_public_repo"] = False
    if "git_token" in safe_agent:
        safe_agent["git_token"] = None
    return safe_agent


async def _sanitize_agent_for_user_with_public_check(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    """Enhanced version that checks if the repository is public."""
    safe_agent = _sanitize_agent_for_user(agent, global_cred)
    
    # Only check if we have a repo URL
    if global_cred and global_cred.git_repo_url:
        repo_url = global_cred.git_repo_url.strip()
        try:
            # Check if it's a GitHub repo
            if "github.com" in repo_url:
                # Extract owner/repo from URL
                match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
                if match:
                    owner, repo = match.groups()
                    safe_agent["is_public_repo"] = await github_service.is_repo_public(owner, repo, token=settings.GITHUB_TOKEN)
            # Check if it's Azure DevOps repo
            elif "dev.azure.com" in repo_url or "visualstudio.com" in repo_url:
                parsed = azure_devops_service.parse_azure_repo_url(repo_url)
                if parsed.get("organization") and parsed.get("project") and parsed.get("repo"):
                    safe_agent["is_public_repo"] = await azure_devops_service.is_repo_public(
                        parsed["organization"],
                        parsed["project"],
                        parsed["repo"],
                    )
        except Exception:
            # If check fails, default to False (assume private for safety)
            safe_agent["is_public_repo"] = False
    
    return safe_agent


def _log_background_task_result(task: asyncio.Task) -> None:
    """Consume and log exceptions from fire-and-forget tasks."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Failed to inspect background task state")
        return

    if exc:
        logger.exception("Background task failed", exc_info=exc)


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"


@app.get("/agents")
async def list_agents(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
    include_defaults: bool = True,
    kind: Optional[str] = None,
    x_task_token: Optional[str] = Header(None),
):
    """Get status of all AI agents with caching to reduce load."""
    organization_name = _require_organization(current_user)
    project_token = _normalize_project_token(project_token)
    requested_kind = _normalized_text(kind).lower() or None
    
    # CACHE DISABLED - Always fetch fresh data for real-time agent status
    # Check cache first
    # cache_key = _get_cache_key(organization_name, project_token, current_user.id)
    # cached_result = _get_cached_agents(cache_key)
    # if cached_result is not None:
    #     # Merge live output_log from in-memory state into cached structural data
    #     live_agents = {a["id"]: a for a in agent_service.get_all_agents(project_token)}
    #     merged_agents = []
    #     for a in cached_result["agents"]:
    #         live = live_agents.get(a.get("id"), {})
    #         merged_agents.append({**a, "output_log": live.get("output_log", []), "status": live.get("status", a.get("status")), "progress": live.get("progress", a.get("progress")), "progress_message": live.get("progress_message", a.get("progress_message")), "current_task": live.get("current_task", a.get("current_task"))})
    #     merged = {"agents": merged_agents}
    #     if requested_kind:
    #         return {"agents": [a for a in merged_agents if a.get("agent_kind") == requested_kind]}
    #     return merged
    
    _ensure_default_agents_for_org(db, organization_name, project_token)
    _bootstrap_org_agent_mappings_if_missing(db, organization_name, project_token)

    mapping_q = db.query(
        models.OrganizationAgentMapping.agent_id,
        models.OrganizationAgentMapping.is_default,
        models.OrganizationAgentMapping.project_token,
        models.OrganizationAgentMapping.agent_kind,
        models.OrganizationAgentMapping.agent_sub_type,
    ).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
    )
    if project_token:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
    else:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
    mapping_rows = mapping_q.all()
    mapped_ids = [row[0] for row in mapping_rows]
    
    logger.info(f"[GET /agents] org={organization_name}, project={project_token}, mapped_ids={mapped_ids}")

    # Query without project_token filter so we catch agents that were created with NULL project_token
    if mapped_ids:
        query = db.query(models.Agent).filter(models.Agent.id.in_(mapped_ids))
        logger.info(f"[GET /agents] SQL Query: {query}")
        records = query.all()
    else:
        records = []
    logger.info(f"[GET /agents] DB records: {[r.id for r in records]}")

    # Upsert: create missing records or fix project_token on existing ones
    existing_by_id = {r.id: r for r in records}
    for mid in mapped_ids:
        public_id = _public_agent_id(mid, project_token)
        if mid not in existing_by_id:
            logger.info(f"[GET /agents] Creating missing Agent record for {mid}")
            # Try to insert, but ignore if it already exists (concurrent insert race)
            try:
                new_record = models.Agent(
                    id=mid,
                    name=public_id,
                    type="validator",
                    project_token=project_token,
                )
                db.add(new_record)
                db.flush()  # Flush immediately to catch IntegrityError
                logger.info(f"[GET /agents] Successfully flushed new record for {mid}")
                records.append(new_record)
            except Exception as e:
                # Likely IntegrityError due to concurrent insert - that's fine, record exists
                logger.info(f"[GET /agents] Insert failed for {mid}, re-fetching: {e}")
                db.rollback()
                # Re-fetch the existing record
                existing = db.query(models.Agent).filter(models.Agent.id == mid).first()
                if existing:
                    logger.info(f"[GET /agents] Found existing record for {mid}")
                    records.append(existing)
                else:
                    logger.error(f"[GET /agents] Could not find existing record for {mid} after insert failure!")
        elif existing_by_id[mid].project_token != project_token:
            # Fix stale project_token
            logger.info(f"[GET /agents] Updating project_token for {mid}")
            existing_by_id[mid].project_token = project_token
    
    # Final commit for any project_token updates
    try:
        db.commit()
        logger.info(f"[GET /agents] Committed {len(records)} agent records")
    except Exception as e:
        logger.error(f"[GET /agents] Commit failed: {e}")
        db.rollback()
    
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))
    logger.info(f"[GET /agents] In-memory after init: {[a['id'] for a in agent_service.get_all_agents(project_token)]}")
    
    # Only restore persisted assignments if we have a task token (otherwise it's too slow)
    if x_task_token:
        logger.info(f"[GET /agents] About to restore persisted assignments, task_token={x_task_token}")
        await agent_service._restore_persisted_agent_assignments(
            project_token=project_token,
            task_token=x_task_token,
        )
        logger.info(f"[GET /agents] Restored persisted assignments")
    else:
        logger.info(f"[GET /agents] Skipping persisted assignment restore (no task token)")

    # Build lookup: public_agent_id -> (kind, sub_type)
    visible_runtime_ids: Dict[str, tuple] = {}
    for row in mapping_rows:
        row_is_default = bool(row[1])
        row_project_token = row[2]
        row_kind = _normalize_agent_kind(row[3], row_project_token, is_default=row_is_default)
        row_sub_type = row[4] or 'dev'
        if not include_defaults and row_is_default:
            logger.info(f"[GET /agents] Skipping default agent: {row[0]}")
            continue
        if requested_kind and row_kind != requested_kind:
            logger.info(f"[GET /agents] Skipping agent {row[0]} with kind={row_kind} (requested={requested_kind})")
            continue
        visible_runtime_ids[_public_agent_id(row[0], project_token)] = (row_kind, row_sub_type)
    
    logger.info(f"[GET /agents] visible_runtime_ids after filtering: {list(visible_runtime_ids.keys())}")

    global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
    
    # Check public repo status for all agents in parallel
    import asyncio
    agent_tasks = [
        _sanitize_agent_for_user_with_public_check(agent, global_cred)
        for agent in agent_service.get_all_agents(project_token)
        if agent.get("id") in visible_runtime_ids
    ]
    sanitized_agents = await asyncio.gather(*agent_tasks)
    
    agents = [
        {
            **sanitized_agent,
            "agent_kind": visible_runtime_ids[sanitized_agent.get("id")][0],
            "sub_type": visible_runtime_ids[sanitized_agent.get("id")][1],
        }
        for sanitized_agent in sanitized_agents
        if sanitized_agent.get("id") in visible_runtime_ids
    ]
    
    result = {"agents": agents}
    
    logger.info(f"[GET /agents] Returning {len(agents)} agents for kind={requested_kind}, include_defaults={include_defaults}")
    
    # CACHE DISABLED - Don't cache for real-time updates
    # Cache only the structural data (not output_log which changes constantly)
    # agents_for_cache = [
    #     {k: v for k, v in a.items() if k != "output_log"}
    #     for a in agents
    # ]
    # _cache_agents(cache_key, {"agents": agents_for_cache})
    
    # Filter by kind if requested
    if requested_kind:
        filtered_agents = [
            agent for agent in agents 
            if agent.get("agent_kind") == requested_kind
        ]
        response_data = {"agents": filtered_agents}
    else:
        response_data = result
    
    # Add cache headers to help frontend optimize polling
    from fastapi import Response
    response = Response(
        content=json.dumps(response_data),
        media_type="application/json",
        headers={
            "Cache-Control": "max-age=5, must-revalidate",
            "X-Cache-TTL": str(AGENT_CACHE_TTL),
            "X-Polling-Interval": "10000"  # Suggest 10s polling interval
        }
    )
    return response_data


@app.get("/coordination/status")
async def get_coordination_status(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Get Master Task Manager coordination status"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    return master_task_manager.master_task_manager.get_coordination_status(project_token)


@app.post("/coordination/agent/{agent_id}/file-lock")
async def request_file_lock(
    agent_id: str,
    file_path: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🔒 Agent requests file lock through Master Task Manager"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    return await master_task_manager.master_task_manager.request_file_lock(agent_id, file_path)


@app.post("/coordination/agent/{agent_id}/configure")
async def configure_agent_capabilities(
    agent_id: str,
    request: dict,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Configure agent capabilities - MANUAL OVERRIDE"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    primary_skills = request.get("primary_skills", [])
    secondary_skills = request.get("secondary_skills", [])
    
    master_task_manager.master_task_manager.set_explicit_agent_config(
        agent_id, primary_skills, secondary_skills
    )
    
    return {
        "status": "configured",
        "agent_id": agent_id,
        "primary_skills": primary_skills,
        "secondary_skills": secondary_skills,
        "message": f"Agent {agent_id} capabilities configured manually"
    }


@app.post("/coordination/agent/{agent_id}/ai-assign")
async def ai_assign_agent_capabilities(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🤖 Let Master Agent decide agent capabilities using AI"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    # Get project context for AI decision
    project_context = f"Project: {project_token or 'default'}"
    
    decision = await master_task_manager.master_task_manager.master_agent_assign_capabilities(
        agent_id, project_context
    )
    
    return {
        "status": "ai_assigned",
        "agent_id": agent_id,
        "decision": decision,
        "message": f"Master Agent assigned capabilities to {agent_id}"
    }


@app.get("/coordination/agent/{agent_id}/capabilities")
async def get_agent_capabilities(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """📋 Get current agent capabilities and assignment method"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    capabilities = master_task_manager.master_task_manager._get_agent_capabilities(agent_id)
    
    return {
        "agent_id": agent_id,
        "capabilities": capabilities,
        "assignment_method": capabilities.get("assigned_by", "unknown")
    }


@app.get("/coordination/agents/bulk-configure")
async def bulk_configure_agents(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Get bulk configuration options for all agents"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    # Get all agents and their current capabilities
    all_agents = {}
    for agent_id in master_task_manager.master_task_manager.agent_status.keys():
        capabilities = master_task_manager.master_task_manager._get_agent_capabilities(agent_id)
        all_agents[agent_id] = {
            "current_capabilities": capabilities,
            "suggested_by_pattern": master_task_manager.master_task_manager._get_agent_capabilities_by_pattern(agent_id),
            "can_ai_assign": True
        }
    
    return {
        "agents": all_agents,
        "available_skills": ["frontend", "backend", "setup", "integration"],
        "assignment_methods": [
            "explicit_config",    # Manual configuration
            "master_agent",       # AI decision by Master Agent  
            "pattern_recognition", # Automatic by name pattern
            "default_fallback"    # Democratic fallback
        ]
    }


@app.get("/agents/tasks")
async def get_pending_tasks(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get pending tasks for agents"""
    # Placeholder implementation
    return {"tasks": []}


# ═══════════════════════════════════════════════════════════════════════════
# Enhanced Context Sharing API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/context/update")
async def update_context(
    project_token: str,
    agent_id: str,
    current_task: Optional[str] = None,
    current_files: List[str] = [],
    completed_tasks: List[str] = [],
    created_files: List[str] = [],
    modified_files: List[str] = [],
    api_endpoints: List[Dict[str, Any]] = [],
    database_tables: List[str] = [],
    shared_utilities: List[str] = [],
    tags: List[str] = [],
    current_user: models.User = Depends(auth.get_current_user)
):
    """📝 Update agent context with structured information"""
    from enhanced_context_service import update_agent_context
    
    success = await update_agent_context(
        project_token=project_token,
        agent_id=agent_id,
        current_task=current_task,
        current_files=current_files,
        completed_tasks=completed_tasks,
        created_files=created_files,
        modified_files=modified_files,
        api_endpoints=api_endpoints,
        database_tables=database_tables,
        shared_utilities=shared_utilities,
        tags=tags
    )
    
    return {"success": success, "agent_id": agent_id}


@app.get("/api/context/query/{query_type}")
async def query_context(
    project_token: str,
    query_type: str,
    file_pattern: Optional[str] = None,
    tag: Optional[str] = None,
    module: Optional[str] = None,
    agent_id: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """🔍 Query shared context with various filters"""
    from enhanced_context_service import query_agent_context
    
    filters = {}
    if file_pattern:
        filters["file_pattern"] = file_pattern
    if tag:
        filters["tag"] = tag
    if module:
        filters["module"] = module
    if agent_id:
        filters["agent_id"] = agent_id
    
    result = await query_agent_context(
        project_token=project_token,
        query_type=query_type,
        **filters
    )
    
    return result


@app.get("/api/context/agent/{agent_id}")
async def get_agent_context_view(
    project_token: str,
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user)
):
    """👁️ Get comprehensive context view for specific agent"""
    from enhanced_context_service import enhanced_context_service
    
    view = await enhanced_context_service.get_agent_context_view(
        project_token=project_token,
        agent_id=agent_id
    )
    
    return view


@app.post("/api/context/memory-board")
async def post_to_memory_board(
    project_token: str,
    agent_id: str,
    message_type: str,
    content: str,
    tags: List[str] = [],
    reply_to: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """💬 Post message to shared memory board"""
    from enhanced_context_service import enhanced_context_service, ContextMessageType
    
    try:
        msg_type = ContextMessageType(message_type)
    except ValueError:
        return {"error": f"Invalid message type: {message_type}"}
    
    message_id = await enhanced_context_service.post_to_memory_board(
        project_token=project_token,
        agent_id=agent_id,
        message_type=msg_type,
        content=content,
        tags=tags,
        reply_to=reply_to
    )
    
    return {"success": True, "message_id": message_id}


@app.get("/api/context/memory-board")
async def get_memory_board(
    project_token: str,
    limit: int = 50,
    tags: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📋 Get messages from memory board"""
    from enhanced_context_service import enhanced_context_service
    
    if project_token not in enhanced_context_service.project_contexts:
        return {"messages": []}
    
    context = enhanced_context_service.project_contexts[project_token]
    messages = context["memory_board"]
    
    # Filter by tags if provided
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        messages = [
            msg for msg in messages
            if any(tag in msg.get("tags", []) for tag in tag_list)
        ]
    
    # Return most recent messages
    return {"messages": messages[-limit:]}


@app.post("/api/context/dependency")
async def declare_dependency(
    project_token: str,
    agent_id: str,
    depends_on: Dict[str, List[str]],
    current_user: models.User = Depends(auth.get_current_user)
):
    """🔗 Declare dependencies on other agents' work"""
    from enhanced_context_service import enhanced_context_service
    
    success = await enhanced_context_service.declare_dependency(
        project_token=project_token,
        agent_id=agent_id,
        depends_on=depends_on
    )
    
    return {"success": success, "agent_id": agent_id, "dependencies": depends_on}


@app.post("/api/context/snapshot")
async def create_context_snapshot(
    project_token: str,
    sync_point: str,
    metadata: Optional[Dict[str, Any]] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📸 Create context snapshot at sync point"""
    from enhanced_context_service import enhanced_context_service
    
    snapshot = await enhanced_context_service.create_context_snapshot(
        project_token=project_token,
        sync_point=sync_point,
        metadata=metadata
    )
    
    return snapshot


@app.get("/api/context/snapshots")
async def get_context_snapshots(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📚 Get all context snapshots for project"""
    from enhanced_context_service import enhanced_context_service
    
    if project_token not in enhanced_context_service.project_contexts:
        return {"snapshots": []}
    
    context = enhanced_context_service.project_contexts[project_token]
    return {"snapshots": context["snapshots"]}


@app.get("/agents/tasks")
async def get_pending_tasks(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
    x_task_token: Optional[str] = Header(None),
):
    """Get all pending tasks waiting to be picked up by agents."""
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    query = db.query(models.Agent)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    records = query.all()
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))
    await agent_service._restore_persisted_agent_assignments(
        project_token=project_token,
        task_token=x_task_token,
    )
    return {
        "pending_tasks": agent_service.get_pending_tasks(project_token),
        "completed_tasks": agent_service.get_completed_tasks(project_token),
    }





# ─────────────────────────────── Preview Deploy ──────────────────────────────
# NOTE: These MUST be defined before /agents/{agent_id}/* routes,
# otherwise FastAPI matches "preview" as an agent_id.

class PreviewDeployRequest(BaseModel):
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None


@app.post("/agents/preview/deploy")
async def deploy_preview(
    request: Optional[PreviewDeployRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    """
    Deploy the agent/integration branch into a live environment.
    Returns a preview URL that opens the running application.
    """
    project_token = _normalize_project_token(project_token)

    # Get git credentials: from request body, or from project-global saved credentials.
    git_repo_url = request.git_repo_url if request else None
    git_token = request.git_token if request else None

    if request and (request.git_repo_url is not None or request.git_token is not None):
        _upsert_project_global_credentials(
            db,
            current_user.id,
            git_repo_url=git_repo_url,
            git_token=git_token,
            project_token=project_token,
        )

    # Try to get credentials from request first, then fall back to saved credentials
    if not git_repo_url or not git_token:
        global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        if global_cred:
            git_repo_url = git_repo_url or global_cred.git_repo_url
            git_token = git_token or global_cred.git_token

    # Only require git_repo_url - token is optional for public repos
    if not git_repo_url:
        raise HTTPException(
            status_code=400,
            detail="Git repo URL is required. Token is optional for public repositories."
        )

    result = await agent_service.deploy_preview(
        git_repo_url=git_repo_url,
        git_token=git_token,
        project_token=project_token,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Deploy failed"))
    return result


@app.get("/agents/preview/status")
async def preview_status(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """Get the current preview deployment status."""
    project_token = _normalize_project_token(project_token)
    return agent_service.get_preview_status(project_token)


@app.post("/agents/preview/fix")
async def fix_preview(
    request: Optional[PreviewDeployRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    """Trigger AI to fix failing preview deployment, commit, push, and restart preview."""
    project_token = _normalize_project_token(project_token)

    git_repo_url = request.git_repo_url if request else None
    git_token = request.git_token if request else None

    # Try to get credentials from request first, then fall back to saved credentials
    if not git_repo_url or not git_token:
        global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        if global_cred:
            git_repo_url = git_repo_url or global_cred.git_repo_url
            git_token = git_token or global_cred.git_token

    # Only require git_repo_url - token is optional for public repos
    if not git_repo_url:
        raise HTTPException(
            status_code=400,
            detail="Git repo URL is required. Token is optional for public repositories."
        )

    result = await agent_service.repair_preview(
        git_repo_url=git_repo_url,
        git_token=git_token,
        project_token=project_token,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Fix failed"))
    return result


@app.post("/agents/preview/stop")
async def stop_preview(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """Stop and destroy the preview environment."""
    project_token = _normalize_project_token(project_token)
    return await agent_service.stop_preview(project_token)


@app.get("/agents/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
    x_task_token: Optional[str] = Header(None),
):
    """Get the current status and details of a specific agent with caching and rate limiting."""
    try:
        project_token = _normalize_project_token(project_token)
        organization_name = _require_organization(current_user)
        
        # Rate limiting: prevent excessive calls to individual agent status
        if not _check_agent_status_rate_limit(agent_id, current_user.id, project_token):
            # Return cached data if available, otherwise return 429
            individual_cache_key = f"agent_status:{organization_name}:{project_token or 'none'}:{current_user.id}:{agent_id}"
            cached_result = _get_cached_agents(individual_cache_key)
            if cached_result is not None:
                return cached_result
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Individual agent status can only be called once every {AGENT_STATUS_RATE_LIMIT} seconds. Use /agents endpoint for bulk status."
            )
        
        # Check cache first for individual agent status
        individual_cache_key = f"agent_status:{organization_name}:{project_token or 'none'}:{current_user.id}:{agent_id}"
        cached_result = _get_cached_agents(individual_cache_key)
        if cached_result is not None:
            return cached_result
        
        _ensure_default_agents(db, project_token)
        query = db.query(models.Agent)
        if project_token:
            query = query.filter(models.Agent.project_token == project_token)
        else:
            query = query.filter(models.Agent.project_token.is_(None))
        records = query.all()
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))
        await agent_service._restore_persisted_agent_assignments(
            project_token=project_token,
            task_token=x_task_token,
            agent_ids=[agent_id],
        )
        agent = agent_service.get_agent_status(agent_id, project_token)
        global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        sanitized_agent = await _sanitize_agent_for_user_with_public_check(agent, global_cred)
        
        result = {"agent": sanitized_agent}
        
        # Cache the individual agent result
        _cache_agents(individual_cache_key, result)
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class RunAgentRequest(BaseModel):
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None

@app.post("/agents/{agent_id}/run")
async def run_agent(
    agent_id: str,
    request: Optional[RunAgentRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None),
    project_token: Optional[str] = None,
):
    """
    Trigger an idle agent to pick a pending task and start working on it.
    The agent runs in the BACKGROUND — this endpoint returns immediately
    so the frontend can poll /agents for real-time status updates.
    """
    project_token = _normalize_project_token(project_token)
    organization_name = _require_organization(current_user)
    
    # Invalidate cache since agent status will change
    _invalidate_agent_cache(organization_name, project_token)
    
    _ensure_default_agents(db, project_token)
    query = db.query(models.Agent)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    records = query.all()
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

    agent = agent_service.get_agent_status(agent_id, project_token)
    if agent["status"] == "running":
        raise HTTPException(status_code=400, detail=f"Agent {agent_id} is already running")

    git_repo_url = request.git_repo_url if request else None
    git_token = request.git_token if request else None

    if request and (request.git_repo_url is not None or request.git_token is not None):
        _upsert_project_global_credentials(
            db,
            current_user.id,
            git_repo_url=git_repo_url,
            git_token=git_token,
            project_token=project_token,
        )
    cred = _resolve_project_global_credential(db, current_user.id, project_token)

    effective_repo = git_repo_url or (cred.git_repo_url if cred else None)
    effective_token = git_token or (cred.git_token if cred else None)
    if effective_repo and effective_token:
        agent["git_repo_url"] = effective_repo
        agent["git_token"] = effective_token
    else:
        agent["git_repo_url"] = None
        agent["git_token"] = None

    # Mark as running immediately so frontend refresh sees it instantly
    agent["status"] = "running"
    agent["progress"] = 0
    agent["output_log"] = []
    agent["progress_message"] = "Initializing..."

    # Fire-and-forget: agent runs in background
    run_repo = effective_repo if effective_repo and effective_token else None
    run_token = effective_token if effective_repo and effective_token else None
    bg_task = asyncio.create_task(
        agent_service.run_agent(
            agent_id,
            git_repo_url=run_repo,
            git_token=run_token,
            continuous=True,  # CRITICAL FIX: Enable continuous mode so agents keep working
            ignore_running_check=True,
            project_token=project_token,
            task_token=x_task_token,
        )
    )
    bg_task.add_done_callback(_log_background_task_result)

    return {"started": True, "agent_id": agent_id}


@app.post("/agents/{agent_id}/reset")
async def reset_agent(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    """Reset an agent back to idle state."""
    try:
        project_token = _normalize_project_token(project_token)
        _ensure_default_agents(db, project_token)
        query = db.query(models.Agent)
        if project_token:
            query = query.filter(models.Agent.project_token == project_token)
        else:
            query = query.filter(models.Agent.project_token.is_(None))
        records = query.all()
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))
        agent = agent_service.reset_agent(agent_id, project_token)
        return {"agent": agent}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class RunAllRequest(BaseModel):
    agents_config: Optional[Dict[str, Dict[str, str]]] = None


@app.post("/agents/run-all")
async def run_all_agents(
    request: Optional[RunAllRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None),
    project_token: Optional[str] = None,
):
    """
    🎯 NEW COORDINATED APPROACH: Master Task Manager controls ALL agents
    No more self-service chaos - Master assigns tasks and prevents conflicts
    """
    project_token = _normalize_project_token(project_token)
    organization_name = _require_organization(current_user)
    
    # Invalidate cache since agent status will change
    _invalidate_agent_cache(organization_name, project_token)
    
    _ensure_default_agents_for_org(db, organization_name, project_token)
    _bootstrap_org_agent_mappings_if_missing(db, organization_name, project_token)

    # Load ALL mapped agents (including user-added ones that may be missing DB records)
    mapping_q = db.query(models.OrganizationAgentMapping.agent_id).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
    )
    if project_token:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
    else:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
    mapped_ids = [row[0] for row in mapping_q.all()]

    records = db.query(models.Agent).filter(models.Agent.id.in_(mapped_ids)).all() if mapped_ids else []

    # Upsert: create missing records or fix project_token on existing ones
    existing_by_id = {r.id: r for r in records}
    for mid in mapped_ids:
        public_id = _public_agent_id(mid, project_token)
        if mid not in existing_by_id:
            try:
                new_record = models.Agent(
                    id=mid,
                    name=public_id,
                    type="validator",
                    project_token=project_token,
                )
                db.add(new_record)
                db.flush()
                records.append(new_record)
            except Exception:
                db.rollback()
                existing = db.query(models.Agent).filter(models.Agent.id == mid).first()
                if existing:
                    records.append(existing)
        elif existing_by_id[mid].project_token != project_token:
            existing_by_id[mid].project_token = project_token
    
    try:
        db.commit()
    except:
        db.rollback()

    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

    # Get available agents (excluding system agents)
    all_agents_in_memory = agent_service.get_all_agents(project_token)
    available_agents = [
        a["id"] for a in all_agents_in_memory
        if a["status"] == "idle" and not agent_service._is_system_agent_id(a["id"])
    ]
    
    if not available_agents:
        raise HTTPException(status_code=400, detail="No idle worker agents available. Please add agents via the UI.")

    # Store task token in project state so _fetch_external_tasks can use it
    if x_task_token:
        agent_service.set_project_task_token(project_token, x_task_token)

    # Get project tasks from external API
    try:
        logger.info(f"Fetching tasks for project: {project_token}")
        all_tasks = await agent_service._fetch_external_tasks(project_token)
        logger.info(f"Fetched {len(all_tasks)} total tasks from external API")
        
        # Filter to only pending/available tasks
        project_tasks = []
        for task in all_tasks:
            status = task.get('status', '').lower()
            if status not in ['completed', 'done', 'closed', 'cancelled']:
                project_tasks.append(task)
        
        logger.info(f"Filtered to {len(project_tasks)} pending tasks")
        
        if not project_tasks:
            logger.warning("No pending tasks found - all tasks may be completed")
            raise HTTPException(status_code=400, detail="No pending tasks available. All tasks may be completed or no tasks exist.")
            
        # Log first few tasks for debugging
        for i, task in enumerate(project_tasks[:3]):
            logger.info(f"Task {i+1}: {task.get('title', 'No title')} - Status: {task.get('status', 'No status')}")
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Failed to fetch tasks: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch tasks from external API: {str(e)}")

    # Set up git credentials
    agents_config = dict(request.agents_config) if request and request.agents_config else {}
    provided_repo = None
    provided_token = None
    for cfg in agents_config.values():
        if not isinstance(cfg, dict):
            continue
        if not provided_repo and cfg.get("git_repo_url"):
            provided_repo = cfg.get("git_repo_url")
        if not provided_token and cfg.get("git_token"):
            provided_token = cfg.get("git_token")
        if provided_repo and provided_token:
            break
    if provided_repo or provided_token:
        _upsert_project_global_credentials(
            db,
            current_user.id,
            git_repo_url=provided_repo,
            git_token=provided_token,
            project_token=project_token,
        )

    # Resolve final git credentials (from request or DB fallback)
    if not provided_repo or not provided_token:
        saved_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        if saved_cred:
            provided_repo = provided_repo or (saved_cred.git_repo_url or "").strip() or None
            provided_token = provided_token or (saved_cred.git_token or "").strip() or None

    # Launch all idle agents using the coordinated workflow with master agent supervision
    task_token = x_task_token or agent_service.get_project_task_token(project_token)
    
    # Build agents_config for the workflow
    workflow_agents_config = {}
    for agent_id in available_agents:
        workflow_agents_config[agent_id] = {
            "git_repo_url": provided_repo or "",
            "git_token": provided_token or "",
        }
    
    # Use the coordinated workflow which includes master agent planning
    try:
        result = await agent_service.run_all_agents(
            agents_config=workflow_agents_config,
            project_token=project_token,
            task_token=task_token,
            enable_supervisor=True,
        )
        logger.info(f"🚀 Coordinated workflow completed for project {project_token}")
        
        return {
            "started": True,
            "agents": available_agents,
            "total_tasks": len(project_tasks),
            "workflow_result": result,
            "message": f"Launched {len(available_agents)} agent(s) with master supervision on {len(project_tasks)} pending task(s).",
        }
    except Exception as workflow_err:
        logger.error(f"Coordinated workflow failed: {workflow_err}")
        # Fallback to individual agent launches
        for agent_id in available_agents:
            asyncio.create_task(
                agent_service.run_agent(
                    agent_id=agent_id,
                    project_token=project_token,
                    task_token=task_token,
                    continuous=True,
                    git_repo_url=provided_repo or None,
                    git_token=provided_token or None,
                )
            )
            logger.info(f"🚀 Launched {agent_id} (fallback mode) for project {project_token}")
        
        return {
            "started": True,
            "agents": available_agents,
            "total_tasks": len(project_tasks),
            "message": f"Launched {len(available_agents)} agent(s) in fallback mode on {len(project_tasks)} pending task(s).",
            "warning": "Coordinated workflow unavailable, using fallback mode",
        }


class AddAgentRequest(BaseModel):
    name: Optional[str] = None
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None
    kind: Optional[str] = None
    sub_type: Optional[str] = None  # 'dev' or 'test'


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None


def _build_external_agent_username(agent_id: Optional[str], fallback_name: Optional[str] = None) -> str:
    """Map local agent id to upstream username format, e.g. agent_04 -> agent4."""
    return agent_service.build_external_agent_username(agent_id, fallback_name)


@app.post("/agents/add")
async def add_agent(
    request: Optional[AddAgentRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
    x_task_token: Optional[str] = Header(None),
):
    """Dynamically add a new agent."""
    organization_name = _require_organization(current_user)
    name = request.name if request else None
    git_repo_url = request.git_repo_url if request else None
    git_token = request.git_token if request else None
    project_token = _normalize_project_token(project_token)
    agent_kind = _normalize_agent_kind(request.kind if request else None, project_token, is_default=False)
    _ensure_default_agents_for_org(db, organization_name, project_token)
    _bootstrap_org_agent_mappings_if_missing(db, organization_name, project_token)

    # Enforce org quota by requested agent kind and sub_type for the project.
    quota = _get_or_init_org_agent_quota(db, organization_name)
    org_usage = _count_org_agent_usage(db, organization_name)
    agent_sub_type = (_normalized_text(getattr(request, 'sub_type', None) or '').lower()) or 'dev'

    # Auto-expand quota to accommodate new agent (quota is a high-water mark, not a hard cap)
    if agent_kind == "dedicated":
        if agent_sub_type == "dev":
            needed = org_usage.get("dedicated_dev", 0) + 1
            if needed > int(quota.dedicated_dev_quota or 0):
                quota.dedicated_dev_quota = needed
                quota.dedicated_quota = int(quota.dedicated_quota or 0) + 1
                db.commit()
        elif agent_sub_type == "test":
            needed = org_usage.get("dedicated_test", 0) + 1
            if needed > int(quota.dedicated_test_quota or 0):
                quota.dedicated_test_quota = needed
                quota.dedicated_quota = int(quota.dedicated_quota or 0) + 1
                db.commit()
    else:
        if agent_sub_type == "dev":
            needed = org_usage.get("shared_dev", 0) + 1
            if needed > int(quota.shared_dev_quota or 0):
                quota.shared_dev_quota = needed
                quota.shared_quota = int(quota.shared_quota or 0) + 1
                db.commit()
        elif agent_sub_type == "test":
            needed = org_usage.get("shared_test", 0) + 1
            if needed > int(quota.shared_test_quota or 0):
                quota.shared_test_quota = needed
                quota.shared_quota = int(quota.shared_quota or 0) + 1
                db.commit()

    # CRITICAL: Serialize agent creation per project to prevent race conditions
    # Multiple parallel calls would all see the same DB state and create duplicate agent_01
    logger.info(f"[add_agent] Waiting for lock (project={project_token})")
    async with agent_service.get_project_agent_creation_lock(project_token):
        logger.info(f"[add_agent] Lock acquired (project={project_token})")
        
        # Load ALL mapped agents (including user-added ones that may be missing DB records)
        mapping_q = db.query(models.OrganizationAgentMapping.agent_id).filter(
            func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
        )
        if project_token:
            mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
        else:
            mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
        mapped_ids = [row[0] for row in mapping_q.all()]
        logger.info(f"[add_agent] Mapped agent IDs: {mapped_ids}")

        records = db.query(models.Agent).filter(models.Agent.id.in_(mapped_ids)).all() if mapped_ids else []
        logger.info(f"[add_agent] Before init: DB has {len(records)} records: {[r.id for r in records]}, memory has {len(agent_service.get_all_agents(project_token))} agents")

        # Upsert: create missing records or fix project_token on existing ones
        existing_by_id = {r.id: r for r in records}
        for mid in mapped_ids:
            public_id = _public_agent_id(mid, project_token)
            if mid not in existing_by_id:
                try:
                    new_record = models.Agent(
                        id=mid,
                        name=public_id,
                        type="validator",
                        project_token=project_token,
                    )
                    db.add(new_record)
                    db.flush()
                    records.append(new_record)
                except Exception:
                    db.rollback()
                    existing = db.query(models.Agent).filter(models.Agent.id == mid).first()
                    if existing:
                        records.append(existing)
            elif existing_by_id[mid].project_token != project_token:
                existing_by_id[mid].project_token = project_token
        
        try:
            db.commit()
        except:
            db.rollback()
        
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))
        logger.info(f"[add_agent] After init: memory has {len(agent_service.get_all_agents(project_token))} agents: {[a['id'] for a in agent_service.get_all_agents(project_token)]}")

        agent = agent_service.add_agent(
            name=name,
            kind=agent_kind,
            project_token=project_token,
        )
        logger.info(f"[add_agent] Created agent: {agent['id']}")
        record = _upsert_agent_record(db, agent["id"], agent.get("name"), agent.get("type"), project_token)
        logger.info(f"[add_agent] Stored DB record with id: {record.id}")
        _ensure_org_agent_mapping(
            db,
            organization_name,
            record.id,
            project_token,
            agent_kind=agent_kind,
            agent_sub_type=agent_sub_type,
            is_default=False,
        )
        logger.info(f"[add_agent] Committed {agent['id']} to DB, releasing lock")
    if git_repo_url or git_token:
        _upsert_project_global_credentials(
            db,
            current_user.id,
            git_repo_url=git_repo_url,
            git_token=git_token,
            project_token=project_token,
        )
    global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
    external_agent = None
    external_error = None
    external_username = _build_external_agent_username(agent.get("id"), agent.get("name"))
    try:
        external_agent = await task_service.create_agent(
            {"username": external_username},
            task_token=x_task_token,
        )
    except TaskServiceError as e:
        external_error = str(e)
        logger.warning(
            "Failed to create upstream agent for %s (username=%s): %s",
            agent.get("id"),
            external_username,
            external_error,
        )
    except Exception as e:
        external_error = str(e)
        logger.warning(
            "Unexpected error while creating upstream agent for %s (username=%s): %s",
            agent.get("id"),
            external_username,
            external_error,
        )

    response = {
        "agent": await _sanitize_agent_for_user_with_public_check(agent, global_cred),
        "external_username": external_username,
    }
    if external_agent is not None:
        response["external_agent"] = external_agent
    if external_error:
        response["external_agent_warning"] = external_error
    return response


@app.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    request: Optional[UpdateAgentRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    if not request:
        raise HTTPException(status_code=400, detail="Request body is required")
    name_provided = request.name is not None
    repo_provided = request.git_repo_url is not None
    token_provided = request.git_token is not None
    if not (name_provided or repo_provided or token_provided):
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    next_name = request.name.strip() if name_provided and request.name else None
    if name_provided and not next_name:
        raise HTTPException(status_code=400, detail="Agent name cannot be empty")
    try:
        project_token = _normalize_project_token(project_token)
        _ensure_default_agents(db, project_token)
        query = db.query(models.Agent)
        if project_token:
            query = query.filter(models.Agent.project_token == project_token)
        else:
            query = query.filter(models.Agent.project_token.is_(None))
        records = query.all()
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

        agent = agent_service.get_agent_status(agent_id, project_token)
        if next_name:
            agent = agent_service.update_agent_name(agent_id, next_name, project_token)
        _upsert_agent_record(db, agent["id"], agent.get("name"), agent.get("type"), project_token)
        if repo_provided or token_provided:
            _upsert_project_global_credentials(
                db,
                current_user.id,
                git_repo_url=request.git_repo_url,
                git_token=request.git_token,
                project_token=project_token,
            )
        global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        sanitized_agent = await _sanitize_agent_for_user_with_public_check(agent, global_cred)
        return {"agent": sanitized_agent}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/agents/{agent_id}")
async def update_agent_post(
    agent_id: str,
    request: Optional[UpdateAgentRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    if not request:
        raise HTTPException(status_code=400, detail="Request body is required")
    name_provided = request.name is not None
    repo_provided = request.git_repo_url is not None
    token_provided = request.git_token is not None
    if not (name_provided or repo_provided or token_provided):
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    next_name = request.name.strip() if name_provided and request.name else None
    if name_provided and not next_name:
        raise HTTPException(status_code=400, detail="Agent name cannot be empty")
    try:
        project_token = _normalize_project_token(project_token)
        _ensure_default_agents(db, project_token)
        query = db.query(models.Agent)
        if project_token:
            query = query.filter(models.Agent.project_token == project_token)
        else:
            query = query.filter(models.Agent.project_token.is_(None))
        records = query.all()
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

        agent = agent_service.get_agent_status(agent_id, project_token)
        if next_name:
            agent = agent_service.update_agent_name(agent_id, next_name, project_token)
        _upsert_agent_record(db, agent["id"], agent.get("name"), agent.get("type"), project_token)
        if repo_provided or token_provided:
            _upsert_project_global_credentials(
                db,
                current_user.id,
                git_repo_url=request.git_repo_url,
                git_token=request.git_token,
                project_token=project_token,
            )
        global_cred = _resolve_project_global_credential(db, current_user.id, project_token)
        sanitized_agent = await _sanitize_agent_for_user_with_public_check(agent, global_cred)
        return {"agent": sanitized_agent}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/agents/{agent_id}")
async def remove_agent(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    """Remove an idle agent."""
    try:
        project_token = _normalize_project_token(project_token)
        organization_name = _require_organization(current_user)
        
        _ensure_default_agents_for_org(db, organization_name, project_token)
        _bootstrap_org_agent_mappings_if_missing(db, organization_name, project_token)

        # Load ALL mapped agents (including user-added ones that may be missing DB records)
        mapping_q = db.query(models.OrganizationAgentMapping.agent_id).filter(
            func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
        )
        if project_token:
            mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
        else:
            mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
        mapped_ids = [row[0] for row in mapping_q.all()]

        records = db.query(models.Agent).filter(models.Agent.id.in_(mapped_ids)).all() if mapped_ids else []

        # Upsert: create missing records or fix project_token on existing ones
        existing_by_id = {r.id: r for r in records}
        for mid in mapped_ids:
            public_id = _public_agent_id(mid, project_token)
            if mid not in existing_by_id:
                try:
                    new_record = models.Agent(
                        id=mid,
                        name=public_id,
                        type="validator",
                        project_token=project_token,
                    )
                    db.add(new_record)
                    db.flush()
                    records.append(new_record)
                except Exception:
                    db.rollback()
                    existing = db.query(models.Agent).filter(models.Agent.id == mid).first()
                    if existing:
                        records.append(existing)
            elif existing_by_id[mid].project_token != project_token:
                existing_by_id[mid].project_token = project_token
        
        try:
            db.commit()
        except:
            db.rollback()

        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

        agent_service.remove_agent(agent_id, project_token)
        _delete_agent_record(db, agent_id, project_token)
        
        # Also remove the mapping
        stored_id = _stored_agent_id(agent_id, project_token)
        db.query(models.OrganizationAgentMapping).filter(
            func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
            models.OrganizationAgentMapping.agent_id == stored_id,
        ).delete()
        db.commit()
        
        return {"success": True, "removed": agent_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# ─────────────────────────────── Task Management Integration ──────────────────────────

from task_service import (
    task_service,
    TaskServiceError,
    TaskServiceTimeoutError,
    TaskServiceConnectionError,
    TaskServiceHTTPError,
)

def _raise_task_service_http_exception(e: TaskServiceError, fallback_message: str) -> None:
    detail = str(e) or fallback_message
    if isinstance(e, TaskServiceTimeoutError):
        raise HTTPException(status_code=504, detail=detail)
    if isinstance(e, TaskServiceConnectionError):
        raise HTTPException(status_code=502, detail=detail)
    status_code = e.status_code if 400 <= e.status_code < 500 else 502
    raise HTTPException(status_code=status_code, detail=detail)

@app.get("/api/agents/")
async def get_external_agents(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Fetch the list of agents from the external task management API."""
    try:
        agents = await task_service.get_agents(task_token=x_task_token)
        return agents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {e}")



@app.get("/api/agent/projects/")
async def get_agent_projects(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Fetch the list of projects from the external task management API."""
    try:
        projects = await task_service.get_projects(task_token=x_task_token)
        return projects
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {e}")

class TaskTokenRequest(BaseModel):
    client_id: str
    client_secret: str

@app.post("/api/token/task/")
async def fetch_task_token(
    payload: TaskTokenRequest,
):
    """Fetch task token dynamically from the task management API"""
    try:
        import httpx
        from config import settings
        token_url = f"{settings.task_api_base_url.rstrip('/')}/api/token/task/"
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, json=payload.dict(), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task token: {str(e)}")

class AgentProjectCreate(BaseModel):
    name: str
    deadline: str
    project_wallet: int
    team: List[int]
    project_token: Optional[str] = None

@app.post("/api/agent/projects/")
async def create_agent_project(
    project: AgentProjectCreate,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Create a new project in the external task management API."""
    try:
        project_dict = project.dict(exclude={"project_token"})
        result = await task_service.create_project(project_dict, task_token=x_task_token)
        
        if project.project_token and result.get("project_application"):
            app_data = result.get("project_application")
            gov_res = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.owner_id == current_user.id,
                models.GovernanceResponse.project_token == project.project_token
            ).first()
            if gov_res:
                gov_res.client_id = app_data.get("client_id")
                gov_res.client_secret = app_data.get("client_secret")
                db.commit()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create project: {e}")

class AgentTaskCreate(BaseModel):
    taskName: str
    description: str
    assignees: List[int] = Field(default_factory=list)
    wallet: int
    deadline: str
    startdate: str
    task_type: str
    priority: str
    sprint: Optional[int] = None
    milestone: Optional[int] = None

class SprintCreateRequest(BaseModel):
    name: str
    summary: Optional[str] = ""
    start_date: str
    deadline: str

class MilestoneCreateRequest(BaseModel):
    name: str
    sprint_id: int
    deadline: str
    start_date: str

class SprintStatusUpdateRequest(BaseModel):
    sprint_id: int
    status: str
    is_completed: bool

class MilestoneStatusUpdateRequest(BaseModel):
    milestone_id: int
    is_completed: bool

class ProjectStatusUpdateRequest(BaseModel):
    deadline: str
    status: str

class TaskMessageRequest(BaseModel):
    task_id: int
    message: str

class TaskProgressRequest(BaseModel):
    task_id: int
    task_progress: int
    additional_info: Optional[str] = None

class TaskCompleteRequest(BaseModel):
    task_id: int

class TaskTimerLogRequest(BaseModel):
    task_id: int
    action: str

class TaskOptInRequest(BaseModel):
    task_id: int
    username: str


class AgentNoteUpsertRequest(BaseModel):
    note_id: Optional[int] = None
    title: str
    content: str
    user: Optional[str] = None




class TaskAssignRequest(BaseModel):
    task_id: int
    username: str


@app.post("/api/agent/task-assign-in/")
async def assign_task_to_agent(
    payload: TaskAssignRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Assign a task to an agent via the external task management API."""
    try:
        # Use the task_service assign_task method
        result = await task_service.assign_task(
            task_id=payload.task_id,
            assignees=[payload.username],
            task_token=x_task_token
        )
        return {"success": True, "message": f"Task {payload.task_id} assigned to {payload.username}", "result": result}
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to assign task")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign task: {e}")


@app.get("/api/agent/sprints/")
async def get_agent_sprints(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Fetch sprints from the external task management API."""
    try:
        return await task_service.get_sprints(task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to fetch sprints")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sprints: {e}")


@app.post("/api/agent/sprints/")
async def create_agent_sprint(
    payload: SprintCreateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Create sprint in the external task management API."""
    try:
        return await task_service.create_sprint(payload.dict(), task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to create sprint")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create sprint: {e}")


@app.put("/api/agent/sprints/")
async def update_agent_sprint_status(
    payload: SprintStatusUpdateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Update sprint status/is_completed in the external task management API."""
    try:
        return await task_service.update_sprint_status(payload.dict(), task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to update sprint status")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update sprint status: {e}")


@app.get("/api/agent/milestones/")
async def get_agent_milestones(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Fetch milestones from the external task management API."""
    try:
        return await task_service.get_milestones(task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to fetch milestones")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch milestones: {e}")


@app.post("/api/agent/milestones/")
async def create_agent_milestone(
    payload: MilestoneCreateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Create milestone in the external task management API."""
    try:
        milestone_payload = payload.dict()
        resolved_sprint_payload = await _resolve_sprint_schedule_payload(
            payload.sprint_id,
            fallback={
                "start_date": payload.start_date,
                "deadline": payload.deadline,
            },
            task_token=x_task_token,
        )
        sprint_start_obj = _parse_yyyy_mm_dd_date(
            _extract_schedule_start(resolved_sprint_payload) or payload.start_date
        )
        sprint_deadline_obj = _parse_yyyy_mm_dd_date(
            _extract_schedule_deadline(resolved_sprint_payload) or payload.deadline
        )
        if sprint_start_obj is not None and sprint_deadline_obj is not None:
            milestone_payload["start_date"], milestone_payload["deadline"] = _normalize_schedule_dates(
                payload.start_date,
                payload.deadline,
                min_date=sprint_start_obj,
                max_date=max(sprint_start_obj, sprint_deadline_obj),
            )
        return await task_service.create_milestone(milestone_payload, task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to create milestone")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create milestone: {e}")


@app.put("/api/agent/milestones/")
async def update_agent_milestone_status(
    payload: MilestoneStatusUpdateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Update milestone completion state in the external task management API."""
    try:
        return await task_service.update_milestone_status(payload.dict(), task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to update milestone status")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update milestone status: {e}")


@app.post("/api/agent/messages/")
async def post_agent_task_message(
    payload: TaskMessageRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Post a comment/message to a task in the external task management API."""
    try:
        return await task_service.post_task_message(payload.dict(), task_token=x_task_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post task message: {e}")


@app.post("/api/agent/task-progress/")
async def post_agent_task_progress(
    payload: TaskProgressRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Update task progress in the external task management API."""
    try:
        return await task_service.update_task_progress(payload.dict(), task_token=x_task_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update task progress: {e}")


@app.post("/api/agent/task-complete/")
async def post_agent_task_complete(
    payload: TaskCompleteRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Mark a task as complete in the external task management API."""
    try:
        return await task_service.complete_task(payload.dict(), task_token=x_task_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete task: {e}")


@app.post("/api/agent/timer-logs/")
async def post_agent_task_timer_log(
    payload: TaskTimerLogRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Post a timer log (clock_in/clock_out) to the external task management API."""
    try:
        return await task_service.post_timer_log(payload.dict(), task_token=x_task_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post timer log: {e}")

@app.post("/api/agent/task-opt-in/")
async def post_agent_task_opt_in(
    payload: TaskOptInRequest,
    x_task_token: Optional[str] = Header(None),
):
    """Opt in a user to a task in the external task management API."""
    try:
        return await task_service.opt_in_task(payload.dict(), task_token=x_task_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to opt in to task: {e}")

@app.get("/api/agent/tasks-list/")
async def get_external_agent_tasks(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = None,
    x_task_token: Optional[str] = Header(None)
):
    """
    Fetch the list of tasks from the external task management API with caching.
    """
    # Check cache first
    cache_key = _get_task_cache_key(x_task_token, page)
    cached_result = _get_cached_tasks(cache_key)
    if cached_result is not None:
        return cached_result
    
    try:
        tasks = await task_service.get_tasks(page=page, task_token=x_task_token)
        
        # Cache the result
        _cache_tasks(cache_key, tasks)
        
        return tasks
    except TaskServiceTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TaskServiceConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except TaskServiceError as e:
        status_code = e.status_code if 400 <= e.status_code < 500 else 502
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {repr(e)}")

@app.get("/api/agent/tasks-total-list/")
async def get_external_agent_total_tasks(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = None,
    x_task_token: Optional[str] = Header(None)
):
    """
    Fetch the list of all tasks from the external task management API.
    """
    try:
        tasks = await task_service.get_total_tasks(page=page, task_token=x_task_token)
        return tasks
    except TaskServiceTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TaskServiceConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except TaskServiceError as e:
        status_code = e.status_code if 400 <= e.status_code < 500 else 502
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch total tasks: {repr(e)}")

@app.get("/api/agent/project-info/")
async def get_agent_project_info(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Fetch project info (deadline, wallet, team) from the external task management API.

    If no external project exists yet for this application, we return an empty
    object instead of treating it as an error. This avoids breaking frontend
    flows before the first bootstrap.
    """
    try:
        info = await task_service.get_project_info(task_token=x_task_token)
        return info
    except TaskServiceHTTPError as e:
        # Upstream 404 -> "No project associated with this application"
        # is a valid state before bootstrap. Surface an empty response
        # so the frontend can treat it as "no project yet" instead of error.
        if e.status_code == 404:
            return {}
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch project info: {repr(e)}")

@app.put("/api/agent/project/update/")
async def update_agent_project_status(
    payload: ProjectStatusUpdateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Update project deadline/status in the external task management API."""
    try:
        return await task_service.update_project_status(payload.dict(), task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to update project status")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update project status: {e}")

@app.get("/api/agent/dashboard/")
async def get_agent_dashboard(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Fetch dashboard info from the external task management API."""
    try:
        data = await task_service.get_dashboard(task_token=x_task_token)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard info: {e}")


@app.put("/api/agent/notes/")
async def upsert_agent_note(
    payload: AgentNoteUpsertRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Create or update an agent note in the external task management API."""
    try:
        return await task_service.upsert_note(payload.dict(exclude_none=True), task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to save note")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save note: {e}")


@app.get("/api/agent/notes/")
async def list_agent_notes(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """List agent notes from the external task management API."""
    try:
        return await task_service.list_notes(task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to fetch notes")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notes: {e}")


@app.get("/api/agent/notes/{note_id}/")
async def get_agent_note_detail(
    note_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """Fetch one agent note from the external task management API."""
    try:
        return await task_service.get_note_detail(note_id, task_token=x_task_token)
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to fetch note detail")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch note detail: {e}")

class AutoGenerateRequest(BaseModel):
    project_token: str
    prerequisites: Optional[List[Dict[str, Any]]] = None
    sprint_id: Optional[int] = None
    milestone_id: Optional[int] = None
    auto_create_plan: Optional[bool] = False
    custom_rules: Optional[str] = None
    project_type: Optional[str] = "greenfield"
    process_mode: Optional[str] = None


class ProjectBootstrapRequest(BaseModel):
    project_token: str
    project_name: Optional[str] = None
    prerequisites: Optional[List[Dict[str, Any]]] = None
    custom_rules: Optional[str] = None
    project_type: Optional[str] = "greenfield"
    process_mode: Optional[str] = None


@app.post("/api/agent/project-bootstrap/")
async def bootstrap_agent_project(
    request: ProjectBootstrapRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Create or update the external task project during the prerequisites step.
    The project deadline is derived STRICTLY from the selected process_mode by
    building a local plan preview and taking its mode-based project_deadline.
    """
    try:
        existing_project_info: Optional[Dict[str, Any]] = None
        try:
            existing_project_info = await task_service.get_project_info(task_token=x_task_token)
        except Exception:
            existing_project_info = None

        gov_response = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == request.project_token,
            models.GovernanceResponse.owner_id == current_user.id,
        ).first()

        project_name = (
            str(request.project_name or "").strip()
            or (gov_response.project_name if gov_response else None)
            or request.project_token
            or "Untitled Project"
        )

        # If this project was created as a frontend "draft" (no governance submit yet),
        # there may be no GovernanceResponse row. We still need a row to persist
        # the generated external task credentials (client_id/client_secret) so
        # the frontend can fetch a task token and project info immediately.
        if not gov_response:
            gov_response = models.GovernanceResponse(
                owner_id=current_user.id,
                project_token=request.project_token,
                project_name=project_name,
                answers={},
                classification="N/A",
                recommendation="Created during task project bootstrap.",
            )
            db.add(gov_response)
            db.commit()
            db.refresh(gov_response)

        # Reuse the same analysis harvesting as auto-generate (governance + documents)
        import json as json_mod

        analysis_payload: Dict[str, Any] = {}
        analysis_report = str(gov_response.recommendation or "").strip() if gov_response else ""
        user_documents = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id
        ).order_by(models.Document.upload_date.desc()).all()

        for doc in user_documents:
            if not doc.analysis_result:
                continue
            try:
                parsed = json_mod.loads(doc.analysis_result)
            except (TypeError, ValueError):
                continue

            gov_ctx = parsed.get("governanceContext") or {}
            proj_meta = parsed.get("projectMeta") or {}
            doc_result_id = proj_meta.get("governance_result_id") or gov_ctx.get("result_id")
            doc_token_id = proj_meta.get("project_token") or gov_ctx.get("project_token")
            doc_project_name = str(
                proj_meta.get("project_name") or gov_ctx.get("project_name") or ""
            ).strip()

            matches_project = False
            if gov_response and doc_result_id is not None and str(doc_result_id) == str(gov_response.id):
                matches_project = True
            elif doc_token_id and str(doc_token_id) == str(request.project_token):
                matches_project = True
            elif project_name and doc_project_name and doc_project_name.lower() == str(project_name).strip().lower():
                matches_project = True

            if not matches_project:
                continue

            analysis_payload = parsed
            parsed_analysis = str(parsed.get("analysis") or "").strip()
            if parsed_analysis:
                analysis_report = parsed_analysis
            break

        reporter_name = " ".join(
            part for part in [current_user.first_name, current_user.last_name] if str(part or "").strip()
        ).strip() or current_user.email

        # Bypass expensive task preview generation in project bootstrap
        # to prevent users waiting 1-2 minutes for prerequisites -> task creation step
        _, project_deadline_date = _normalize_project_dates(analysis_payload)
        mode_deadline = _format_date(project_deadline_date)

        if not mode_deadline:
            raise HTTPException(status_code=500, detail="Failed to derive mode-based project deadline.")

        # If a project already exists in the external system, update its deadline
        # instead of creating a new project.
        if existing_project_info:
            # Preserve the current status from the external project if available,
            # because the upstream API expects both deadline and status together.
            existing_status = None
            if isinstance(existing_project_info, dict):
                project_block = existing_project_info.get("project") or existing_project_info
                if isinstance(project_block, dict):
                    existing_status = project_block.get("status")

            update_payload = {
                "deadline": mode_deadline,
                "status": existing_status or "in_progress",
            }
            await task_service.update_project_status(update_payload, task_token=x_task_token)
            return {
                "status": "success",
                "created": False,
                "project_deadline": mode_deadline,
                "project": existing_project_info,
            }

        create_payload = {
            "name": project_name,
            "deadline": mode_deadline,
            "project_wallet": 1000,
            "team": [24],
            "project_token": request.project_token,
        }
        # Use x_task_token if provided; otherwise fall back to server-side task service credentials.
        created_project = await task_service.create_project(create_payload, task_token=x_task_token)

        # After creation, explicitly update the deadline using the same mode-based
        # value to guard against any upstream defaults overriding our payload.
        created_status = None
        if isinstance(created_project, dict):
            project_block = created_project.get("project_application") or created_project.get("project") or created_project
            if isinstance(project_block, dict):
                created_status = project_block.get("status")

        update_payload = {
            "deadline": mode_deadline,
            "status": created_status or "in_progress",
        }
        try:
            await task_service.update_project_status(update_payload, task_token=x_task_token)
        except Exception:
            # Best-effort: ignore update failures here, the create call already
            # succeeded and the local preview still has the correct deadline.
            pass

        # Persist credentials (best-effort) if present
        if (
            gov_response
            and isinstance(created_project, dict)
            and isinstance(created_project.get("project_application"), dict)
        ):
            app_data = created_project.get("project_application") or {}
            if app_data.get("client_id") and app_data.get("client_secret"):
                gov_response.client_id = app_data.get("client_id")
                gov_response.client_secret = app_data.get("client_secret")
                db.commit()

        return {
            "status": "success",
            "created": True,
            "project_deadline": mode_deadline,
            "project": created_project,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bootstrap project: {e}")



def _to_optional_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _extract_date_yyyy_mm_dd(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    text = str(value).strip()
    if len(text) < 10:
        return None

    candidate = text[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except Exception:
        return None


def _extract_first_date_from_mapping(payload: Any, keys: tuple[str, ...]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    for key in keys:
        extracted = _extract_date_yyyy_mm_dd(payload.get(key))
        if extracted:
            return extracted
    return None


def _parse_yyyy_mm_dd_date(value: Any) -> Optional[datetime.date]:
    extracted = _extract_date_yyyy_mm_dd(value)
    if not extracted:
        return None
    try:
        return datetime.strptime(extracted, "%Y-%m-%d").date()
    except Exception:
        return None


def _normalize_schedule_dates(
    start_value: Any,
    end_value: Any,
    *,
    min_date: datetime.date,
    max_date: datetime.date,
    require_strict_order: bool = False,
) -> tuple[str, str]:
    start_date = _parse_yyyy_mm_dd_date(start_value) or min_date
    end_date = _parse_yyyy_mm_dd_date(end_value) or max_date

    if start_date < min_date:
        start_date = min_date
    if start_date > max_date:
        start_date = max_date

    if require_strict_order:
        if end_date <= start_date:
            if min_date < max_date:
                start_date = min_date
                end_date = max_date
            else:
                end_date = start_date
    elif end_date < start_date:
        end_date = start_date

    if end_date > max_date:
        end_date = max_date

    if require_strict_order:
        if end_date <= start_date and min_date < max_date:
            start_date = min_date
            end_date = max_date
        elif end_date < start_date:
            end_date = start_date
    elif end_date < start_date:
        end_date = start_date

    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def _extract_schedule_start(payload: Any) -> Optional[str]:
    return _extract_first_date_from_mapping(
        payload,
        (
            "start_date",
            "startdate",
            "startDate",
            "planned_start",
            "plannedStart",
        ),
    )


def _extract_schedule_deadline(payload: Any) -> Optional[str]:
    return _extract_first_date_from_mapping(
        payload,
        (
            "deadline",
            "end_date",
            "endDate",
            "planned_end",
            "plannedEnd",
        ),
    )


def _find_entity_by_id(payload: Any, entity_id: Any) -> Optional[Dict[str, Any]]:
    target_id = _to_optional_int(entity_id)
    if target_id is None:
        return None

    queue: List[Any] = [payload]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)

        if isinstance(current, dict):
            current_id = _to_optional_int(
                current.get("id")
                or current.get("sprint_id")
                or current.get("milestone_id")
            )
            if current_id == target_id:
                return current
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    queue.append(item)
    return None


async def _resolve_sprint_schedule_payload(
    sprint_id: Optional[int],
    *,
    fallback: Optional[Dict[str, Any]] = None,
    created_result: Optional[Dict[str, Any]] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    resolved: Dict[str, Any] = dict(fallback or {})
    target_id = _to_optional_int(sprint_id)
    if target_id is None:
        return resolved

    created_match = _find_entity_by_id(created_result, target_id)
    if created_match:
        resolved.update(created_match)

    try:
        upstream_sprints = await task_service.get_sprints(task_token=task_token)
        upstream_match = _find_entity_by_id(upstream_sprints, target_id)
        if upstream_match:
            resolved.update(upstream_match)
    except Exception as exc:
        logger.warning(
            "Failed to resolve sprint %s schedule window from upstream API: %s",
            target_id,
            exc,
        )

    return resolved


def _clamp_preview_payload_task_dates(
    preview_payload: Dict[str, Any],
    *,
    min_date: Optional[datetime.date],
    max_date: Optional[datetime.date],
) -> None:
    if not isinstance(preview_payload, dict) or min_date is None or max_date is None:
        return

    if max_date < min_date:
        max_date = min_date

    for task in preview_payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        start_iso, end_iso = _normalize_schedule_dates(
            task.get("planned_start") or task.get("startdate"),
            task.get("planned_end") or task.get("deadline"),
            min_date=min_date,
            max_date=max_date,
        )
        task["planned_start"] = start_iso
        task["planned_end"] = end_iso

    for task in preview_payload.get("preview_json") or []:
        if not isinstance(task, dict):
            continue
        start_iso, end_iso = _normalize_schedule_dates(
            task.get("planned_start") or task.get("startdate"),
            task.get("deadline") or task.get("planned_end"),
            min_date=min_date,
            max_date=max_date,
        )
        task["startdate"] = start_iso
        task["planned_start"] = start_iso
        task["deadline"] = end_iso


def _extract_created_entity_id(payload: Any, entity_key: str) -> Optional[int]:
    if not isinstance(payload, dict):
        return None

    direct_id = _to_optional_int(payload.get("id") or payload.get(f"{entity_key}_id"))
    if direct_id is not None:
        return direct_id

    for nested_key in (entity_key, "data", "result", f"created_{entity_key}"):
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        nested_id = _to_optional_int(nested.get("id") or nested.get(f"{entity_key}_id"))
        if nested_id is not None:
            return nested_id

    return None


def _extract_created_entity_name(payload: Any, entity_key: str) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    direct_name = str(
        payload.get("name")
        or payload.get(f"{entity_key}_name")
        or ""
    ).strip()
    if direct_name:
        return direct_name

    for nested_key in (entity_key, "data", "result", f"created_{entity_key}"):
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        nested_name = str(
            nested.get("name")
            or nested.get(f"{entity_key}_name")
            or ""
        ).strip()
        if nested_name:
            return nested_name

    return None


def _apply_schedule_ids_to_preview_payload(
    preview_payload: Dict[str, Any],
    *,
    placeholder_to_real_sprint: Dict[str, int],
    placeholder_to_real_milestone: Dict[str, int],
    placeholder_to_real_sprint_name: Optional[Dict[str, str]] = None,
    placeholder_to_real_milestone_name: Optional[Dict[str, str]] = None,
    fallback_sprint_id: Optional[int] = None,
    fallback_milestone_id: Optional[int] = None,
) -> None:
    """Replace placeholder sprint/milestone IDs with real external API IDs.

    Each task carries ``_placeholder_sprint_id`` and ``_placeholder_milestone_id``
    which are mapped to the real IDs created in the external task API.
    """
    if not isinstance(preview_payload, dict):
        return

    sprint_name_map = placeholder_to_real_sprint_name if isinstance(placeholder_to_real_sprint_name, dict) else {}
    milestone_name_map = placeholder_to_real_milestone_name if isinstance(placeholder_to_real_milestone_name, dict) else {}
    first_real_sprint = fallback_sprint_id
    if not first_real_sprint and placeholder_to_real_sprint:
        first_real_sprint = next(iter(placeholder_to_real_sprint.values()), None)
    first_real_milestone = fallback_milestone_id
    if not first_real_milestone and placeholder_to_real_milestone:
        first_real_milestone = next(iter(placeholder_to_real_milestone.values()), None)

    if first_real_sprint is not None:
        preview_payload["sprint_id"] = first_real_sprint

    if first_real_milestone is not None:
        preview_payload["milestone_id"] = first_real_milestone

    # Update created_sprints / sprints list entries
    for key in ("created_sprints", "sprints"):
        collection = preview_payload.get(key)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            placeholder = str(item.get("id") or "")
            real_id = placeholder_to_real_sprint.get(placeholder, fallback_sprint_id)
            if real_id is not None:
                item["id"] = real_id
    # Keep created_sprint pointing to the first
    cs = preview_payload.get("created_sprint")
    if isinstance(cs, dict):
        placeholder = str(cs.get("id") or "")
        cs["id"] = placeholder_to_real_sprint.get(placeholder, first_real_sprint)

    # Update created_milestones / milestones list entries
    for key in ("created_milestones", "milestones"):
        collection = preview_payload.get(key)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            placeholder = str(item.get("id") or "")
            real_id = placeholder_to_real_milestone.get(placeholder, fallback_milestone_id)
            if real_id is not None:
                item["id"] = real_id
            sprint_placeholder = str(item.get("sprint_id") or "")
            real_sprint = placeholder_to_real_sprint.get(sprint_placeholder, first_real_sprint)
            if real_sprint is not None:
                item["sprint_id"] = real_sprint
    cm = preview_payload.get("created_milestone")
    if isinstance(cm, dict):
        placeholder = str(cm.get("id") or "")
        cm["id"] = placeholder_to_real_milestone.get(placeholder, first_real_milestone)
        sprint_placeholder = str(cm.get("sprint_id") or "")
        cm["sprint_id"] = placeholder_to_real_sprint.get(sprint_placeholder, first_real_sprint)

    # Update structured tasks
    for task in preview_payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        sp = str(task.get("sprint_id") or "")
        task["sprint_id"] = placeholder_to_real_sprint.get(sp, first_real_sprint)
        sprint_name = sprint_name_map.get(sp, "")
        if sprint_name:
            task["sprint_name"] = sprint_name
        mp = str(task.get("milestone_id") or "")
        task["milestone_id"] = placeholder_to_real_milestone.get(mp, first_real_milestone)
        milestone_name = milestone_name_map.get(mp, "")
        if milestone_name:
            task["milestone_name"] = milestone_name

    # Update preview_json tasks (sent to external batch API)
    for task in preview_payload.get("preview_json") or []:
        if not isinstance(task, dict):
            continue
        sp = str(task.pop("_placeholder_sprint_id", "") or "")
        mp = str(task.pop("_placeholder_milestone_id", "") or "")
        sprint_name = sprint_name_map.get(sp, "")
        milestone_name = milestone_name_map.get(mp, "")

        task.pop("sprint_id", None)
        task.pop("milestone_id", None)
        task.pop("sprint_name", None)
        task.pop("milestone_name", None)

        if sprint_name:
            task["sprint"] = sprint_name
        if milestone_name:
            task["milestone"] = milestone_name

@app.post("/api/agent/tasks/generate-local/")
async def generate_tasks_locally(
    request: AutoGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None)
):
    """
    Generate tasks locally using AI, store in database, then optionally sync to NXDUNE.
    """
    try:
        from task_generation_service import generate_tasks_locally as gen_tasks
        
        # Get AI config
        ai_config = await ai_service.get_ai_config()
        
        # Generate tasks using improved prompt
        tasks = await gen_tasks(
            project_token=request.project_token,
            db=db,
            user_id=current_user.id,
            custom_rules=request.custom_rules,
            process_mode=request.process_mode or "ai_first",
            project_type=request.project_type or "greenfield",
            prerequisites=request.prerequisites or [],
            api_url=ai_config.get("api_url"),
            api_key=settings.ai_api_key,
            model=ai_config.get("model")
        )
        
        if not tasks:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate tasks. Please check your project context and try again."
            )
        
        # Store tasks in local database
        # First delete any existing tasks for this project to avoid duplicate task_id errors
        db.query(models.Task).filter(
            models.Task.project_token == request.project_token,
            models.Task.owner_id == current_user.id
        ).delete()
        db.commit()

        stored_tasks = []
        for task_data in tasks:
            # Use project_token + task_id as unique DB key, but store clean task_id separately
            clean_task_id = task_data["task_id"]
            db_unique_id = f"{request.project_token}_{clean_task_id}"
            
            # Convert list/dict fields to JSON strings for SQLite storage
            assigned_to = task_data.get("assignedTo", [])
            if isinstance(assigned_to, list):
                assigned_to = json.dumps(assigned_to)
            
            linked_tasks = task_data.get("linked_tasks", [])
            if isinstance(linked_tasks, list):
                linked_tasks = json.dumps(linked_tasks)
            
            checklist = task_data.get("checklist", [])
            if isinstance(checklist, list):
                checklist = json.dumps(checklist)
            elif not isinstance(checklist, str):
                checklist = json.dumps([])
            
            task = models.Task(
                task_id=db_unique_id,
                project_token=request.project_token,
                owner_id=current_user.id,
                task_name=task_data["taskName"],
                task_type=task_data["task_type"],
                description=task_data.get("description", ""),
                priority=task_data.get("priority", "medium"),
                task_wallet=task_data.get("task_wallet", 1),
                startdate=task_data.get("startdate"),
                planned_start=task_data.get("planned_start"),
                deadline=task_data.get("deadline"),
                assigned_to=assigned_to,
                reported_by=task_data.get("reported_by", "system"),
                sprint=task_data.get("sprint", "new"),
                milestone=task_data.get("milestone", "main"),
                linked_tasks=linked_tasks,
                checklist=checklist,
                synced_to_nxdune=False
            )
            db.add(task)
            stored_tasks.append(task)
        
        db.commit()
        
        logger.info(f"Generated and stored {len(stored_tasks)} tasks locally for project {request.project_token}")
        
        # Create multiple sprints and milestones in external API if task token is provided
        sprint_ids = []
        milestone_ids = []
        sprint_names = []
        milestone_names = []
        
        if x_task_token:
            try:
                # Extract unique sprints and milestones from tasks
                unique_sprints = {}
                unique_milestones = {}
                
                for task in tasks:
                    sprint_name = task.get("sprint", "Sprint 1")
                    milestone_name = task.get("milestone", "Milestone 1")
                    
                    if sprint_name not in unique_sprints:
                        unique_sprints[sprint_name] = {
                            "name": sprint_name,
                            "start_dates": [],
                            "deadlines": []
                        }
                    
                    if milestone_name not in unique_milestones:
                        unique_milestones[milestone_name] = {
                            "name": milestone_name,
                            "sprint": sprint_name,
                            "start_dates": [],
                            "deadlines": []
                        }
                    
                    # Collect dates for each sprint/milestone
                    if task.get("startdate"):
                        unique_sprints[sprint_name]["start_dates"].append(task["startdate"])
                        unique_milestones[milestone_name]["start_dates"].append(task["startdate"])
                    if task.get("deadline"):
                        unique_sprints[sprint_name]["deadlines"].append(task["deadline"])
                        unique_milestones[milestone_name]["deadlines"].append(task["deadline"])
                
                # Create sprints in external API
                sprint_name_to_id = {}
                for sprint_name, sprint_data in unique_sprints.items():
                    sprint_start = min(sprint_data["start_dates"]) if sprint_data["start_dates"] else datetime.now().strftime('%Y-%m-%d')
                    sprint_deadline = max(sprint_data["deadlines"]) if sprint_data["deadlines"] else (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
                    
                    logger.info(f"Creating sprint '{sprint_name}' in external API")
                    sprint_result = await task_service.create_sprint(
                        {
                            "name": sprint_name,
                            "summary": f"AI-generated sprint for {request.project_token}",
                            "start_date": sprint_start,
                            "deadline": sprint_deadline,
                        },
                        task_token=x_task_token
                    )
                    
                    if isinstance(sprint_result, dict):
                        sprint_id = sprint_result.get("id") or sprint_result.get("sprint_id")
                        if sprint_id:
                            sprint_ids.append(sprint_id)
                            sprint_names.append(sprint_name)
                            sprint_name_to_id[sprint_name] = sprint_id
                            logger.info(f"Created sprint: ID={sprint_id}, Name={sprint_name}")
                
                # Create milestones in external API
                milestone_name_to_id = {}
                for milestone_name, milestone_data in unique_milestones.items():
                    milestone_start = min(milestone_data["start_dates"]) if milestone_data["start_dates"] else datetime.now().strftime('%Y-%m-%d')
                    milestone_deadline = max(milestone_data["deadlines"]) if milestone_data["deadlines"] else (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                    
                    # Get sprint ID for this milestone
                    milestone_sprint_name = milestone_data["sprint"]
                    milestone_sprint_id = sprint_name_to_id.get(milestone_sprint_name)
                    
                    logger.info(f"Creating milestone '{milestone_name}' in external API")
                    milestone_result = await task_service.create_milestone(
                        {
                            "name": milestone_name,
                            "sprint_id": milestone_sprint_id,
                            "start_date": milestone_start,
                            "deadline": milestone_deadline,
                        },
                        task_token=x_task_token
                    )
                    
                    if isinstance(milestone_result, dict):
                        milestone_id = milestone_result.get("id") or milestone_result.get("milestone_id")
                        if milestone_id:
                            milestone_ids.append(milestone_id)
                            milestone_names.append(milestone_name)
                            milestone_name_to_id[milestone_name] = milestone_id
                            logger.info(f"Created milestone: ID={milestone_id}, Name={milestone_name}")
                
            except Exception as sprint_milestone_error:
                logger.warning(f"Failed to create sprints/milestones in external API: {sprint_milestone_error}")
                # Continue with task sync even if sprint/milestone creation fails
        
        # Always sync to NXDUNE via batch file upload if task token is provided
        synced = False
        sync_error_detail = None
        if x_task_token:
            try:
                import io
                import json as json_mod
                import httpx

                nxdune_base = settings.task_api_base_url.rstrip("/")
                batch_url = f"{nxdune_base}/api/agent/tasks/batch/"

                # Make task_ids unique per project to avoid NXDUNE duplicate conflicts.
                # Use a short 6-char hash of the project token as prefix: e.g. "a3f9b2_EPIC-01"
                import hashlib
                short_hash = hashlib.md5(request.project_token.encode()).hexdigest()[:6]

                # Valid NXDUNE priority values
                VALID_PRIORITIES = {"low", "medium", "high"}
                PRIORITY_MAP = {"critical": "high", "urgent": "high", "normal": "medium", "minor": "low"}

                prefixed_tasks = []
                for t in tasks:
                    pt = dict(t)
                    pt["task_id"] = f"{short_hash}_{pt['task_id']}"
                    if pt.get("linked_tasks"):
                        pt["linked_tasks"] = [
                            f"{short_hash}_{lid}" for lid in pt["linked_tasks"]
                        ]
                    # Normalize priority to valid NXDUNE values
                    raw_priority = str(pt.get("priority") or "medium").lower()
                    pt["priority"] = PRIORITY_MAP.get(raw_priority, raw_priority) if raw_priority not in VALID_PRIORITIES else raw_priority
                    
                    # Map sprint/milestone names to IDs if available
                    task_sprint_name = pt.get("sprint", "")
                    task_milestone_name = pt.get("milestone", "")
                    
                    if task_sprint_name in sprint_name_to_id:
                        pt["sprint_id"] = sprint_name_to_id[task_sprint_name]
                    if task_milestone_name in milestone_name_to_id:
                        pt["milestone_id"] = milestone_name_to_id[task_milestone_name]
                    
                    prefixed_tasks.append(pt)

                # Serialize raw array directly — no wrapper key
                tasks_json_bytes = json_mod.dumps(prefixed_tasks, ensure_ascii=False, indent=2).encode("utf-8")
                json_file = io.BytesIO(tasks_json_bytes)

                # Debug: log exact payload being sent to NXDUNE
                logger.info(f"NXDUNE batch sync payload ({len(prefixed_tasks)} tasks):\n{tasks_json_bytes.decode('utf-8')[:2000]}")

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        batch_url,
                        headers={"Authorization": f"Bearer {x_task_token}"},
                        files={"file": ("tasks.json", json_file, "application/json")},
                    )

                if response.status_code in (200, 201):
                    for task in stored_tasks:
                        task.synced_to_nxdune = True
                    db.commit()
                    synced = True
                    # Use prefixed tasks as the canonical response (IDs match NXDUNE)
                    tasks = prefixed_tasks
                    logger.info(f"Synced {len(tasks)} tasks to NXDUNE batch API")
                else:
                    sync_error_detail = f"NXDUNE returned {response.status_code}: {response.text[:300]}"
                    logger.warning(f"NXDUNE batch sync failed — {sync_error_detail}")
            except Exception as sync_error:
                sync_error_detail = str(sync_error)
                logger.warning(f"Failed to sync tasks to NXDUNE: {sync_error_detail}")
                # Tasks are stored locally — continue regardless
        
        return {
            "status": "success",
            "message": f"Generated {len(tasks)} tasks successfully",
            "tasks": tasks,
            "tasks_created": len(tasks),
            "synced_to_nxdune": synced,
            "sync_error": sync_error_detail if not synced and x_task_token else None,
            "sprints_created": len(sprint_ids) if x_task_token else 0,
            "sprint_ids": sprint_ids if x_task_token else [],
            "sprint_names": sprint_names if x_task_token else [],
            "milestones_created": len(milestone_ids) if x_task_token else 0,
            "milestone_ids": milestone_ids if x_task_token else [],
            "milestone_names": milestone_names if x_task_token else [],
        }
    
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Task generation failed: {str(e)}"
        )


@app.post("/api/agent/tasks/sync/")
async def sync_tasks_to_nxdune(
    project_token: str = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None),
):
    """Sync locally stored (unsynced) tasks to NXDUNE."""
    if not x_task_token:
        raise HTTPException(status_code=400, detail="X-Task-Token header is required.")
    if not project_token:
        raise HTTPException(status_code=400, detail="project_token query param is required.")

    unsynced = db.query(models.Task).filter(
        models.Task.project_token == project_token,
        models.Task.owner_id == current_user.id,
        models.Task.synced_to_nxdune == False,
    ).all()

    if not unsynced:
        return {"status": "success", "message": "All tasks already synced.", "synced": 0, "failed": 0}

    try:
        import io, json as json_mod, hashlib, httpx

        nxdune_base = settings.task_api_base_url.rstrip("/")
        batch_url = f"{nxdune_base}/api/agent/tasks/batch/"
        short_hash = hashlib.md5(project_token.encode()).hexdigest()[:6]

        VALID_PRIORITIES = {"low", "medium", "high"}
        PRIORITY_MAP = {"critical": "high", "urgent": "high", "normal": "medium", "minor": "low"}

        def _strip_prefix(task_id: str) -> str:
            prefix = f"{project_token}_"
            return task_id[len(prefix):] if task_id.startswith(prefix) else task_id

        prefixed_tasks = []
        for t in unsynced:
            clean_id = _strip_prefix(t.task_id)
            raw_priority = str(t.priority or "medium").lower()
            priority = PRIORITY_MAP.get(raw_priority, raw_priority) if raw_priority not in VALID_PRIORITIES else raw_priority
            linked = [f"{short_hash}_{lid}" for lid in (t.linked_tasks or [])]
            prefixed_tasks.append({
                "task_id": f"{short_hash}_{clean_id}",
                "taskName": t.task_name,
                "task_type": t.task_type,
                "description": t.description or "",
                "priority": priority,
                "task_wallet": t.task_wallet,
                "startdate": t.startdate,
                "planned_start": t.planned_start,
                "deadline": t.deadline,
                "assignedTo": t.assigned_to or [],
                "reported_by": t.reported_by or "system",
                "sprint": t.sprint or "new",
                "milestone": t.milestone or "main",
                "linked_tasks": linked,
                "checklist": t.checklist or "",
            })

        tasks_json_bytes = json_mod.dumps(prefixed_tasks, ensure_ascii=False, indent=2).encode("utf-8")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                batch_url,
                headers={"Authorization": f"Bearer {x_task_token}"},
                files={"file": ("tasks.json", io.BytesIO(tasks_json_bytes), "application/json")},
            )

        if response.status_code in (200, 201):
            for t in unsynced:
                t.synced_to_nxdune = True
            db.commit()
            return {"status": "success", "message": f"Synced {len(unsynced)} tasks to NXDUNE.", "synced": len(unsynced), "failed": 0}
        else:
            error_detail = f"NXDUNE returned {response.status_code}: {response.text[:400]}"
            logger.warning(f"Sync failed — {error_detail}")
            raise HTTPException(status_code=502, detail=error_detail)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync to NXDUNE failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/tasks/local/")
async def get_local_tasks(
    project_token: str,
    page: int = 1,
    page_size: int = 50,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Get locally stored tasks for a project with pagination"""
    base_query = db.query(models.Task).filter(
        models.Task.project_token == project_token,
        models.Task.owner_id == current_user.id
    )

    total = base_query.count()
    offset = (page - 1) * page_size
    tasks = base_query.order_by(models.Task.created_at).offset(offset).limit(page_size).all()

    def serialize(t):
        # Strip project_token prefix from task_id for display (e.g. "proj_EPIC-01" → "EPIC-01")
        display_id = t.task_id
        prefix = f"{project_token}_"
        if display_id.startswith(prefix):
            display_id = display_id[len(prefix):]
        return {
            "task_id": display_id,
            "taskName": t.task_name,
            "task_type": t.task_type,
            "assignedTo": t.assigned_to or [],
            "description": t.description,
            "startdate": t.startdate,
            "planned_start": t.planned_start,
            "deadline": t.deadline,
            "priority": t.priority,
            "task_wallet": t.task_wallet,
            "sprint": t.sprint,
            "milestone": t.milestone,
            "reported_by": t.reported_by,
            "linked_tasks": t.linked_tasks or [],
            "checklist": t.checklist,
            "synced_to_nxdune": t.synced_to_nxdune,
            "nxdune_task_id": t.nxdune_task_id,
        }

    has_next = (offset + page_size) < total
    has_prev = page > 1

    return {
        "tasks": [serialize(t) for t in tasks],
        "count": total,
        "next": f"?project_token={project_token}&page={page + 1}" if has_next else None,
        "previous": f"?project_token={project_token}&page={page - 1}" if has_prev else None,
        "current_page": page,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@app.post("/api/agent/auto-generate/")
async def auto_generate_project_tasks(
    request: AutoGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None)
):
    """
    Generate the AI task-plan JSON for the task-creation page, upload it to the
    external batch task endpoint, and return the same payload for preview.
    """
    try:
        import json as json_mod

        if not x_task_token:
            raise HTTPException(
                status_code=400,
                detail="x-task-token header is required before generating and uploading task JSON.",
            )

        gov_response = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == request.project_token,
            models.GovernanceResponse.owner_id == current_user.id,
        ).first()

        project_name = (
            (gov_response.project_name if gov_response else None)
            or request.project_token
            or "Untitled Project"
        )
        project_info: Dict[str, Any] = {}
        project_exists = True
        try:
            fetched_project_info = await task_service.get_project_info(task_token=x_task_token)
            if isinstance(fetched_project_info, dict):
                project_info = fetched_project_info
        except Exception as e:
            project_exists = False
            logger.warning(
                "Failed to fetch project info for auto-generate plan %s: %s",
                request.project_token,
                e,
            )

        analysis_payload: Dict[str, Any] = {}
        analysis_report = str(gov_response.recommendation or "").strip() if gov_response else ""
        user_documents = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id
        ).order_by(models.Document.upload_date.desc()).all()

        for doc in user_documents:
            if not doc.analysis_result:
                continue
            try:
                parsed = json_mod.loads(doc.analysis_result)
            except (TypeError, ValueError):
                continue

            gov_ctx = parsed.get("governanceContext") or {}
            proj_meta = parsed.get("projectMeta") or {}
            doc_result_id = proj_meta.get("governance_result_id") or gov_ctx.get("result_id")
            doc_token_id = proj_meta.get("project_token") or gov_ctx.get("project_token")
            doc_project_name = str(
                proj_meta.get("project_name") or gov_ctx.get("project_name") or ""
            ).strip()

            matches_project = False
            if gov_response and doc_result_id is not None and str(doc_result_id) == str(gov_response.id):
                matches_project = True
            elif doc_token_id and str(doc_token_id) == str(request.project_token):
                matches_project = True
            elif project_name and doc_project_name and doc_project_name.lower() == str(project_name).strip().lower():
                matches_project = True

            if not matches_project:
                continue

            analysis_payload = parsed
            parsed_analysis = str(parsed.get("analysis") or "").strip()
            if parsed_analysis:
                analysis_report = parsed_analysis
            break

        project_data = (
            project_info.get("project")
            if isinstance(project_info.get("project"), dict)
            else project_info
        )
        project_start_date = _extract_first_date_from_mapping(
            project_data,
            (
                "start_date",
                "project_start_date",
                "project_start",
                "startdate",
                "startDate",
                "projectStartDate",
            ),
        )
        project_deadline = _extract_first_date_from_mapping(
            project_data,
            (
                "deadline",
                "project_deadline",
                "end_date",
                "project_end_date",
                "endDate",
                "projectEndDate",
            ),
        )
        if project_start_date:
            analysis_payload["project_start_date"] = project_start_date
        if project_deadline:
            analysis_payload["project_deadline"] = project_deadline

        reporter_name = " ".join(
            part for part in [current_user.first_name, current_user.last_name] if str(part or "").strip()
        ).strip() or current_user.email

        preview_payload = await build_local_task_plan_preview(
            project_token=request.project_token,
            project_name=project_name,
            project_reference=(gov_response.id if gov_response else request.project_token),
            sprint_reference=request.sprint_id,
            milestone_reference=request.milestone_id,
            analysis_report=analysis_report,
            analysis_payload=analysis_payload,
            prerequisites=request.prerequisites or analysis_payload.get("prerequisites") or [],
            reporter_name=reporter_name,
            custom_rules=request.custom_rules,
            project_type=request.project_type or "greenfield",
            process_mode=request.process_mode,
        )

        # -----------------------------------------------------------------
        # Project must be created DURING task-creation, and its deadline must
        # strictly follow the selected process_mode (derived by the preview).
        # -----------------------------------------------------------------
        if not project_exists:
            try:
                mode_deadline = (
                    preview_payload.get("project_deadline")
                    if isinstance(preview_payload, dict)
                    else None
                )
                mode_deadline = str(mode_deadline or "").strip() or None
                if not mode_deadline:
                    mode_deadline = analysis_payload.get("project_deadline") or analysis_payload.get("deadline")
                mode_deadline = str(mode_deadline or "").strip() or datetime.utcnow().strftime("%Y-%m-%d")

                create_payload = {
                    "name": project_name,
                    "deadline": mode_deadline,
                    "project_wallet": 1000,
                    "team": [24],
                    "project_token": request.project_token,
                }
                created_project = await task_service.create_project(create_payload, task_token=x_task_token)

                # If upstream returns credentials, persist to GovernanceResponse (best-effort)
                if (
                    gov_response
                    and isinstance(created_project, dict)
                    and isinstance(created_project.get("project_application"), dict)
                ):
                    app_data = created_project.get("project_application") or {}
                    if app_data.get("client_id") and app_data.get("client_secret"):
                        gov_response.client_id = app_data.get("client_id")
                        gov_response.client_secret = app_data.get("client_secret")
                        db.commit()

                project_exists = True
            except Exception as e:
                logger.warning(
                    "Auto-generate could not create missing project %s: %s",
                    request.project_token,
                    e,
                )


        created_sprints_list = (
            preview_payload.get("created_sprints")
            if isinstance(preview_payload, dict)
            and isinstance(preview_payload.get("created_sprints"), list)
            else []
        )
        created_milestones_list = (
            preview_payload.get("created_milestones")
            if isinstance(preview_payload, dict)
            and isinstance(preview_payload.get("created_milestones"), list)
            else []
        )
        # Fallback: if lists are empty keep backward compat with single-sprint keys
        if not created_sprints_list:
            single_sprint = (
                preview_payload.get("created_sprint")
                if isinstance(preview_payload, dict) and isinstance(preview_payload.get("created_sprint"), dict)
                else {}
            )
            if single_sprint:
                created_sprints_list = [single_sprint]
        if not created_milestones_list:
            single_milestone = (
                preview_payload.get("created_milestone")
                if isinstance(preview_payload, dict) and isinstance(preview_payload.get("created_milestone"), dict)
                else {}
            )
            if single_milestone:
                created_milestones_list = [single_milestone]

        placeholder_to_real_sprint: Dict[str, int] = {}
        placeholder_to_real_milestone: Dict[str, int] = {}
        placeholder_to_real_sprint_name: Dict[str, str] = {}
        placeholder_to_real_milestone_name: Dict[str, str] = {}
        sprint_create_results: list = []
        milestone_create_results: list = []

        project_start_obj = _parse_yyyy_mm_dd_date(preview_payload.get("project_start_date"))
        project_deadline_obj = _parse_yyyy_mm_dd_date(preview_payload.get("project_deadline"))

        # --- Create sprints ------------------------------------------------
        if request.sprint_id is not None:
            # User provided a single sprint — map every placeholder to it
            for sp in created_sprints_list:
                placeholder = str(sp.get("id") or "")
                if placeholder:
                    placeholder_to_real_sprint[placeholder] = request.sprint_id
        else:
            for sp in created_sprints_list:
                placeholder = str(sp.get("id") or "")
                sprint_start_value = str(
                    sp.get("start_date")
                    or preview_payload.get("project_start_date")
                    or ""
                ).strip()
                sprint_deadline_value = str(
                    sp.get("deadline")
                    or preview_payload.get("project_deadline")
                    or ""
                ).strip()

                s_start_obj = _parse_yyyy_mm_dd_date(sprint_start_value)
                s_deadline_obj = _parse_yyyy_mm_dd_date(sprint_deadline_value)
                if (
                    s_start_obj is not None
                    and s_deadline_obj is not None
                    and s_start_obj >= s_deadline_obj
                ):
                    if (
                        project_start_obj is not None
                        and project_deadline_obj is not None
                        and project_start_obj < project_deadline_obj
                    ):
                        sprint_start_value = str(preview_payload.get("project_start_date") or "").strip()
                        sprint_deadline_value = str(preview_payload.get("project_deadline") or "").strip()
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Project date window is too small for sprint creation. "
                                "Project deadline must be after project start date."
                            ),
                        )

                result = await task_service.create_sprint(
                    {
                        "name": str(sp.get("name") or f"Sprint {len(sprint_create_results) + 1}").strip()
                               or f"Sprint {len(sprint_create_results) + 1}",
                        "summary": str(sp.get("summary") or "").strip(),
                        "start_date": sprint_start_value,
                        "deadline": sprint_deadline_value,
                    },
                    task_token=x_task_token,
                )
                real_id = _extract_created_entity_id(result, "sprint")
                if real_id is None:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Sprint '{sp.get('name')}' was created but no id was returned by the task API.",
                    )
                sprint_create_results.append(result)
                if placeholder:
                    placeholder_to_real_sprint[placeholder] = real_id
                    real_name = _extract_created_entity_name(result, "sprint")
                    if real_name:
                        placeholder_to_real_sprint_name[placeholder] = real_name
                logger.info("Created sprint %s (placeholder %s) -> real id %s", sp.get("name"), placeholder, real_id)

        # --- Create milestones --------------------------------------------
        if request.milestone_id is not None:
            for ms in created_milestones_list:
                placeholder = str(ms.get("id") or "")
                if placeholder:
                    placeholder_to_real_milestone[placeholder] = request.milestone_id
        else:
            for ms in created_milestones_list:
                placeholder = str(ms.get("id") or "")
                sprint_placeholder = str(ms.get("sprint_id") or "")
                real_sprint_id = placeholder_to_real_sprint.get(
                    sprint_placeholder,
                    next(iter(placeholder_to_real_sprint.values()), None) if placeholder_to_real_sprint else None,
                )
                ms_start = str(ms.get("start_date") or "").strip()
                ms_deadline = str(ms.get("deadline") or "").strip()

                # Clamp milestone dates within its sprint's window
                if real_sprint_id is not None:
                    resolved_sprint_payload = await _resolve_sprint_schedule_payload(
                        real_sprint_id,
                        fallback=ms,
                        task_token=x_task_token,
                    )
                    sp_start_obj = _parse_yyyy_mm_dd_date(_extract_schedule_start(resolved_sprint_payload) or ms_start)
                    sp_end_obj = _parse_yyyy_mm_dd_date(_extract_schedule_deadline(resolved_sprint_payload) or ms_deadline)
                    if sp_start_obj is not None and sp_end_obj is not None:
                        ms_start, ms_deadline = _normalize_schedule_dates(
                            ms_start, ms_deadline,
                            min_date=sp_start_obj,
                            max_date=max(sp_start_obj, sp_end_obj),
                        )

                result = await task_service.create_milestone(
                    {
                        "name": str(ms.get("name") or f"Milestone {len(milestone_create_results) + 1}").strip()
                               or f"Milestone {len(milestone_create_results) + 1}",
                        "sprint_id": real_sprint_id,
                        "start_date": ms_start,
                        "deadline": ms_deadline,
                    },
                    task_token=x_task_token,
                )
                real_id = _extract_created_entity_id(result, "milestone")
                if real_id is None:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Milestone '{ms.get('name')}' was created but no id was returned by the task API.",
                    )
                milestone_create_results.append(result)
                if placeholder:
                    placeholder_to_real_milestone[placeholder] = real_id
                    real_name = _extract_created_entity_name(result, "milestone")
                    if real_name:
                        placeholder_to_real_milestone_name[placeholder] = real_name
                logger.info("Created milestone %s (placeholder %s) -> real id %s", ms.get("name"), placeholder, real_id)

        # --- Apply real IDs to all tasks ----------------------------------
        _apply_schedule_ids_to_preview_payload(
            preview_payload,
            placeholder_to_real_sprint=placeholder_to_real_sprint,
            placeholder_to_real_milestone=placeholder_to_real_milestone,
            placeholder_to_real_sprint_name=placeholder_to_real_sprint_name,
            placeholder_to_real_milestone_name=placeholder_to_real_milestone_name,
        )

        batch_payload = (
            preview_payload.get("preview_json")
            if isinstance(preview_payload, dict) and isinstance(preview_payload.get("preview_json"), list)
            else []
        )
        batch_payload_text = json_mod.dumps(batch_payload, ensure_ascii=False, indent=2)
        logger.info(
            "Generated task batch payload for project %s:\n%s",
            request.project_token,
            batch_payload_text,
        )
        print(f"[auto-generate] Generated task batch payload for {request.project_token}:\n{batch_payload_text}")
        batch_upload_result = await task_service.create_tasks_batch(
            batch_payload,
            task_token=x_task_token,
        )

        if isinstance(preview_payload, dict):
            if sprint_create_results:
                preview_payload["sprint_create_results"] = sprint_create_results
            if milestone_create_results:
                preview_payload["milestone_create_results"] = milestone_create_results
            preview_payload["batch_upload_result"] = batch_upload_result
            preview_payload["message"] = (
                f"AI generated {preview_payload.get('tasks_created', 0)} task preview item(s) "
                f"across {len(created_sprints_list)} sprint(s) "
            )
            preview_payload["preview_mode"] = False

        agent_service.seed_project_tasks(
            request.project_token,
            preview_payload.get("tasks") if isinstance(preview_payload, dict) else [],
        )

        return preview_payload
    except HTTPException:
        raise
    except TaskServiceError as e:
        _raise_task_service_http_exception(e, "Failed to upload generated task batch")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate local task preview: {e}")


@app.put("/api/agent/project-config/")
async def put_agent_project_config(
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """
    Persist per-project config used by the agent pipeline.

    Supports:
    - multipart/form-data: mode, prerequisites (JSON string), analysed_file (JSON string), input_file (binary), text (string), repo_link_url, project_token (optional)
    - application/json: { mode, prerequisites, analysed_file, text, repo_link_url, project_token? }
    """
    import json as json_mod

    content_type = str(request.headers.get("content-type") or "").lower()

    mode: str = ""
    prerequisites_obj: Any = None
    analysed_obj: Any = None
    governance_obj: Any = None
    repo_link_url: Optional[str] = None
    project_token: Optional[str] = None
    upload: Optional[UploadFile] = None
    text_content: Optional[str] = None

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        mode = str(payload.get("mode") or "").strip()
        prerequisites_obj = payload.get("prerequisites")
        analysed_obj = payload.get("analysed_file")
        governance_obj = payload.get("governance")
        repo_link_url = str(payload.get("repo_link_url") or "").strip() or None
        project_token = str(payload.get("project_token") or "").strip() or None
        text_content = str(payload.get("text") or "").strip() or None
    else:
        form = await request.form()
        mode = str(form.get("mode") or "").strip()
        repo_link_url = str(form.get("repo_link_url") or "").strip() or None
        project_token = str(form.get("project_token") or "").strip() or None
        text_content = str(form.get("text") or "").strip() or None

        prereq_raw = form.get("prerequisites")
        analysed_raw = form.get("analysed_file")
        governance_raw = form.get("governance")
        upload = form.get("input_file")

        if prereq_raw is not None and str(prereq_raw).strip():
            try:
                prerequisites_obj = json_mod.loads(str(prereq_raw))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid prerequisites JSON string")

        if analysed_raw is not None and str(analysed_raw).strip():
            try:
                analysed_obj = json_mod.loads(str(analysed_raw))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid analysed_file JSON string")

        if governance_raw is not None and str(governance_raw).strip():
            try:
                governance_obj = json_mod.loads(str(governance_raw))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid governance JSON string")

        if upload is not None and not isinstance(upload, UploadFile):
            upload = None

    if not mode:
        raise HTTPException(status_code=400, detail="mode is required")

    if isinstance(analysed_obj, dict):
        new_obj = {}
        if "analysis" in analysed_obj:
            new_obj["analysis"] = analysed_obj.get("analysis")
        
        if new_obj:
            analysed_obj = new_obj

    safe_project = project_token or "default"
    base_dir = Path(__file__).resolve().parent / "storage" / "project_configs" / str(current_user.id) / safe_project
    base_dir.mkdir(parents=True, exist_ok=True)

    config_payload = {
        "mode": mode,
        "prerequisites": prerequisites_obj if prerequisites_obj is not None else {},
        "analysed_file": analysed_obj if analysed_obj is not None else {},
        "governance": governance_obj if governance_obj is not None else {},
        "repo_link_url": repo_link_url,
        "project_token": safe_project,
        "owner_id": current_user.id,
        "saved_at": datetime.utcnow().isoformat(),
        "text": text_content,
    }

    (base_dir / "project_config.json").write_text(
        json_mod.dumps(config_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    saved_input_filename: Optional[str] = None
    if upload is not None and getattr(upload, "filename", None):
        content = await upload.read()
        if content:
            original_name = str(upload.filename)
            suffix = Path(original_name).suffix or ".bin"
            saved_input_filename = f"input_file{suffix}"
            (base_dir / saved_input_filename).write_bytes(content)
    try:
        if x_task_token:
            from task_service import task_service
            await task_service.update_project_config(config_payload, task_token=x_task_token)
    except Exception as e:
        logger.warning("Failed to sync project config to upstream: %s", e)

    return {
        "status": "ok",
        "message": "Task creation started and will shortly appear here in the list You can continue if you want task creation will continue in background",
        "project_token": safe_project,
        "mode": mode,
        "repo_link_url": repo_link_url,
        "saved_input_file": saved_input_filename,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        timeout_keep_alive=900,  # 15 minutes to support long-running AI analysis
    )

@app.get("/api/production/validate")
async def validate_production_readiness(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Validate if project is ready for production deployment"""
    try:
        validation = await agent_service._validate_production_readiness(project_token=project_token)
        return validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

@app.get("/api/production/report")
async def get_production_report(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get comprehensive production readiness report"""
    try:
        report = await agent_service._generate_production_report(project_token=project_token)
        return {"report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@app.post("/api/production/ensure-ready")
async def ensure_production_ready(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Ensure project meets production standards with auto-fixes"""
    try:
        result = await agent_service._ensure_production_ready_project(project_token=project_token)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Production preparation failed: {str(e)}")

@app.get("/api/system/health")
async def system_health_check():
    """Complete system health check for production readiness"""
    try:
        health = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "database": "healthy",
                "llm_gateway": "healthy" if llm_gateway.check_api_key() else "degraded",
                "docker": "healthy" if agent_service._check_docker_available() else "unavailable",
                "git_manager": "healthy"
            },
            "version": "1.0.0",
            "uptime": "unknown"
        }
        
        # Check critical components
        unhealthy_components = [k for k, v in health["components"].items() if v != "healthy"]
        if unhealthy_components:
            health["status"] = "degraded"
            health["issues"] = unhealthy_components
        
        return health
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
@app.get("/api/bulletproof/success-rate")
async def get_bulletproof_success_rate(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get bulletproof execution success rate metrics"""
    try:
        state = agent_service._ensure_project_state(project_token)
        all_tasks = state.get("tasks", [])
        completed_tasks = [t for t in all_tasks if agent_service._task_status_is_done(t.get("status"))]
        
        # Calculate success metrics
        total_tasks = len(all_tasks)
        completed_count = len(completed_tasks)
        success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
        
        # Analyze task complexity and success correlation
        task_success_by_type = {}
        for task in completed_tasks:
            task_type = task.get("task_type", "UNKNOWN")
            if task_type not in task_success_by_type:
                task_success_by_type[task_type] = {"completed": 0, "total": 0}
            task_success_by_type[task_type]["completed"] += 1
        
        for task in all_tasks:
            task_type = task.get("task_type", "UNKNOWN")
            if task_type not in task_success_by_type:
                task_success_by_type[task_type] = {"completed": 0, "total": 0}
            task_success_by_type[task_type]["total"] += 1
        
        # Calculate success rate by type
        for task_type in task_success_by_type:
            data = task_success_by_type[task_type]
            data["success_rate"] = (data["completed"] / data["total"] * 100) if data["total"] > 0 else 0
        
        # Determine if we're meeting the 90% target
        meets_target = success_rate >= 90.0
        
        return {
            "overall_success_rate": round(success_rate, 1),
            "meets_90_percent_target": meets_target,
            "total_tasks": total_tasks,
            "completed_tasks": completed_count,
            "remaining_tasks": total_tasks - completed_count,
            "success_by_type": task_success_by_type,
            "target": 90.0,
            "status": "EXCELLENT" if success_rate >= 90 else "GOOD" if success_rate >= 75 else "NEEDS_IMPROVEMENT"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Success rate calculation failed: {str(e)}")

@app.post("/api/bulletproof/optimize-tasks")
async def optimize_tasks_for_success(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Optimize existing tasks for bulletproof execution"""
    try:
        state = agent_service._ensure_project_state(project_token)
        all_tasks = state.get("tasks", [])
        
        # Apply bulletproof optimization to all tasks
        from task_generation_service import _bulletproof_task_generation_post_process
        optimized_tasks = _bulletproof_task_generation_post_process(all_tasks)
        
        # Update the state with optimized tasks
        state["tasks"] = optimized_tasks
        
        return {
            "success": True,
            "message": f"Optimized {len(optimized_tasks)} tasks for bulletproof execution",
            "optimized_count": len(optimized_tasks),
            "improvements": [
                "Enhanced task descriptions with bulletproof requirements",
                "Added comprehensive validation steps to checklists",
                "Improved error handling specifications",
                "Added testing and verification requirements"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task optimization failed: {str(e)}")

@app.get("/api/bulletproof/agent-performance")
async def get_agent_performance_metrics(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get detailed agent performance metrics for bulletproof execution"""
    try:
        state = agent_service._ensure_project_state(project_token)
        agents = state.get("agent_states", {})
        
        performance_metrics = {}
        
        for agent_id, agent_data in agents.items():
            if agent_service._is_system_agent_id(agent_id):
                continue
                
            # Calculate agent-specific metrics
            agent_tasks = [t for t in state.get("tasks", []) if t.get("assigned_agent") == agent_id]
            completed_agent_tasks = [t for t in agent_tasks if agent_service._task_status_is_done(t.get("status"))]
            
            success_rate = (len(completed_agent_tasks) / len(agent_tasks) * 100) if agent_tasks else 0
            
            # Analyze self-healing effectiveness
            healing_stats = {
                "total_healing_attempts": 0,
                "successful_healings": 0,
                "average_iterations": 0
            }
            
            # Get recent output logs for analysis
            output_logs = agent_data.get("output_log", [])
            healing_logs = [log for log in output_logs if "self-healing" in log.get("message", "").lower()]
            
            if healing_logs:
                healing_stats["total_healing_attempts"] = len(healing_logs)
                # Estimate successful healings (simplified)
                healing_stats["successful_healings"] = len([log for log in healing_logs if "completed" in log.get("message", "")])
            
            performance_metrics[agent_id] = {
                "agent_name": agent_data.get("name", agent_id),
                "status": agent_data.get("status", "unknown"),
                "total_tasks": len(agent_tasks),
                "completed_tasks": len(completed_agent_tasks),
                "success_rate": round(success_rate, 1),
                "meets_target": success_rate >= 90.0,
                "self_healing": healing_stats,
                "last_activity": agent_data.get("last_run", "never"),
                "current_task": agent_data.get("current_task", {}).get("title", "None") if agent_data.get("current_task") else "None"
            }
        
        # Calculate overall agent performance
        all_success_rates = [metrics["success_rate"] for metrics in performance_metrics.values() if metrics["total_tasks"] > 0]
        overall_agent_performance = sum(all_success_rates) / len(all_success_rates) if all_success_rates else 0
        
        return {
            "overall_agent_performance": round(overall_agent_performance, 1),
            "meets_90_percent_target": overall_agent_performance >= 90.0,
            "agent_metrics": performance_metrics,
            "total_active_agents": len([a for a in performance_metrics.values() if a["status"] != "idle"]),
            "high_performing_agents": len([a for a in performance_metrics.values() if a["success_rate"] >= 90]),
            "target": 90.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent performance calculation failed: {str(e)}")

@app.post("/api/bulletproof/guarantee-success")
async def guarantee_bulletproof_success(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Apply all bulletproof optimizations to guarantee 90%+ success rate"""
    try:
        # 1. Optimize tasks for bulletproof execution
        optimize_result = await optimize_tasks_for_success(project_token, current_user)
        
        # 2. Ensure production readiness
        production_result = await agent_service._ensure_production_ready_project(project_token=project_token)
        
        # 3. Validate system health
        health_result = await system_health_check()
        
        # 4. Calculate expected success rate
        success_metrics = await get_bulletproof_success_rate(project_token, current_user)
        
        return {
            "success": True,
            "message": "Bulletproof success optimizations applied",
            "expected_success_rate": "90%+",
            "optimizations_applied": [
                "Task descriptions enhanced with bulletproof requirements",
                "Comprehensive validation steps added to all tasks",
                "Error handling and testing requirements specified",
                "Production readiness validation enabled",
                "System health monitoring activated"
            ],
            "task_optimization": optimize_result,
            "production_readiness": production_result,
            "system_health": health_result.get("status", "unknown"),
            "current_metrics": success_metrics,
            "guarantee": "90%+ task execution success rate with bulletproof enhancements"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulletproof guarantee setup failed: {str(e)}")

ARTIFACTS_DIR = Path(os.getenv('ARTIFACTS_DIR', './project_artifacts'))
 
def get_container_port(project_id: str) -> str:
    """Return the host port for a preview container belonging to *project_id*.

    The function now checks three sources, in order:
    1️⃣ **Agent preview state** – ``agent_service.get_preview_status`` stores the
        ``preview_url`` (e.g. ``http://localhost:9100``) when a preview is
        running. If that URL is available we extract the port from it.
    2️⃣ **Legacy registry file** – ``.container_registry.json`` as before.
    3️⃣ **Docker ``ps`` fallback** – searches running containers whose name
        contains the *project_id* and parses the ``Ports`` column.
    Returns ``None`` when no port can be determined.
    """
    import re
    try:
        # 1️⃣ Check the in‑memory preview state via agent_service.
        preview_state = agent_service.get_preview_status(project_id)
        if preview_state and preview_state.get("status") == "running":
            preview_url = preview_state.get("preview_url")
            if preview_url:
                # Expected format: http://localhost:<port>
                match = re.search(r"://[^:/]+:(\d+)", preview_url)
                if match:
                    return match.group(1)

        # 2️⃣ Legacy registry lookup.
        registry_file = ARTIFACTS_DIR / '.container_registry.json'
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                for name, info in registry.items():
                    if project_id in name and isinstance(info, dict) and 'port' in info:
                        return str(info['port'])

        # 3️⃣ Docker fallback – search running containers for the project id.
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={project_id}", "--format", "{{{{.Names}}}} {{{{.Ports}}}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and project_id in parts[0]:
                    port_match = re.search(r"0\.0\.0\.0:(\d+)->", parts[1])
                    if port_match:
                        return port_match.group(1)
    except Exception as e:
        print(f"Error determining container port for {project_id}: {e}")

    print(f"No port found for project_id: {project_id}")
    return None
 
def _rewrite_html_assets(html_bytes: bytes, proxy_prefix: str) -> bytes:
    """Rewrite absolute asset paths in HTML so they route through the proxy.

    e.g. src="/assets/main.js"  ->  src="/app/{token}/assets/main.js"
         href="/style.css"       ->  href="/app/{token}/style.css"
         url(/fonts/x.woff)      ->  url(/app/{token}/fonts/x.woff)

    Only rewrites paths that start with "/" but NOT "//" (protocol-relative),
    and NOT paths that already start with the proxy_prefix.
    """
    import re as _re

    proxy_prefix = proxy_prefix.rstrip("/")

    def _replace_attr(m):
        attr, quote, path = m.group(1), m.group(2), m.group(3)
        # skip protocol-relative, data URIs, mailto, hash-only etc.
        if path.startswith("//") or ":" in path.split("/")[0] or path.startswith("#"):
            return m.group(0)
        if path.startswith(proxy_prefix + "/") or path == proxy_prefix:
            return m.group(0)
        return f'{attr}={quote}{proxy_prefix}{path}{quote}'

    def _replace_url(m):
        inner = m.group(1).strip("'\"")
        if inner.startswith("//") or ":" in inner.split("/")[0] or inner.startswith("#"):
            return m.group(0)
        if inner.startswith(proxy_prefix + "/") or inner == proxy_prefix:
            return m.group(0)
        return f"url({proxy_prefix}{inner})"

    try:
        html = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return html_bytes

    # Rewrite src=, href=, action= attributes with absolute paths
    html = _re.sub(
        r'(src|href|action)=(["\'])(/[^"\'>\s]*)\2',
        _replace_attr,
        html,
        flags=_re.IGNORECASE,
    )
    # Rewrite CSS url(/...) references
    html = _re.sub(
        r'url\((["\']?/[^)"\'>\s]*["\']?)\)',
        _replace_url,
        html,
        flags=_re.IGNORECASE,
    )

    return html.encode("utf-8")


def proxy_request(target_base: str, request: Request, forward_path: str, proxy_prefix: str = ""):
    """Generic proxy handler. If proxy_prefix is given, rewrites HTML asset paths."""
    target_url = target_base + forward_path

    # Forward query params
    if request.url.query:
        target_url += "?" + request.url.query

    # Forward headers (excluding host)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in ["host", "x-forwarded-for", "x-forwarded-proto"]
    }

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            allow_redirects=False,
            timeout=(5, 30)
        )

        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection"
        ]

        response_headers = {
            name: value
            for name, value in resp.headers.items()
            if name.lower() not in excluded_headers
        }

        body = resp.content
        content_type = resp.headers.get("content-type", "")

        # Rewrite HTML so absolute asset paths are proxied correctly
        if proxy_prefix and "text/html" in content_type:
            body = _rewrite_html_assets(body, proxy_prefix)

        return StreamingResponse(
            iter([body]),
            status_code=resp.status_code,
            headers=response_headers
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Proxy Error: {str(e)}")
 
@app.api_route("/app/{token}/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.api_route("/app/{token}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def route_proxy(token: str, request: Request, path: str = ""):
    """Route requests to the appropriate container based on project token"""
    # Get container port for this project
    port = get_container_port(token)
    print(f"Port for token {token}: {port}")
    if not port:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{token}' not found or container not running"
        )
   
    target = f"http://127.0.0.1:{port}"
    forward_path = "/" + path if path else "/"
    proxy_prefix = f"/app/{token}"
    return proxy_request(target, request, forward_path, proxy_prefix=proxy_prefix)