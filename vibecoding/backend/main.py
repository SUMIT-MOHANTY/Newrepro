import json
import hashlib
from pathlib import Path
import asyncio
import os
import uuid
import re as _re
from datetime import datetime
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import httpx
from dotenv import load_dotenv

from ai_config import ai_config
from project_manager import project_manager
from web_tools import make_request_with_tools
from git_manager import git_manager
from auth import SignupRequest, LoginRequest, signup_user, login_user, get_current_user, ForgotPasswordRequest, ResetPasswordRequest, forgot_password, reset_password
from dual_agent_handler import get_dual_agent_handler
from prompts import MAIN_SYSTEM_PROMPT, APP_NAME

import socket
import logging

# Silence noisy pollers
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

load_dotenv()

# Helper function to get AI client for verification
def get_ai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=ai_config.api_key,
        base_url=ai_config.base_url
    )

# Helper function to log prompts and responses
def log_ai_interaction(prompt: str, response: str, interaction_type: str = "main"):
    """Log AI prompts and responses to a text file for testing."""
    try:
        log_dir = Path("ai_logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"ai_log_{timestamp}.txt"
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{'='*80}\n")
            f.write(f"AI INTERACTION LOG - {interaction_type.upper()}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"{'='*80}\n\n")
            
            f.write(f"{'─'*80}\n")
            f.write(f"PROMPT:\n")
            f.write(f"{'─'*80}\n")
            f.write(prompt)
            f.write(f"\n\n{'─'*80}\n")
            f.write(f"RESPONSE:\n")
            f.write(f"{'─'*80}\n")
            f.write(response)
            f.write(f"\n\n{'='*80}\n")
        
        print(f"📝 Logged AI interaction to: {log_file}")
    except Exception as e:
        print(f"Failed to log AI interaction: {e}")

app = FastAPI(title=f"{APP_NAME} API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARTIFACTS_DIR = Path(os.getenv('ARTIFACTS_DIR', './project_artifacts'))

# ─── WebSocket Connection Manager ───────────────────────────────────────────────
class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, project_id: str):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket connected for project {project_id}. Total connections: {len(self.active_connections[project_id])}")
    
    def disconnect(self, websocket: WebSocket, project_id: str):
        if project_id in self.active_connections:
            try:
                self.active_connections[project_id].remove(websocket)
                logger.info(f"WebSocket disconnected for project {project_id}. Remaining: {len(self.active_connections[project_id])}")
                if not self.active_connections[project_id]:
                    del self.active_connections[project_id]
            except ValueError:
                pass
    
    async def broadcast(self, message: dict, project_id: str):
        """Broadcast message to all connected clients for a project"""
        if project_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send WebSocket message: {e}")
                    disconnected.append(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn, project_id)

manager = ConnectionManager()

# Create a session with connection pooling and retry logic for proxy requests
def get_proxy_session():
    """Create a fresh requests session for each call (no pooling for container connections)"""
    session = requests.Session()
    
    # For local container connections, disable connection pooling to avoid stale connections
    # when containers are being dynamically started/stopped
    adapter = HTTPAdapter(
        pool_connections=1,  # Minimal pooling
        pool_maxsize=1,      # One connection at a time
        max_retries=Retry(
            total=3,  # More retries for containers starting up
            connect=3,  # Retry on connection failures
            backoff_factor=0.3,  # Faster backoff (0.3s, 0.6s, 1.2s)
            status_forcelist=[500, 502, 503, 504],  # Don't retry on 429
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
        )
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def get_or_create_proxy_session():
    """Return a fresh session for each proxy request to avoid pooling issues"""
    return get_proxy_session()

async def wait_for_container_ready(base_url, max_attempts=20, initial_delay=1):
    """Wait until the container at base_url responds to requests"""
    delay = initial_delay
    for attempt in range(max_attempts):
        try:
            session = get_proxy_session()
            
            # First try the health endpoint if available
            try:
                health_resp = session.get(f"{base_url}/health", timeout=(2, 5))
                if health_resp.status_code == 200:
                    health_data = health_resp.json()
                    if health_data.get("status") == "healthy":
                        print(f"✅ Container {base_url} is healthy on attempt {attempt + 1}")
                        return True
                    else:
                        print(f"⏳ Container responding but not healthy yet: {health_data.get('reason', 'unknown')}")
            except:
                # Health endpoint not available, try regular HEAD request
                pass
            
            # Fallback to HEAD request
            resp = session.head(base_url, timeout=(2, 5))  # Quick check
            if resp.status_code < 500:  # 4xx is fine, means container is responding
                print(f"✅ Container {base_url} is ready on attempt {attempt + 1}")
                return True
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"⏳ Attempt {attempt + 1}/{max_attempts} - Waiting for container to be ready...")
                await asyncio.sleep(delay)
                delay *= 1.5  # Exponential backoff
    
    return False

# ─── Container Proxy Endpoint ──────────────────────────────────────────────────
def get_warming_up_html():
    """Returns the 'Warming up' HTML with meta-refresh."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="3">
        <title>Preview Warming Up</title>
        <style>
            body {{
                background: #0f172a;
                color: white;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            .loader {{
                width: 48px;
                height: 48px;
                border: 3px solid #FFF;
                border-bottom-color: transparent;
                border-radius: 50%;
                display: inline-block;
                box-sizing: border-box;
                animation: rotation 1s linear infinite;
                margin-bottom: 20px;
            }}
            @keyframes rotation {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .text {{ text-align: center; color: rgba(255,255,255,0.8); }}
            progress {{ width: 200px; height: 4px; accent-color: #a855f7; border-radius: 2px; margin-top: 15px; border: none; background: rgba(255,255,255,0.1); }}
        </style>
    </head>
    <body>
        <span class="loader"></span>
        <div class="text">
            <h2 style="margin: 0 0 8px 0;">Preview is Warming Up...</h2>
            <p style="margin: 0; opacity: 0.7;">Workspace is starting in the background.</p>
            <progress></progress>
        </div>
    </body>
    </html>
    """

@app.api_route("/vibecoding/app/{project_token}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False, response_class=HTMLResponse)
@app.api_route("/vibecoding/app/{project_token}/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False, response_class=HTMLResponse)
async def container_proxy(project_token: str, path: str = "", request: Request = None):
    """
    Generic proxy that routes traffic to the specific Docker container for a project.
    The preview URL is fixed per project — the proxy resolves the current container
    port at request time from .container_registry.json.
    """
    query_params = request.scope.get("query_string", b"").decode()

    # Determine if this is a "main page" request (HTML) or an asset request
    is_asset = bool(path) and any(
        path.endswith(ext) for ext in
        ('.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
         '.woff', '.woff2', '.ttf', '.eot', '.map', '.json', '.webp')
    )

    port = get_container_port(project_token)
    if not port:
        # Container not registered yet — always return warming-up page (never a JSON error)
        logger.info(f"🏘️ Container for {project_token} not registered yet. Returning 'Warming up' HTML.")
        return HTMLResponse(content=get_warming_up_html())

    # Pure transparent proxy: strip the /vibecoding/app/{project_token}/ prefix
    # and forward the remaining path to the container as-is
    target_base = f"http://127.0.0.1:{port}"
    target_url = f"{target_base}/{path}"
    if query_params:
        target_url += f"?{query_params}"

    excluded_outgoing = ["host", "content-length", "connection", "keep-alive", "proxy-connection", "upgrade"]
    headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded_outgoing}
    headers["accept-encoding"] = "identity"

    logger.info(f"🔀 Proxy: {request.method} /vibecoding/app/{project_token}/{path} → {target_url}")

    # Wait for container to be ready
    is_ready = await wait_for_container_ready(target_base, max_attempts=15, initial_delay=1.0)
    if not is_ready:
        print(f"⚠️ Container {target_base} still not responding after 15s. Proceeding anyway.")

    max_retries = 5
    last_error = None

    for attempt in range(max_retries):
        try:
            session = get_proxy_session()
            body = await request.body()

            print(f"🔄 Proxying {request.method} to {target_url} (attempt {attempt + 1})")
            resp = session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body if body else None,
                allow_redirects=False,
                timeout=(5, 30)
            )

            excluded_response = ["content-encoding", "content-length", "transfer-encoding", "connection",
                                  "keep-alive", "x-frame-options", "content-security-policy"]
            response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_response}
            response_headers["X-Frame-Options"] = "ALLOWALL"
            response_headers["Access-Control-Allow-Origin"] = "*"

            final_content = resp.content
            encoding = resp.headers.get("content-encoding", "").lower()
            if "gzip" in encoding:
                import gzip as _gzip
                try:
                    final_content = _gzip.decompress(final_content)
                except Exception:
                    pass

            # Rewrite response content to add proxy prefix to all absolute paths
            # This makes the container's responses work through the proxy
            content_type = resp.headers.get("content-type", "").lower()
            proxy_prefix = f"/vibecoding/app/{project_token}"
            
            # Only rewrite text-based content types
            if final_content and any(ct in content_type for ct in ["text/html", "text/css", "application/javascript", "text/javascript", "application/json"]):
                try:
                    text_content = final_content.decode('utf-8', errors='ignore')
                    
                    # Rewrite absolute paths to include proxy prefix
                    # Match: href="/...", src="/...", action="/...", url(/...), "/..." in JSON/JS
                    # But avoid double-prefixing paths that already have the prefix
                    
                    if "text/html" in content_type:
                        # HTML: Rewrite attributes
                        text_content = _re.sub(
                            r'((?:href|src|action|data|content)=")(/(?!vibecoding/app/)[^"]*)"',
                            rf'\1{proxy_prefix}\2"',
                            text_content
                        )
                        text_content = _re.sub(
                            r"((?:href|src|action|data|content)=')(/(?!vibecoding/app/)[^']*)'",
                            rf"\1{proxy_prefix}\2'",
                            text_content
                        )
                    
                    elif "text/css" in content_type:
                        # CSS: Rewrite url() references
                        text_content = _re.sub(
                            r'url\((["\']?)(/(?!vibecoding/app/)[^)"\'"]+)\1\)',
                            rf'url(\1{proxy_prefix}\2\1)',
                            text_content
                        )
                    
                    elif "javascript" in content_type or "json" in content_type:
                        # JS/JSON: Rewrite string literals with absolute paths
                        # Match strings like "/api/...", "/assets/...", etc.
                        text_content = _re.sub(
                            r'(["\'])(/(?!vibecoding/app/)[a-zA-Z0-9/_.-]+)\1',
                            rf'\1{proxy_prefix}\2\1',
                            text_content
                        )
                    
                    final_content = text_content.encode('utf-8')
                    logger.debug(f"✅ Rewrote paths in {content_type} for {project_token}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to rewrite paths in response: {e}")

            response_headers["content-length"] = str(len(final_content))
            media_type = resp.headers.get("content-type", "")

            return StreamingResponse(
                iter([final_content]),
                status_code=resp.status_code,
                headers=response_headers,
                media_type=media_type
            )

        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 0.5
                print(f"⏳ Connection error (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            break
        except Exception as e:
            last_error = e
            break

    # All retries failed — always return warming-up HTML (never a raw error in the iframe)
    logger.info(f"🏘️ Proxy failed for {project_token}. Returning 'Warming up' HTML.")
    return HTMLResponse(content=get_warming_up_html(), status_code=200)


class Message(BaseModel):
    role: str
    content: str
    code: Optional[str] = None

class GenerateRequest(BaseModel):
    prompt: str
    history: List[Message] = []
    project_id: Optional[str] = None
    discuss_mode: bool = False
    images: Optional[List[str]] = None

class MessagePersistenceRequest(BaseModel):
    id: str
    role: str
    content: Optional[str] = None
    code: Optional[str] = None
    version_id: Optional[str] = None
    timestamp: str
    suggestions: Optional[List[str]] = None
    tool_calls: Optional[List[dict]] = None
    images: Optional[List[str]] = None
    summary: Optional[str] = None

class GenerateResponse(BaseModel):
    message: str
    code: Optional[str] = None
    project_id: str
    version_id: Optional[str] = None
    preview_url: Optional[str] = None
    tool_calls_log: Optional[List[dict]] = None
    suggestions: Optional[List[str]] = None
    summary: Optional[str] = None
    message_id: Optional[str] = None

class ProjectCreateRequest(BaseModel):
    project_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    project_id: str
    name: Optional[str] = None
    created_at: str
    versions: List[dict]
    current_version: Optional[str] = None
    owner_id: Optional[int] = None

class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]

class GitRequest(BaseModel):
    project_id: str
    files: Optional[List[str]] = None
    message: Optional[str] = None
    branch_name: Optional[str] = None
    remote_url: Optional[str] = None
    remote_name: Optional[str] = "origin"
    username: Optional[str] = None
    token: Optional[str] = None
    chat_version: Optional[int] = None
    version_id: Optional[str] = None
    restore: Optional[bool] = False

async def summarize_content(content: str, code: str = None) -> str:
    """Helper to generate a professional CXO summary for a message."""
    try:
        prompt = f"""Summarize the following implementation into a single professional, justifiable paragraph for a CXO or Business Analyst. 
Focus on the strategic impact and functional achievements. Use a sophisticated, outcome-oriented tone.
Do NOT use technical jargon.

CONTENT: {content[:1000]}
CODE SNIPPET: {code[:2000] if code else "No code provided"}

SUMMARY:"""
        
        messages = [
            {"role": "system", "content": "You are a professional business strategist and product manager. Your job is to translate technical code updates into business-value summaries."},
            {"role": "user", "content": prompt}
        ]
        
        response = ai_config.make_request(messages)
        if "choices" in response and len(response["choices"]) > 0:
            summary = response["choices"][0]["message"].get("content", "").strip()
            # Remove prefixes like "Summary: " or "Strategic Impact: "
            if ":" in summary and len(summary.split(":")[0]) < 25:
                summary = ":".join(summary.split(":")[1:]).strip()
            
            if summary:
                return summary
        
        return "Implemented requested functionality to enhance the platform's core capabilities and business logic."
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        # Fallback to a generic summary if AI fails
        return "Modifications completed based on your specific requirements to ensure system stability and performance."

async def lazy_summarize_message(msg_id: str, content: str, code: str):
    """Background task to generate and save a summary if it's missing."""
    try:
        summary = await summarize_content(content, code)
        from auth import get_db
        conn = get_db()
        try:
            conn.execute("UPDATE messages SET summary = ? WHERE id = ?", (summary, msg_id))
            conn.commit()
            logger.info(f"✅ Lazy-summarized message {msg_id}")
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed lazy-summarization for {msg_id}: {e}")

async def generate_suggestions(message: str, code: str, user_prompt: str) -> List[str]:
    """Use AI to generate 3 contextual one-liner suggestions based on what was just created."""
    try:
        suggestion_prompt = f"""Based on what was just generated, provide exactly 3 short, actionable one-liner suggestions for what the user might want to do next. Each suggestion should be a natural follow-up to enhance or extend what was created.

User's original request: {user_prompt}

What was generated:
{message[:500]}

Code summary: {"Code was generated" if code else "No code generated"}

Provide ONLY 3 suggestions, one per line, no numbering, no explanations. Each should be a complete sentence that could be sent directly as a prompt. Keep each under 60 characters.

Example format:
Add a navigation bar with smooth scrolling
Make the design responsive for mobile
Add hover animations to the buttons"""

        suggestion_messages = [
            {"role": "system", "content": "You are a helpful assistant that generates concise, actionable suggestions."},
            {"role": "user", "content": suggestion_prompt}
        ]
        
        response = ai_config.make_request(suggestion_messages, temperature=0.7)
        suggestions_text = response["choices"][0]["message"].get("content", "") if "choices" in response else ""
        
        # Log the suggestion generation interaction
        log_ai_interaction(suggestion_prompt, suggestions_text, "suggestion_generation")
        
        # Parse suggestions (one per line)
        suggestions = [s.strip() for s in suggestions_text.strip().split('\n') if s.strip()]
        # Remove any numbering like "1.", "2.", etc.
        suggestions = [_re.sub(r'^\d+[\.\)]\s*', '', s) for s in suggestions]
        # Take only first 3
        suggestions = suggestions[:3]
        
        return suggestions if len(suggestions) == 3 else []
    except Exception as e:
        print(f"Failed to generate suggestions: {e}")
        return []

# AI Configuration is now handled by ai_config.py

# ─── Auth Endpoints ─────────────────────────────────────────────────────────────
@app.post("/vibecoding/api/auth/signup")
async def signup(request: SignupRequest):
    """Register a new user."""
    return signup_user(request)


@app.post("/vibecoding/api/auth/login")
async def login(request: LoginRequest):
    """Login with email and password."""
    return login_user(request)


@app.get("/vibecoding/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current authenticated user."""
    return user


@app.get("/vibecoding/api/auth/verify")
async def verify_token(user: dict = Depends(get_current_user)):
    """Verify if the current token is valid."""
    return {"valid": True, "user": user}


@app.post("/vibecoding/api/auth/forgot-password")
async def forgot_password_endpoint(request: ForgotPasswordRequest):
    """Request password reset."""
    return forgot_password(request)


@app.post("/vibecoding/api/auth/reset-password")
async def reset_password_endpoint(request: ResetPasswordRequest):
    """Reset password using token from email."""
    return reset_password(request)


# ─── SSO / Handoff from BRDAnalyzer ─────────────────────────────────────────────
import hmac as _hmac
import base64 as _base64
import time as _time_mod

HANDOFF_SECRET = os.getenv("HANDOFF_SECRET", "dsuite-vibecoding-handoff-secret-local-dev")


def _verify_handoff_token(token_str: str) -> dict:
    """
    Verify HMAC-signed handoff token and retrieve payload from D-Suite database.
    
    New approach: Token is just tokenId.signature, payload is stored in database.
    This avoids URL length limits (HTTP 431 errors).
    """
    parts = token_str.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError("Malformed handoff token")
    
    token_id, sig = parts
    
    # Verify HMAC signature
    expected_sig = _hmac.new(HANDOFF_SECRET.encode(), token_id.encode(), hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expected_sig, sig):
        raise ValueError("Invalid handoff token signature")
    
    # Retrieve payload from D-Suite database
    # We need to make an HTTP request to D-Suite backend to get the payload
    try:
        import requests
        dsuite_backend_url = os.getenv("DSUITE_BACKEND_URL", "http://localhost:8000")
        response = requests.get(
            f"{dsuite_backend_url}/api/vibecoding/handoff-payload/{token_id}",
            timeout=5
        )
        
        if response.status_code == 404:
            raise ValueError("Handoff token not found or expired")
        elif response.status_code != 200:
            raise ValueError(f"Failed to retrieve handoff payload: {response.status_code}")
        
        payload = response.json()
        
        # Check expiry
        if payload.get("exp", 0) < int(_time_mod.time()):
            raise ValueError("Handoff token expired")
        
        return payload
        
    except requests.exceptions.RequestException as e:
        # Fallback: Try to decode from token (backward compatibility with old tokens)
        try:
            # Old format: payload_b64.signature
            payload_b64 = token_id
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(_base64.urlsafe_b64decode(payload_b64))
            if payload.get("exp", 0) < int(_time_mod.time()):
                raise ValueError("Handoff token expired")
            return payload
        except Exception:
            raise ValueError(f"Failed to retrieve handoff payload: {str(e)}")


class SSOHandoffRequest(BaseModel):
    handoff_token: str


@app.post("/vibecoding/api/auth/sso")
async def sso_handoff(request: SSOHandoffRequest):
    """
    Accept a handoff token from BRDAnalyzer, auto-create or login the user,
    create the project if needed, and return a Vibecoding JWT.
    """
    try:
        payload = _verify_handoff_token(request.handoff_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    email = payload.get("email", "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Handoff token missing email")

    first_name = payload.get("first_name", "")
    last_name = payload.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() or email.split("@")[0]
    username = email.split("@")[0].replace(".", "_").replace("+", "_").lower()

    project_token = payload.get("project_token")
    project_context = payload.get("project_context", {})

    from auth import get_db as get_auth_db, create_jwt_token, hash_password, generate_avatar_color, generate_random_password
    from email_service import email_service

    conn = get_auth_db()
    is_new_user = False
    generated_password = None
    
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            user_id = user["id"]
            user_data = {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "avatar_color": user["avatar_color"],
                "created_at": user["created_at"],
            }
        else:
            # New user - generate password and mark for email notification
            is_new_user = True
            generated_password = generate_random_password()
            password_hash, salt = hash_password(generated_password)
            avatar_color = generate_avatar_color(email)
            now = datetime.utcnow().isoformat()
            base_username = username
            suffix = 0
            while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                suffix += 1
                username = f"{base_username}_{suffix}"
            cursor = conn.execute(
                """INSERT INTO users (username, email, password_hash, salt, full_name, avatar_color, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (username, email, password_hash, salt, full_name, avatar_color, now, now),
            )
            conn.commit()
            user_id = cursor.lastrowid
            user_data = {
                "id": user_id,
                "username": username,
                "email": email,
                "full_name": full_name,
                "avatar_color": avatar_color,
                "created_at": now,
            }
            
            # Send welcome email with credentials to new user
            try:
                logger.info(f"📧 Sending welcome email to new user: {email}")
                email_sent = email_service.send_welcome_email(
                    email,
                    username,
                    generated_password
                )
                if email_sent:
                    logger.info(f"✅ Welcome email sent successfully to {email}")
                else:
                    logger.warning(f"⚠️ Failed to send welcome email to {email}")
            except Exception as e:
                logger.error(f"❌ Error sending welcome email to {email}: {e}")
                # Don't fail the handoff if email fails - user can still login

        token = create_jwt_token({"user_id": user_id, "email": email, "username": username})
    finally:
        conn.close()

    project_info = None
    if project_token:
        existing = project_manager.get_project_info(project_token)
        if existing:
            if existing.get("owner_id") is None:
                existing["owner_id"] = user_id
            if project_context:
                existing["brd_context"] = project_context
            # Update with new handoff fields
            if payload.get("brd_text"):
                existing["brd_text"] = payload["brd_text"]
            if payload.get("analysis_data"):
                existing["analysis_data"] = payload["analysis_data"]
            if payload.get("prerequisites"):
                existing["prerequisites"] = payload["prerequisites"]
            if payload.get("custom_rules"):
                existing["custom_rules"] = payload["custom_rules"]
            if payload.get("governance_context"):
                existing["governance_context"] = payload["governance_context"]
            existing["process_mode"] = payload.get("process_mode", "vibe_coding")
            existing["handoff_source"] = "dsuite"
            existing["handoff_timestamp"] = datetime.utcnow().isoformat()
            
            project_manager.update_project_metadata(project_token, existing)
            project_info = existing
        else:
            project_name = payload.get("project_name") or project_context.get("project_name") or f"Project {project_token[:8]}"
            brd_summary = project_context.get("brd_summary", "")
            
            # Create project with full handoff data
            project_metadata = {
                "name": project_name,
                "description": brd_summary,
                "owner_id": user_id,
                "brd_context": project_context,
                "brd_text": payload.get("brd_text", ""),
                "analysis_data": payload.get("analysis_data", {}),
                "prerequisites": payload.get("prerequisites", []),
                "custom_rules": payload.get("custom_rules", ""),
                "governance_context": payload.get("governance_context", {}),
                "process_mode": payload.get("process_mode", "vibe_coding"),
                "handoff_source": "dsuite",
                "handoff_timestamp": datetime.utcnow().isoformat(),
                "auto_execute": True,  # Flag to trigger automatic execution
            }
            
            project_manager.create_project_directory(project_token, metadata=project_metadata)
            project_info = project_manager.get_project_info(project_token)

    # Prepare response message
    message = "SSO login successful"
    if is_new_user:
        message = "Welcome! Your account has been created. Check your email for login credentials."
    
    return {
        "token": token,
        "user": user_data,
        "project": project_info,
        "message": message,
        "auto_execute": project_info.get("auto_execute", False) if project_info else False,
        "is_new_user": is_new_user,
        "email_sent": is_new_user and generated_password is not None,
    }


@app.post("/vibecoding/api/projects/{project_id}/trigger-handoff-execution")
async def trigger_handoff_execution(
    project_id: str,
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    """
    Trigger automatic project creation and task execution for a project
    that was created via D-Suite handoff.
    
    This endpoint:
    1. Reads the BRD text and analysis data from project metadata
    2. Writes the BRD to the agent's mailbox (/tmp/vibe_prompt)
    3. Starts the agent container if not already running
    4. Returns immediately while agent processes in background
    """
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Verify ownership
        if project_info.get("owner_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this project")
        
        # Check if this is a handoff project
        if project_info.get("handoff_source") != "dsuite":
            raise HTTPException(status_code=400, detail="This project was not created via D-Suite handoff")
        
        # Check if execution has already been started
        if project_info.get("execution_started"):
            logger.info(f"⚠️ Execution already started for project {project_id} at {project_info.get('execution_start_time')}")
            return {
                "status": "already_started",
                "message": "Execution has already been triggered for this project",
                "project_id": project_id,
                "execution_start_time": project_info.get("execution_start_time"),
            }
        
        # Get BRD text and analysis data
        brd_text = project_info.get("brd_text", "")
        analysis_data = project_info.get("analysis_data", {})
        prerequisites = project_info.get("prerequisites", [])
        custom_rules = project_info.get("custom_rules", "")
        
        if not brd_text and not analysis_data:
            raise HTTPException(status_code=400, detail="No BRD data found in project metadata")
        
        # Construct comprehensive prompt for the agent
        agent_prompt = f"""# VibeCoding Auto-Execution from D-Suite

## Project Information
- **Project Name**: {project_info.get('name', 'Unnamed Project')}
- **Project ID**: {project_id}
- **Source**: D-Suite Handoff
- **Timestamp**: {project_info.get('handoff_timestamp', 'Unknown')}

## Business Requirements Document (BRD)

{brd_text}

## AI Analysis Summary

{json.dumps(analysis_data, indent=2) if analysis_data else 'No analysis data available'}

## Prerequisites Provided

{json.dumps(prerequisites, indent=2) if prerequisites else 'No prerequisites specified'}

## Custom Development Rules

{custom_rules if custom_rules else 'No custom rules specified'}

---

**Instructions**: Please analyze the BRD above and create a complete, production-ready application that fulfills all the requirements. Follow these steps:

1. **Plan**: Create a comprehensive task plan with all necessary components
2. **Implement**: Generate all required code files with complete implementations
3. **Deploy**: Set up the application and make it accessible
4. **Verify**: Ensure everything works correctly

Begin implementation now."""

        container_name = f"vibecoding_{project_id}"  # Match the naming convention in project_manager
        
        try:
            # Check if container is running
            check_container = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={container_name}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            container_running = bool(check_container.stdout.strip())
            
            if not container_running:
                # Start the container FIRST
                logger.info(f"Starting agent container: {container_name}")
                
                # Get user's API key from project metadata or use default
                api_key = project_info.get("api_key", os.getenv("OPENAI_API_KEY", ""))
                
                # Get the workspace path for this project
                workspace_path = str(project_manager.artifacts_dir / project_id / "workspace")
                
                # Start the agent container
                container_url = project_manager.start_agent_container(
                    api_key=api_key,
                    project_path=workspace_path,
                    project_id=project_id
                )
                
                if not container_url:
                    raise HTTPException(status_code=500, detail="Failed to start container")
                
                logger.info(f"✅ Container started successfully at {container_url}")
                
                # Wait for container to fully initialize
                import asyncio
                await asyncio.sleep(8)  # Increased wait time for container initialization
            else:
                logger.info(f"Container {container_name} is already running")
            
            # Send a simple trigger prompt to start the agent
            trigger_prompt = "start building based on the BRD requirements"
            
            logger.info(f"Sending trigger prompt to container")
            
            # Use docker exec to write the prompt inside the container
            write_result = subprocess.run(
                ["docker", "exec", container_name, "bash", "-c", 
                 f"echo '{trigger_prompt}' > /tmp/vibe_prompt"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if write_result.returncode != 0:
                logger.error(f"Failed to write prompt to container: {write_result.stderr}")
                raise HTTPException(status_code=500, detail=f"Failed to send prompt to agent: {write_result.stderr}")
            
            logger.info(f"✅ Successfully sent trigger prompt to container")
            
            # Mark project as execution started
            project_info["execution_started"] = True
            project_info["execution_start_time"] = datetime.utcnow().isoformat()
            project_manager.update_project_metadata(project_id, project_info)
            
            return {
                "status": "triggered",
                "message": "Agent execution triggered successfully",
                "project_id": project_id,
                "container_name": container_name,
                "container_running": container_running,
            }
            
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Docker command timed out")
        except Exception as e:
            logger.error(f"Failed to trigger handoff execution: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to trigger execution: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in trigger_handoff_execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vibecoding/api/projects/{project_id}/brd-context")
async def get_brd_context(project_id: str):
    """
    API endpoint for the AI agent inside the container to fetch BRD context.
    This is called by the agent when it receives the trigger prompt.
    No authentication required since it's called from within the container.
    """
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check if this is a handoff project
        if project_info.get("handoff_source") != "dsuite":
            return {
                "has_brd": False,
                "message": "This project was not created via D-Suite handoff"
            }
        
        # Return the BRD context
        return {
            "has_brd": True,
            "project_name": project_info.get("name", "Unnamed Project"),
            "project_id": project_id,
            "brd_text": project_info.get("brd_text", ""),
            "analysis_data": project_info.get("analysis_data", {}),
            "prerequisites": project_info.get("prerequisites", []),
            "custom_rules": project_info.get("custom_rules", ""),
            "governance_context": project_info.get("governance_context", {}),
            "handoff_timestamp": project_info.get("handoff_timestamp", ""),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching BRD context for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vibecoding/api")
async def root():
    return {"message": f"{APP_NAME} API is running"}

# ─── WebSocket Endpoint ─────────────────────────────────────────────────────────
@app.websocket("/vibecoding/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time project updates"""
    await manager.connect(websocket, project_id)
    try:
        while True:
            # Keep connection alive and receive any client messages
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
    except Exception as e:
        logger.error(f"WebSocket error for project {project_id}: {e}")
        manager.disconnect(websocket, project_id)

@app.post("/vibecoding/api/broadcast/{project_id}")
async def broadcast_message(project_id: str, request: dict):
    """
    Internal endpoint for AI agent to broadcast messages via WebSocket.
    This is called by the ai-agent.py report() function.
    """
    try:
        await manager.broadcast(request, project_id)
        return {"status": "broadcasted"}
    except Exception as e:
        logger.error(f"Broadcast failed for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/chat/dual-agent")
async def dual_agent_chat(request: GenerateRequest):
    """
    New endpoint using dual-agent architecture:
    - Routes to Chat Agent for general questions
    - Routes to Code Execution Agent (in container) for code generation
    """
    try:
        # Get dual agent handler
        handler = get_dual_agent_handler()
        
        # Convert history to dict format
        history = [{"role": msg.role, "content": msg.content} for msg in request.history]
        
        # Handle the message
        result = await handler.handle_message(request.prompt, history)
        
        if result.get("success"):
            # Get or create project ID
            project_id = request.project_id or project_manager.generate_project_id()
            
            # Save code version if code was generated
            version_id = None
            code = result.get("code")
            preview_url = result.get("preview_url")
            
            if code:
                code = _preprocess_ai_response(code)
                version_id, _ = project_manager.update_workspace_from_code(project_id, code, request.prompt)
                
                # Save chat history for the current branch (not commit hash)
                status = git_manager.get_status(project_id)
                current_branch = status.get("branch", "main") if status["status"] == "success" else "main"
                
                history.append({"role": "user", "content": request.prompt})
                history.append({"role": "assistant", "content": result.get("message", "")})
                await project_manager.save_chat_version(project_id, current_branch, history)
                
                container_url = await project_manager.create_container_for_code(project_id, "workspace")
                if container_url:
                    preview_url = container_url
            
            return {
                "message": result.get("message", ""),
                "code": code,
                "project_id": project_id,
                "version_id": version_id,
                "preview_url": preview_url,
                "agent_type": result.get("agent_type"),
                "tool_calls_log": None
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def _preprocess_ai_response(text: str) -> str:
    """Fix mixed AI output where // FILE: headers are used for SEARCH/REPLACE patches.

    Handles three common AI mis-formats:
    1. "// FILE: path" followed by <<<SEARCH → converted to "// PATCH: path"
    2. "// FILE: path (Updated)" empty markers → removed entirely
    3. Duplicate "// FILE: path" blocks where only the last has real content → deduplicated
    """
    import re

    # Pass 1: Remove "// FILE: path (Updated)" artifact markers (always empty labels)
    text = re.sub(r'(?m)^//\s*FILE:\s*[^\n]+?\s*\(Updated\)\s*$', '', text)

    # Pass 2: Convert "// FILE: path" that precede <<<SEARCH into "// PATCH: path"
    # Walk line-by-line so we can look ahead
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        file_match = re.match(r'^(//\s*)FILE:\s*(.+)$', line.strip())
        if file_match:
            filename = file_match.group(2).strip()
            # Look ahead past blank lines for <<<SEARCH
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r'\s*<<<\s*SEARCH', lines[j]):
                result.append(f'// PATCH: {filename}')
            else:
                result.append(line)
        else:
            result.append(line)
        i += 1

    text = '\n'.join(result)

    # Pass 3: Deduplicate // FILE: markers with the same path (keep last)
    file_positions = {}
    for m in re.finditer(r'(?i)(?://|#|<!--)\s*FILE:\s*([^\n]+)', text):
        path = m.group(1).strip().rstrip(' ->')
        file_positions.setdefault(path, []).append(m.start())

    remove_ranges = []
    for path, positions in file_positions.items():
        if len(positions) > 1:
            all_occurrences = list(re.finditer(
                r'(?:(?://|#|<!--)\s*FILE:\s*' + re.escape(path) + r'[^\n]*\n)',
                text
            ))
            for occ in all_occurrences[:-1]:
                next_file = re.search(r'(?://|#|<!--)\s*FILE:\s*', text[occ.end():])
                end = occ.end() + next_file.start() if next_file else occ.end()
                content_between = text[occ.end():end].strip()
                if not content_between or content_between.startswith('<<<'):
                    remove_ranges.append((occ.start(), end))

    for start, end in sorted(remove_ranges, reverse=True):
        text = text[:start] + text[end:]

    return text.strip()


@app.post("/vibecoding/api/projects/{project_id}/messages")
async def save_project_message(project_id: str, request: MessagePersistenceRequest, user: dict = Depends(get_current_user)):
    """Persist a single user or assistant message to the project's chat history"""
    from auth import get_db
    conn = get_db()
    try:
        # Get current container ID for logging if not provided
        container_id = None
        project_info = project_manager.get_project_info(project_id)
        if project_info:
            container_id = project_info.get("container_id")

        conn.execute(
            """INSERT OR REPLACE INTO messages 
               (id, project_id, container_id, role, content, code, version_id, timestamp, suggestions, tool_calls, image_paths, metadata, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.id, project_id, container_id, request.role, request.content, request.code, 
             request.version_id, request.timestamp, 
             json.dumps(request.suggestions) if request.suggestions else None,
             json.dumps(request.tool_calls) if request.tool_calls else None,
             json.dumps(request.images) if request.images else None,
             None,
             request.summary)
        )
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()


class AgentMessageRequest(BaseModel):
    """Request model for AI agent to save messages via API"""
    project_id: str
    container_id: str
    role: str
    content: str
    code: Optional[str] = None
    suggestions: Optional[List[dict]] = None
    metadata: Optional[dict] = None
    summary: Optional[str] = None


@app.post("/vibecoding/api/agent/message")
async def save_agent_message(request: AgentMessageRequest):
    """
    API endpoint for AI agent (running in Docker) to save messages to database.
    This replaces direct database access from the container.
    No authentication required - only accessible from Docker network.
    """
    try:
        from auth import get_db
        import uuid
        import time
        
        # Always capture the current Git HEAD as version_id for every agent message.
        # This ensures the restore functionality can always find a valid checkpoint
        # from any preceding message in the chat history.
        version_id = None
        try:
            hash_res = git_manager._run_git_command(request.project_id, ["rev-parse", "HEAD"])
            if hash_res.get("status") == "success" and hash_res.get("stdout", "").strip():
                version_id = hash_res["stdout"].strip()
                logger.info(f"Captured current commit hash {version_id} for project {request.project_id}")
        except Exception:
            pass  # Git not initialized yet — leave version_id as None
        
        # 2. Insert message into database with the version_id (commit hash)
        conn = get_db()
        message_id = f'agent_{int(time.time())}_{uuid.uuid4().hex[:4]}'
        
        conn.execute(
            """INSERT INTO messages
               (id, project_id, container_id, role, content, code, version_id,
                timestamp, suggestions, tool_calls, image_paths, metadata, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message_id,
                request.project_id,
                request.container_id,
                request.role,
                request.content,
                request.code,
                version_id,
                datetime.now().isoformat(),
                json.dumps(request.suggestions) if request.suggestions else None,
                None,  # tool_calls
                None,  # image_paths
                json.dumps(request.metadata) if request.metadata else None,
                request.summary
            )
        )
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Agent message saved: {message_id} with version_id {version_id} for project {request.project_id}")

        
        return {
            "success": True,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to save agent message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save message: {str(e)}"
        )


@app.post("/vibecoding/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest, background_tasks: BackgroundTasks):
    # Get or create project ID at the start
    project_id = request.project_id or project_manager.generate_project_id()
    
    def build_vision_message(text: str, image_data_urls: list = None) -> dict:
        """Build an OpenAI/NVIDIA vision-format message with text + images."""
        if not image_data_urls:
            return {"role": "user", "content": text}
        content = []
        for data_url in image_data_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url}
            })
        content.append({"type": "text", "text": text})
        return {"role": "user", "content": content}

    from auth import get_db
    import uuid
    import json
    import time
    from datetime import datetime
    
    # Guaranteed User Message Persistence (Atomic)
    user_msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    user_timestamp = datetime.now().isoformat()
    try:
        conn = get_db()
        # Use INSERT OR IGNORE to prevent duplicate messages with same ID
        # This ensures we never overwrite an existing message
        conn.execute(
            """INSERT OR IGNORE INTO messages 
               (id, project_id, role, content, code, timestamp, image_paths, suggestions, tool_calls, metadata, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_msg_id, project_id, "user", request.prompt, None, user_timestamp,
             json.dumps(request.images) if request.images else None, 
             None, None, None, None)
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ User prompt verified and stored: {user_msg_id} at {user_timestamp} (Project: {project_id})")
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to save user prompt: {e}")
        # We continue so the user still gets a response, but we've logged the failure

    try:
        # ── Discuss mode: pure conversation, no code generation ──────────
        if request.discuss_mode:
            from prompts import CHAT_SYSTEM_PROMPT
            from datetime import datetime
            
            now = datetime.now()
            date_label = f"CURRENT DATE & TIME: {now.strftime('%A, %B %d, %Y %H:%M:%S')}\n\n"
            
            messages = [{"role": "system", "content": date_label + CHAT_SYSTEM_PROMPT}]
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append(build_vision_message(request.prompt, request.images))

            response = await ai_config.make_async_request(messages)
            ai_response = response["choices"][0]["message"].get("content", "") if "choices" in response else ""
            
            # Log the discuss mode interaction
            log_ai_interaction(request.prompt, ai_response, "discuss_mode")
            
            # Generate suggestions for discuss mode too
            suggestions = await generate_suggestions(ai_response, "", request.prompt)
            agent_summary = await summarize_content(ai_response, "")

            # Autonomously persist assistant message in discuss mode
            msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
            project_info = project_manager.get_project_info(project_id)
            container_id = project_info.get("container_id") if project_info else None
            
            conn = get_db()
            conn.execute(
                """INSERT INTO messages 
                    (id, project_id, container_id, role, content, code, version_id, timestamp, suggestions, tool_calls, image_paths, metadata, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, project_id, container_id, "assistant", ai_response, None, None,
                    datetime.now().isoformat(), 
                    json.dumps(suggestions) if suggestions else None,
                    None, None, None, agent_summary)
            )
            conn.commit()
            conn.close()

            return GenerateResponse(
                message=ai_response,
                code=None,
                project_id=project_id,
                version_id=None,
                preview_url=None,
                tool_calls_log=None,
                suggestions=suggestions,
                summary=agent_summary,
                message_id=msg_id
            )

        # ── Autonomous Flow: Delegating to Container-Side Resident Agent ──────
        logger.info(f"🦾 Triggering Autonomous Orchestrator for Project: {project_id}")

        workspace_dir = project_manager.artifacts_dir / project_id / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Ensure project metadata exists so manager knows what it's dealing with
        if not (workspace_dir / "metadata.json").exists():
            project_manager._ensure_workspace_metadata(project_id, workspace_dir, "initial")

        # 1. Compute the fixed preview URL for this project BEFORE starting the container.
        #    The URL is deterministic — it never changes for a given project_id.
        preview_url = project_manager.get_preview_url(project_id)

        # 2. Start or ensure the agent container is alive (volume-mounted to workspace)
        agent_url = project_manager.start_agent_container(
            api_key=ai_config.api_key,
            project_path=str(workspace_dir),
            project_id=project_id
        )

        if not agent_url:
            raise HTTPException(status_code=500, detail="Failed to initialize Autonomous Agent runtime.")

        # 3. Register the agent container port in the project registry so the proxy can route to it
        try:
            project_manager.agent_container.reload()
            port_bindings = project_manager.agent_container.ports.get('80/tcp', [])
            if port_bindings and port_bindings[0].get('HostPort'):
                host_port = port_bindings[0]['HostPort']
                project_manager._save_container_registry(project_id, host_port)
                logger.info(f"📋 Registered agent port {host_port} for project {project_id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not register agent port: {e}")

        # 4. Hand off task to the agent mailbox
        # Only include actual user messages as context (skip the agent's own acknowledgements)
        handoff_prompt = request.prompt
        if request.history:
            user_turns = [m for m in request.history if m.role == "user"]
            if user_turns:
                history_summary = "\n".join([f"User: {m.content[:200]}" for m in user_turns[-3:]])
                handoff_prompt = f"CONTEXT (previous turns):\n{history_summary}\n\nCURRENT REQUEST: {request.prompt}"

        logger.info(f"📤 Sending prompt to container for project {project_id}: {handoff_prompt[:100]}...")
        result = project_manager.send_request(handoff_prompt, project_id=project_id)
        logger.info(f"📬 Mailbox delivery result: {result}")

        # Let AI decide if this needs task breakdown or direct generation
        # This is more accurate than heuristics
        try:
            complexity_prompt = f"""Analyze this user request and determine if it needs task breakdown or direct generation.

USER REQUEST: {request.prompt}

Consider:
- Number of features/modules required
- Complexity of the application
- Whether it's a simple change or a full application
- If it involves multiple interconnected components
- Estimated number of files needed

Respond with a JSON object:
{{
  "complexity": "COMPLEX" or "SIMPLE",
  "reasoning": "Brief explanation",
  "estimated_files": number
}}

Guidelines:
- SIMPLE: Single feature, small app (1-5 files), or modification to existing code
- COMPLEX: Multiple modules, full platform (6+ files), or interconnected features

Examples:
- "Build a todo app" → {{"complexity": "SIMPLE", "reasoning": "Single feature app with basic CRUD", "estimated_files": 3}}
- "Add dark mode" → {{"complexity": "SIMPLE", "reasoning": "UI modification", "estimated_files": 2}}
- "Build a Captive Insurance Platform with IAM, policy admin, compliance" → {{"complexity": "COMPLEX", "reasoning": "Multiple modules with authentication, business logic, and compliance", "estimated_files": 25}}

Your analysis:"""

            complexity_response = await ai_config.make_async_request([
                {"role": "system", "content": "You are an expert at analyzing software requirements complexity. Always respond with valid JSON."},
                {"role": "user", "content": complexity_prompt}
            ], temperature=0.1)
            
            response_text = complexity_response["choices"][0]["message"].get("content", "").strip() if "choices" in complexity_response else "{}"
            logger.info(f"🤖 AI raw response: {response_text[:200]}")
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(0))
                is_complex_task = analysis.get("complexity", "SIMPLE").upper() == "COMPLEX"
                reasoning = analysis.get("reasoning", "")
                estimated_files = analysis.get("estimated_files", 0)
                
                logger.info(f"🤖 AI complexity analysis: {analysis.get('complexity')} - {reasoning} (est. {estimated_files} files) → is_complex_task={is_complex_task}")
            else:
                # Fallback if JSON parsing fails
                is_complex_task = "COMPLEX" in response_text.upper()
                logger.warning(f"Failed to parse JSON, using text match: {response_text[:100]} → is_complex_task={is_complex_task}")
            
        except Exception as e:
            logger.error(f"Failed to get AI complexity decision: {e}", exc_info=True)
            # Fallback to simple heuristic
            is_complex_task = len(request.prompt.split()) > 50 or request.prompt.count('\n') > 5
            logger.info(f"Using fallback heuristic → is_complex_task={is_complex_task}")
        
        if is_complex_task:
            # Don't send acknowledgment - let the agent send task breakdown directly
            # This keeps the loader active until tasks are ready
            logger.info("🎯 Complex task detected - skipping immediate acknowledgment, waiting for task breakdown")
            
            # Return a minimal response that keeps the loader active
            return GenerateResponse(
                message="",  # Empty message keeps loader active
                code=None,
                project_id=project_id,
                version_id="workspace",
                preview_url=preview_url,
                suggestions=[],
                summary="Analyzing requirement and generating task breakdown...",
                message_id=None,
                metadata={"awaiting_task_breakdown": True, "keep_loader_active": True}
            )

        # 5. Simple task — keep loader active; the agent sends all messages via WebSocket.
        #    This ensures the correct order: thinking block → "Thinking completed" → summary with suggestions.
        #    We deliberately skip generating an immediate ack here so the summary never jumps ahead.
        logger.info("✅ Simple task — returning empty response; agent will broadcast progress via WebSocket")
        return GenerateResponse(
            message="",           # Empty keeps the loader active in the frontend
            code=None,
            project_id=project_id,
            version_id="workspace",
            preview_url=preview_url,
            suggestions=[],
            summary="",
            message_id=None,
            metadata={"keep_loader_active": True}
        )

    except Exception as e:
        logger.error(f"Error in generate_code: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Determine a user-friendly error message based on the type of error
        error_msg = str(e)
        user_friendly_msg = "An unexpected error occurred while generating your project. Please try again or refine your prompt."
        
        if "NameError" in error_msg:
            user_friendly_msg = "A technical error occurred (Reference Error). Our team has been notified. Please try again in 1 minute."
        elif "HTTPException" in error_msg:
            user_friendly_msg = f"System error: {error_msg}. Please check your inputs or project settings."
            
        return GenerateResponse(
            message=user_friendly_msg,
            code=None,
            project_id=project_id,
            version_id=None,
            preview_url=None,
            tool_calls_log=None,
            suggestions=None
        )

@app.get("/vibecoding/api/health")
async def health_check():
    docker_available = project_manager.docker_client is not None
    public_host = os.getenv('PUBLIC_HOST', 'http://localhost')
    return {
        "status": "healthy",
        "docker_available": docker_available,
        "public_host": public_host
    }

@app.get("/vibecoding/api/projects/{project_id}/container-health")
async def container_health(project_id: str):
    """Check if the project's agent container is healthy and serving traffic."""
    if project_manager.docker_client is None:
        return {"healthy": False, "reason": "docker_unavailable"}

    port = get_container_port(project_id)

    # If not in registry yet, try to find the per-project agent container directly
    if not port:
        try:
            container = project_manager.docker_client.containers.get(f"vibecoding-agent-{project_id}")
            container.reload()
            if container.status == "running":
                port_bindings = container.ports.get('80/tcp', [])
                if port_bindings and port_bindings[0].get('HostPort'):
                    port = port_bindings[0]['HostPort']
                    project_manager._save_container_registry(project_id, port)
        except Exception:
            pass

    if not port:
        return {"healthy": False, "reason": "port_not_registered"}

    try:
        resp = requests.get(f"http://127.0.0.1:{port}", timeout=2)
        if resp.status_code < 500:
            return {"healthy": True, "http_status": resp.status_code}
        return {"healthy": False, "reason": f"http_{resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"healthy": False, "reason": "connection_refused"}
    except Exception as e:
        return {"healthy": False, "reason": str(e)}

# Project Management Endpoints

@app.post("/vibecoding/api/projects", response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest, user: dict = Depends(get_current_user)):
    try:
        user_id = user["id"]
        
        # If project_id is provided, check if it exists
        if request.project_id:
            project_info = project_manager.get_project_info(request.project_id)
            if project_info:
                # Project exists - check ownership
                if project_info.get("owner_id") is None:
                    # No owner, claim it for this user
                    project_info["owner_id"] = user_id
                    project_manager.update_project_metadata(request.project_id, project_info)
                    return ProjectResponse(**project_info)
                elif project_info.get("owner_id") == user_id:
                    # User owns it, return it
                    return ProjectResponse(**project_info)
                else:
                    # Someone else owns it
                    raise HTTPException(status_code=403, detail="Access denied")
            else:
                # Project doesn't exist with this ID - reject creation with custom ID
                raise HTTPException(status_code=404, detail="Project not found")
        
        # No project_id provided - create new project with generated ID
        project_id = project_manager.generate_project_id()
        project_manager.create_project_directory(project_id, metadata={
            "name": request.name,
            "description": request.description,
            "owner_id": user_id
        })
        
        project_info = project_manager.get_project_info(project_id)
        return ProjectResponse(**project_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects", response_model=ProjectListResponse)
async def list_projects(user: dict = Depends(get_current_user)):
    try:
        user_id = user["id"]
        projects = project_manager.list_projects(owner_id=user_id)
        return ProjectListResponse(projects=projects)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check ownership (Strict)
        if project_info.get("owner_id") is not None and project_info.get("owner_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
            
        return ProjectResponse(**project_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/vibecoding/api/projects/{project_id}/start")
async def start_project_container(project_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """
    Start (or wake up) the agent container for a project when the user opens it.
    Returns the fixed preview URL immediately — the container boots in the background.
    No-op if the container is already running.
    """
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        if project_info.get("owner_id") is not None and project_info.get("owner_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        # Only start if the workspace has files — no point starting an empty container
        workspace_dir = project_manager.artifacts_dir / project_id / "workspace"
        has_files = workspace_dir.exists() and any(
            f for f in workspace_dir.rglob("*")
            if f.is_file() and f.name not in ("metadata.json", ".gitignore") and ".git" not in f.parts
        )

        preview_url = project_manager.get_preview_url(project_id)

        if not has_files:
            return {"preview_url": preview_url, "started": False, "reason": "empty_workspace"}

        # Start container in background so the HTTP response returns immediately
        async def _start():
            try:
                agent_url = project_manager.start_agent_container(
                    api_key=ai_config.api_key,
                    project_path=str(workspace_dir),
                    project_id=project_id
                )
                if agent_url and project_manager.agent_container:
                    project_manager.agent_container.reload()
                    port_bindings = project_manager.agent_container.ports.get('80/tcp', [])
                    if port_bindings and port_bindings[0].get('HostPort'):
                        project_manager._save_container_registry(project_id, port_bindings[0]['HostPort'])
                        logger.info(f"🚀 Container started for project {project_id} on port {port_bindings[0]['HostPort']}")
            except Exception as e:
                logger.warning(f"Background container start failed for {project_id}: {e}")

        background_tasks.add_task(_start)

        return {"preview_url": preview_url, "started": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/versions")
async def list_versions(project_id: str):
    """List all Git branches for a project (version history shows branches)"""
    try:
        # Get branches from Git
        branches_result = git_manager.list_branches(project_id)
        
        if branches_result["status"] != "success":
            # Fallback to old version system if Git not initialized
            versions = project_manager.get_all_versions(project_id)
            return {"versions": versions}
        
        # Save current branch
        current_status = git_manager.get_status(project_id)
        current_branch = current_status.get("branch", "")
        
        versions = []
        for branch_info in branches_result.get("branches", []):
            if branch_info["type"] == "local":  # Only show local branches
                # Temporarily checkout branch to get its latest commit
                if branch_info["name"] != current_branch:
                    git_manager.checkout_branch(project_id, branch_info["name"])
                
                commits_result = git_manager.get_commit_history(project_id)
                commits = commits_result.get("commits", [])
                
                # Switch back
                if branch_info["name"] != current_branch and current_branch:
                    git_manager.checkout_branch(project_id, current_branch)
                
                # Format as version for frontend compatibility
                latest_commit = commits[0] if commits else None
                versions.append({
                    "version_id": branch_info["name"],
                    "prompt": f"Branch: {branch_info['name']}",
                    "created_at": latest_commit["date"] if latest_commit else "",
                    "is_branch": True,
                    "commit_count": len(commits),
                    "is_current": branch_info["is_current"]
                })
        
        return {"versions": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/versions/{version_id}/code")
async def get_version_code(project_id: str, version_id: str):
    try:
        code = project_manager.get_version_code(project_id, version_id)
        if not code:
            raise HTTPException(status_code=404, detail="Version not found")
        return {"code": code}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/versions/{version_id}/files")
async def get_version_files(project_id: str, version_id: str):
    """Get all files for a specific version (branch or commit)"""
    try:
        # Save current branch
        current_status = git_manager.get_status(project_id)
        current_branch = current_status.get("branch", "")
        
        # If version_id is a branch name, checkout that branch
        branches_result = git_manager.list_branches(project_id)
        is_branch = False
        
        if branches_result["status"] == "success":
            branch_names = [b["name"] for b in branches_result.get("branches", []) if b["type"] == "local"]
            if version_id in branch_names:
                is_branch = True
                if version_id != current_branch:
                    git_manager.checkout_branch(project_id, version_id)
        
        # Get files from workspace (current Git state)
        files = project_manager.get_workspace_files(project_id, max_files=100, max_chars_per_file=100000)
        
        # Switch back to original branch
        if is_branch and version_id != current_branch and current_branch:
            git_manager.checkout_branch(project_id, current_branch)
        
        if files is None or len(files) == 0:
            # Fallback to old version system
            files = project_manager.get_version_all_files(project_id, version_id)
            if files is None:
                raise HTTPException(status_code=404, detail="Version not found")
        
        return {"files": files, "version_id": version_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/projects/{project_id}/versions/{version_id}/preview")
async def create_preview(project_id: str, version_id: str):
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            raise HTTPException(
                status_code=503,
                detail="Docker not available. Please ensure Docker Desktop is installed and running."
            )

        # Check metadata exists before attempting container creation
        project_dir = project_manager.artifacts_dir / project_id
        if version_id == "workspace":
            metadata_file = project_dir / "workspace" / "metadata.json"
        else:
            metadata_file = project_dir / "versions" / version_id / "metadata.json"

        if not metadata_file.exists():
            # No code generated yet — return empty gracefully
            return {"preview_url": None}
        
        # Check if version_id is a branch name
        branches_result = git_manager.list_branches(project_id)
        is_branch = False
        
        if branches_result["status"] == "success":
            branch_names = [b["name"] for b in branches_result.get("branches", []) if b["type"] == "local"]
            if version_id in branch_names:
                is_branch = True
                # Checkout the branch
                current_status = git_manager.get_status(project_id)
                current_branch = current_status.get("branch", "")
                
                if version_id != current_branch:
                    git_manager.checkout_branch(project_id, version_id)
        
        # Switch container to workspace (which now reflects the checked out branch)
        preview_url = await project_manager.create_container_for_code(project_id, "workspace")
        
        if not preview_url:
            return {"preview_url": None}
        return {"preview_url": preview_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/vibecoding/api/projects/{project_id}/versions/{version_id}/preview")
async def stop_preview(project_id: str, version_id: str):
    try:
        project_manager.stop_container(project_id, version_id)
        return {"message": "Preview stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/download")
async def download_project(project_id: str):
    try:
        zip_path = project_manager.create_project_zip(project_id)
        if not zip_path:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return FileResponse(
            path=str(zip_path),
            filename=f"{project_id}_complete.zip",
            media_type="application/zip"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Chat Persistence Endpoints

@app.get("/vibecoding/api/projects/{project_id}/chat/{version_id}")
async def get_chat_history(project_id: str, version_id: str):
    try:
        history = await project_manager.get_chat_version(project_id, version_id)
        if history is None:
            return {"history": []}
            
        # Sanitize history to remove raw code markers if any leaked in
        sanitized_history = []
        import re
        for msg in history:
            content = msg.get("content", "")
            if msg.get("role") == "assistant" and content:
                # Split at markers
                parts = re.split(r'(?i)//\s*FILE:|#\s*FILE:|<!--\s*FILE:|//\s*PATCH:', content)
                clean_content = parts[0].strip()
                # If we cleaned everything out but there's metadata suggesting code was there, show a clean message
                if not clean_content and (len(parts) > 1 or msg.get("versionId")):
                    clean_content = "The codebase was updated."
                msg["content"] = clean_content
            sanitized_history.append(msg)
            
        return {"history": sanitized_history}
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/projects/{project_id}/chat/{version_id}")
async def save_chat_history(project_id: str, version_id: str, request: dict):
    try:
        history = request.get("history", [])
        await project_manager.save_chat_version(project_id, version_id, history)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Git Integration Endpoints

@app.post("/vibecoding/api/git/status")
async def git_status(request: GitRequest):
    try:
        status = git_manager.get_status(request.project_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/init")
async def git_init(request: GitRequest):
    try:
        # If remote_url is provided, we clone instead of just init
        if request.remote_url:
            if not request.token:
                return {"status": "error", "message": "Personal Access Token (PAT) is required."}
            
            # 1. Validate connection first
            if "dev.azure.com" in request.remote_url.lower() or "visualstudio.com" in request.remote_url.lower():
                val_res = await git_manager.validate_azure_devops_connection(request.remote_url, request.token)
            else:
                val_res = await git_manager.validate_github_connection(request.remote_url, request.token)
                
            if val_res["status"] == "error":
                return val_res
            
            # 2. Clone the repo
            result = git_manager.clone_repo(request.project_id, request.remote_url, request.token)
            
            # 3. If clone successful, initialize project workspace metadata
            if result["status"] == "success":
                workspace_dir = project_manager.artifacts_dir / request.project_id / "workspace"
                project_manager._ensure_workspace_metadata(request.project_id, workspace_dir, "initial_clone")
                # Also notify the manager to sync or prepare for code serving
                await project_manager.switch_to_workspace(request.project_id)
            
            return result
        else:
            # Default behavior: git init
            result = git_manager.init_repo(request.project_id)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/validate")
async def git_validate(request: GitRequest):
    try:
        if not request.remote_url:
            raise HTTPException(status_code=400, detail="Remote URL is required")
        if not request.token:
            return {"status": "error", "message": "Personal Access Token (PAT) is required."}
            
        if "dev.azure.com" in request.remote_url.lower() or "visualstudio.com" in request.remote_url.lower():
            result = await git_manager.validate_azure_devops_connection(request.remote_url, request.token)
        else:
            result = await git_manager.validate_github_connection(request.remote_url, request.token)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/add")
async def git_add(request: GitRequest):
    try:
        result = git_manager.add_files(request.project_id, request.files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/commit")
async def git_commit(request: GitRequest):
    try:
        if not request.message:
            raise HTTPException(status_code=400, detail="Commit message is required")
        result = git_manager.commit(request.project_id, request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/commits")
async def git_commits(request: GitRequest):
    try:
        result = git_manager.get_commit_history(request.project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/branch")
async def git_branch(request: GitRequest):
    try:
        if not request.branch_name:
            raise HTTPException(status_code=400, detail="Branch name is required")
        result = git_manager.create_branch(request.project_id, request.branch_name)
        # Switch container to workspace to reflect the new branch state
        await project_manager.switch_to_workspace(request.project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/checkout")
async def git_checkout(request: GitRequest):
    try:
        if not request.branch_name:
            raise HTTPException(status_code=400, detail="Branch name is required")
        result = git_manager.checkout_branch(request.project_id, request.branch_name)
        # Switch container to workspace to reflect the checked out branch
        await project_manager.switch_to_workspace(request.project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/branches")
async def git_branches(request: GitRequest):
    try:
        result = git_manager.list_branches(
            request.project_id,
            request.username,
            request.token
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/branches")
async def get_project_branches(project_id: str):
    """Get all Git branches for a project (for version history UI)"""
    try:
        result = git_manager.list_branches(project_id)
        if result["status"] != "success":
            return {"branches": []}
        
        branches = []
        for branch_info in result.get("branches", []):
            if branch_info["type"] == "local":  # Only show local branches
                # Get commit history for this branch
                current_status = git_manager.get_status(project_id)
                current_branch = current_status.get("branch", "")
                
                # Temporarily checkout branch to get its commits
                if branch_info["name"] != current_branch:
                    git_manager.checkout_branch(project_id, branch_info["name"])
                
                commits_result = git_manager.get_commit_history(project_id)
                commits = commits_result.get("commits", [])
                
                # Switch back to original branch
                if branch_info["name"] != current_branch and current_branch:
                    git_manager.checkout_branch(project_id, current_branch)
                
                branches.append({
                    "name": branch_info["name"],
                    "is_current": branch_info["is_current"],
                    "commit_count": len(commits),
                    "latest_commit": commits[0] if commits else None
                })
        
        return {"branches": branches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/branches/{branch_name}/commits")
async def get_branch_commits(project_id: str, branch_name: str):
    """Get all commits for a specific branch (checkpoints in chat)"""
    try:
        # Check project exists
        current_status = git_manager.get_status(project_id)
        if current_status.get("status") != "success":
            return {"commits": []}

        current_branch = current_status.get("branch", "")

        # Checkout the requested branch only if it differs and exists
        switched = False
        if branch_name != current_branch:
            checkout_result = git_manager.checkout_branch(project_id, branch_name)
            if checkout_result["status"] != "success":
                # Branch doesn't exist yet — return empty gracefully
                return {"commits": []}
            switched = True

        # Get commits
        commits_result = git_manager.get_commit_history(project_id)

        # Switch back to original branch
        if switched and current_branch:
            git_manager.checkout_branch(project_id, current_branch)

        return {"commits": commits_result.get("commits", []) if commits_result.get("status") == "success" else []}
    except Exception as e:
        logger.warning(f"get_branch_commits error (returning empty): {e}")
        return {"commits": []}

@app.post("/vibecoding/api/git/remote")
async def git_remote(request: GitRequest):
    try:
        if not request.remote_url:
            raise HTTPException(status_code=400, detail="Remote URL is required")
        result = git_manager.add_remote(request.project_id, request.remote_url, request.remote_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/push")
async def git_push(request: GitRequest):
    try:
        result = git_manager.push(
            request.project_id, 
            request.remote_name, 
            request.branch_name or "main",
            request.username,
            request.token
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _group_log_messages(raw_messages: list) -> list:
    """
    Group consecutive agent background-log messages (from ai-agent.py's report())
    into a single ThinkingBlock-compatible message for the frontend.

    Detection order (any match → it's a log):
      1. metadata.is_background_log == True  (set by ai-agent.py after this fix)
      2. container_id == 'vibecoding-ai-agent'  (legacy rows before the fix)
      3. metadata.type in log_types AND no code AND no task_plan  (extra safety net)

    Regular user messages, code-bearing assistant messages, and task-breakdown
    messages are NEVER grouped — they pass through unchanged.

    KEY BEHAVIOUR: if a log group sits at the TAIL of the message list with no
    terminal message (suggestions / code / task_plan) after it, we mark it as
    isThinking=True so the frontend keeps the spinner visible while the agent
    is still working.  Once a terminal message arrives the group is no longer at
    the tail and will be flushed with isThinking=False.
    """
    LOG_TYPES = {'status', 'info', 'thinking', 'action', 'celebration', 'question'}

    # Terminal message types / signals that mean the agent has finished a round.
    TERMINAL_TYPES = {'success', 'celebration', 'task_breakdown', 'task_execution_complete',
                      'task_execution_failed', 'task_execution_blocked'}

    def _is_log(msg):
        if msg.get('role') != 'assistant':
            return False
        # Messages with suggestions are terminal responses ("Great! Your changes are
        # working…", "Try these next:") — always show them as normal chat messages.
        suggestions = msg.get('suggestions')
        if suggestions and len(suggestions) > 0:
            return False
        meta = msg.get('metadata') or {}
        if meta.get('is_background_log'):
            return True
        if msg.get('container_id') == 'vibecoding-ai-agent':
            return True
        # Safety-net: agent status message with no code/task data
        if (meta.get('type') in LOG_TYPES
                and not msg.get('code')
                and not meta.get('task_plan')
                and meta.get('type') != 'task_breakdown'):
            return True
        return False

    def _is_terminal(msg):
        """True when this message signals the agent has finished its current task."""
        if msg.get('role') != 'assistant':
            return False
        meta = msg.get('metadata') or {}
        if meta.get('is_final_message') or meta.get('type') == 'success' or meta.get('status') == 'success':
            return True
        if meta.get('type') in TERMINAL_TYPES:
            return True
        if meta.get('task_plan') or meta.get('type') == 'task_breakdown':
            return True
        suggestions = msg.get('suggestions')
        if suggestions and len(suggestions) > 0:
            return True
        if msg.get('code'):
            return True
        content = msg.get('content', '')
        if '[AGENT] VERIFICATION' in content or 'Your app is live' in content or 'No API endpoint tests' in content or 'API endpoint tests' in content:
            return True
        return False

    result = []
    log_buffer = []
    group_id = None
    group_ts = None

    def _flush(is_tail: bool = False):
        nonlocal log_buffer, group_id, group_ts
        if not log_buffer:
            return
        has_error = any(l['level'] == 'error' for l in log_buffer)
        # If this group is at the tail and no terminal message has followed,
        # keep isThinking=True so the frontend spinner stays visible.
        is_thinking = is_tail and not has_error
        result.append({
            'id': group_id,
            'role': 'assistant',
            'content': log_buffer[-1]['message'],
            'timestamp': group_ts,
            'code': None,
            'suggestions': None,
            'metadata': {
                'type': 'background_execution',
                'is_background_log': True,
                'grouped': True,
                'has_error': has_error,
            },
            'thinkingLogs': log_buffer.copy(),
            'isThinking': is_thinking,
        })
        log_buffer = []
        group_id = None
        group_ts = None

    # Track whether the last non-log message was terminal so we can decide
    # whether a trailing log group should stay in "thinking" state.
    seen_terminal_after_last_flush = False

    for msg in raw_messages:
        if _is_log(msg):
            if group_id is None:
                group_id = msg['id']
                group_ts = msg.get('timestamp')
                seen_terminal_after_last_flush = False  # reset for new group
            meta = msg.get('metadata') or {}
            mtype = meta.get('type', 'status')
            level = ('error' if mtype == 'error'
                     else 'success' if mtype in ('success', 'celebration')
                     else 'info')
            log_buffer.append({
                'message': msg.get('content', ''),
                'timestamp': msg.get('timestamp'),
                'level': level,
            })
        else:
            # Flush current log group as NOT tail (a real message follows it)
            _flush(is_tail=False)
            result.append(msg)
            if _is_terminal(msg):
                seen_terminal_after_last_flush = True

    # Final flush — this group IS at the tail.
    # isThinking = True only if we haven't seen a terminal message after the
    # last log group started (meaning the agent is still mid-task).
    _flush(is_tail=not seen_terminal_after_last_flush)
    return result


@app.get("/vibecoding/api/projects/{project_id}/messages")
async def get_project_messages(project_id: str, background_tasks: BackgroundTasks):
    from auth import get_db
    conn = get_db()
    try:
        # Order by ROWID (SQLite's internal row number) which represents insertion order
        # This is the most reliable way to get messages in the order they were created
        # regardless of timestamp or ID issues
        rows = conn.execute(
            "SELECT rowid, * FROM messages WHERE project_id = ? ORDER BY rowid ASC",
            (project_id,)
        ).fetchall()
        
        messages = []
        startup_messages = [
            '👋 VibeCoding Agent is online and ready!'
        ]
        
        for row in rows:
            msg = dict(row)
            # Remove rowid from the message dict as it's just for ordering
            msg.pop('rowid', None)
            
            # Skip startup messages - they're just informational and shouldn't persist
            if msg.get('role') == 'assistant' and any(startup_msg in msg.get('content', '') for startup_msg in startup_messages):
                continue
            
            # Parse JSON fields
            for field in ["suggestions", "tool_calls", "image_paths", "metadata"]:
                if msg.get(field):
                    try:
                        msg[field] = json.loads(msg[field])
                    except:
                        pass
            
            # Map image_paths to images for frontend compatibility
            if "image_paths" in msg:
                msg["images"] = msg.pop("image_paths")
            
            # Match frontend format
            if msg.get("role") == "assistant":
                msg["code"] = msg.get("code")
                # Trigger lazy summarization if missing and has code
                if not msg.get("summary") and msg.get("code"):
                    background_tasks.add_task(lazy_summarize_message, msg["id"], msg["content"], msg["code"])
            messages.append(msg)

        # ── Group consecutive agent log messages into ThinkingBlock format ──────
        # This ensures that after a page reload the logs are still shown collapsed
        # inside a single ThinkingBlock rather than as individual chat messages.
        messages = _group_log_messages(messages)
            
        return {"messages": messages}
    finally:
        conn.close()


@app.delete("/vibecoding/api/projects/{project_id}/messages")
async def delete_project_messages(
    project_id: str,
    after_index: Optional[int] = None,
    after_message_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Delete messages after a certain index or message ID to sync conversation history with Git restore"""
    from auth import get_db
    conn = get_db()
    try:
        if after_message_id:
            # Find the rowid of the message with after_message_id
            row = conn.execute(
                "SELECT rowid FROM messages WHERE project_id = ? AND id = ?",
                (project_id, after_message_id)
            ).fetchone()
            if row:
                target_rowid = row[0]
                conn.execute(
                    "DELETE FROM messages WHERE project_id = ? AND rowid >= ?",
                    (project_id, target_rowid)
                )
                conn.commit()
                logger.info(f"🗑️ Deleted messages starting from message ID {after_message_id} (rowid >= {target_rowid}) for project {project_id}")
                return {"status": "success", "deleted_by": "message_id"}
            else:
                return {"status": "error", "message": f"Message ID {after_message_id} not found"}
        
        elif after_index is not None:
            # Retrieve rowids in insertion order (rowid ASC)
            rows = conn.execute(
                "SELECT rowid FROM messages WHERE project_id = ? ORDER BY rowid ASC",
                (project_id,)
            ).fetchall()
            
            rowids = [row[0] for row in rows]
            
            # If after_index is within range, delete all messages with rowid greater than the rowid at after_index
            if 0 <= after_index < len(rowids):
                target_rowid = rowids[after_index]
                conn.execute(
                    "DELETE FROM messages WHERE project_id = ? AND rowid > ?",
                    (project_id, target_rowid)
                )
                conn.commit()
                logger.info(f"🗑️ Deleted messages after index {after_index} (rowid > {target_rowid}) for project {project_id}")
                return {"status": "success", "deleted_count": len(rowids) - 1 - after_index}
            
        return {"status": "success", "message": "No deletion parameters matched, no messages deleted"}
    except Exception as e:
        logger.error(f"❌ Failed to delete messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/vibecoding/api/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str):
    """Get tasks from the .vibecoding_tasks.json file in the workspace"""
    try:
        # Path to the tasks file in the workspace
        workspace_dir = ARTIFACTS_DIR / project_id / "workspace"
        tasks_file = workspace_dir / ".vibecoding_tasks.json"
        context_file = workspace_dir / ".vibecoding_context.json"
        
        if not tasks_file.exists():
            return {"tasks": [], "total_tasks": 0}
        
        with open(tasks_file, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        
        # Try to get project summary from context file
        project_summary = ""
        if context_file.exists():
            try:
                with open(context_file, 'r', encoding='utf-8') as f:
                    context = json.load(f)
                    project_summary = context.get('project_summary', '')
            except Exception as e:
                logger.warning(f"Failed to read context file: {e}")
        
        # Calculate progress
        total_tasks = len(tasks)
        completed_count = sum(1 for task in tasks if task.get('status') == 'completed')
        pending_count = sum(1 for task in tasks if task.get('status') == 'pending')
        failed_count = sum(1 for task in tasks if task.get('status') == 'failed')
        
        return {
            "project_summary": project_summary,
            "tasks": tasks,
            "total_tasks": total_tasks,
            "completed_count": completed_count,
            "pending_count": pending_count,
            "failed_count": failed_count,
            "progress_percentage": round((completed_count / total_tasks * 100)) if total_tasks > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error fetching tasks for project {project_id}: {e}")
        return {"tasks": [], "total_tasks": 0, "error": str(e)}


@app.post("/vibecoding/api/chat/new")
async def start_new_chat(request: GitRequest):
    try:
        project_id = request.project_id
        if not request.chat_version:
            raise HTTPException(status_code=400, detail="chat_version is required")
            
        # 1. Archive current workspace to a version folder before branching
        try:
            prev_v = int(request.chat_version) - 1
            project_manager.archive_workspace_to_version(project_id, f"Archive of Chat v{prev_v}")
        except Exception as e:
            logger.warning(f"Failed to archive workspace: {e}")

        # 2. Create new branch
        branch_name = f"chat-v{request.chat_version}"
        
        workspace_dir = git_manager._get_workspace_dir(project_id)
        if not (workspace_dir / ".git").exists():
            git_manager.init_repo(project_id)
            
        result = git_manager.create_branch(project_id, branch_name)
        # Switch container to workspace to reflect the new branch
        await project_manager.switch_to_workspace(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/git/checkpoint")
async def git_checkpoint(request: GitRequest):
    """Switch to a specific version's checkpoint (commit)"""
    try:
        project_id = request.project_id
        version_id = request.version_id
        
        if not version_id:
            raise HTTPException(status_code=400, detail="version_id is required")
        
        # First, verify the commit exists in the repository
        verify_res = git_manager._run_git_command(project_id, ["cat-file", "-t", version_id])
        if verify_res["status"] != "success" or "commit" not in verify_res["stdout"]:
            # Commit doesn't exist, try to find it by searching commit messages
            search_res = git_manager._run_git_command(project_id, ["log", "--all", f"--grep={version_id}", "--pretty=format:%H", "-n", "1"])
            if search_res["status"] == "success" and search_res["stdout"].strip():
                version_id = search_res["stdout"].strip()
            else:
                return {"status": "error", "message": f"Checkpoint {version_id[:8]} not found in repository"}
        
        # Check if there are uncommitted changes
        status = git_manager.get_status(project_id)
        has_changes = status.get("modified_files") or status.get("added_files") or status.get("deleted_files") or status.get("untracked_files")
        
        if has_changes:
            # Stash changes so we can restore them later if needed
            stash_res = git_manager._run_git_command(project_id, ["stash", "push", "-u", "-m", "Auto-stash before checkpoint view"])
            if stash_res["status"] != "success":
                # If stash fails, force discard (likely just metadata.json)
                git_manager._run_git_command(project_id, ["reset", "--hard"])
                git_manager._run_git_command(project_id, ["clean", "-fd"])
            
        # Checkout or Restore the commit
        if request.restore:
            logger.info(f"🔄 Performing Git Restore (hard reset) to: {version_id} via container")
            res = project_manager.send_request(f"__SYS_CMD_RESTORE__:{version_id}", project_id=project_id)
            if not res.get("success"):
                raise HTTPException(status_code=500, detail="Failed to send restore command to container")
            return {"status": "success", "message": "Restore command queued to container"}
        else:
            checkout_res = git_manager.checkout_commit(project_id, version_id)
        
        if checkout_res["status"] == "success":
            # Tell the supervisor to switch the container to the workspace
            await project_manager.switch_to_workspace(project_id)
            return checkout_res
            
        return {"status": "error", "message": f"Failed to checkout commit: {checkout_res.get('stderr', 'Unknown error')}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/vibecoding/api/cleanup")
async def cleanup_containers():
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            return {"message": "Docker not available - no containers to clean up"}
        
        project_manager.cleanup_old_containers()
        return {"message": "Cleanup completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vibecoding/api/projects/{project_id}/frozen-files")
async def get_frozen_files(project_id: str, user: dict = Depends(get_current_user)):
    """Get list of frozen files for a project"""
    try:
        frozen_files = project_manager.get_frozen_files(project_id)
        return {"frozen_files": frozen_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Summarization Endpoint for CXO Reports ---
class SummaryRequest(BaseModel):
    content: str
    code: Optional[str] = None

@app.post("/vibecoding/api/summarize")
async def summarize_changes(request: SummaryRequest, user=Depends(get_current_user)):
    try:
        summary = await summarize_content(request.content, request.code)
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        return {"summary": "Modifications completed based on your specific requirements."}
@app.post("/vibecoding/api/projects/{project_id}/frozen-files")
async def set_file_frozen(project_id: str, request: dict, user: dict = Depends(get_current_user)):
    """Set or unset frozen status for a file"""
    try:
        file_path = request.get("file_path")
        frozen = request.get("frozen", True)
        
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path is required")
        
        success = project_manager.set_file_frozen(project_id, file_path, frozen)
        
        if success:
            return {
                "success": True,
                "file_path": file_path,
                "frozen": frozen,
                "message": f"File {'frozen' if frozen else 'unfrozen'} successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update frozen status")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_container_port(project_id: str) -> str:
    """Get the container port for a project by reading its container info"""
    try:
        # Use the same artifacts_dir as project_manager to ensure consistency
        registry_file = project_manager.artifacts_dir / '.container_registry.json'
        logger.debug(f"Looking for registry at: {registry_file.absolute()}")
        
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                container_name = f"vibecoding_{project_id}"
                logger.debug(f"Registry contents: {list(registry.keys())}")
                if container_name in registry:
                    port = registry[container_name]['port']
                    logger.info(f"✅ Found container port for {project_id}: {port}")
                    return port
                else:
                    logger.warning(f"⚠️ Container {container_name} not in registry")
                    logger.warning(f"   Available containers: {list(registry.keys())}")
        else:
            logger.warning(f"⚠️ Registry file does not exist: {registry_file.absolute()}")
    except Exception as e:
        logger.error(f"❌ Error reading container registry: {e}")
        import traceback
        traceback.print_exc()
    return None




# ─── Catch-all Proxy for Absolute Assets ──────────────────────────────────────
# CRITICAL: This MUST stay at the very end of the file to avoid intercepting other routes
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def asset_fallback_proxy(path: str, request: Request):
    """
    Handles requests for absolute asset paths (e.g. /assets/foo.js) that are loaded
    by the container app and use the Referer header to identify which project they belong to.
    React Router paths (/vibecoding/a/*, /vibecoding/login, etc.) are NOT handled here.
    """
    # Ignore React Router frontend paths — these should never reach the backend
    react_router_prefixes = ("vibecoding/a/", "vibecoding/login", "vibecoding/signup",
                             "vibecoding/forgot-password", "vibecoding/reset-password",
                             "vibecoding/", )
    if not path or path in ("vibecoding", "vibecoding/") or any(path.startswith(p) for p in react_router_prefixes):
        raise HTTPException(status_code=404)

    referer = request.headers.get("referer", "")
    if not referer:
        raise HTTPException(status_code=404)

    # Only handle assets whose referer is a container app URL
    match = _re.search(r'/(?:vibecoding/)?app/([a-zA-Z0-9_-]+)/', referer)
    if not match:
        raise HTTPException(status_code=404)

    project_token = match.group(1)
    
    # Get container port for this project
    port = get_container_port(project_token)
    if not port:
        raise HTTPException(status_code=404)

    target_url = f"http://127.0.0.1:{port}/{path}"
    query_params = request.scope.get("query_string", b"").decode()
    if query_params:
        target_url += f"?{query_params}"
    
    # Force no-gzip for assets as well to avoid compression issues in proxy
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    headers["accept-encoding"] = "identity"

    try:
        session = get_proxy_session()
        resp = session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=await request.body(),
            allow_redirects=False,
            timeout=(5, 30)
        )
        
        # Decompress if necessary
        body = resp.content
        encoding = resp.headers.get("content-encoding", "").lower()
        if "gzip" in encoding:
            import gzip as _gzip
            try:
                body = _gzip.decompress(body)
                print(f"📦 Decompressed gzipped asset: {len(resp.content)} → {len(body)} bytes")
            except Exception as e:
                print(f"⚠️ Gzipped asset decompression failed: {e}")

        excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive"]
        response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}
        response_headers["content-length"] = str(len(body))
        
        return StreamingResponse(
            iter([body]), 
            status_code=resp.status_code, 
            headers=response_headers,
            media_type=resp.headers.get("content-type")
        )
    except Exception as e:
        print(f"❌ Fallback proxy error for {target_url}: {e}")
        raise HTTPException(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)