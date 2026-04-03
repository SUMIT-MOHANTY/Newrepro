import json
import hashlib
from pathlib import Path
import asyncio
import os
import uuid
import re as _re
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Response
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

import logging
logging.basicConfig(level=logging.INFO)
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
            <p style="margin: 0; opacity: 0.7;">Container is starting in the background.</p>
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
    This allows the frontend to use a single persistent URL while containers use ephemeral ports.
    """
    # Forward query parameters
    query_params = request.scope.get("query_string", b"").decode()
    
    # 1. First, check if the container is even ready (has a port)
    port = get_container_port(project_token)
    if not port:
        # If it's a main page request, return Warming Up instead of 404
        if not path or path.endswith((".html", "/")):
            logger.info(f"🏘️ Container for {project_token} not registered yet. Returning 'Warming up' HTML.")
            return HTMLResponse(content=get_warming_up_html())
        raise HTTPException(status_code=404, detail=f"Container for {project_token} not found or not running.")

    target_base = f"http://127.0.0.1:{port}"
    target_url = f"{target_base}/{path}"
    if query_params:
        target_url += f"?{query_params}"

    # Prepare headers — exclude hop-by-hop and connection-management headers
    excluded_outgoing = ["host", "content-length", "connection", "keep-alive", "proxy-connection", "upgrade"]
    headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded_outgoing}
    headers["accept-encoding"] = "identity"  # Prefer uncompressed for stable proxying
    
    # 1. First, wait for container to be ready (Pre-flight)
    is_ready = await wait_for_container_ready(target_base, max_attempts=15, delay=1.0)
    if not is_ready:
        print(f"⚠️ Container {target_base} still not responding after 15s. Proceeding anyway.")

    # 2. Proxy request with internal retries to avoid "Connection Reset" JSON in iframe
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
            
            # Prepare response headers
            excluded_response = ["content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive", "x-frame-options", "content-security-policy"]
            response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_response}
            
            # Allow iframe embedding
            response_headers["X-Frame-Options"] = "ALLOWALL"
            response_headers["Access-Control-Allow-Origin"] = "*"

            # Handle content
            final_content = resp.content
            encoding = resp.headers.get("content-encoding", "").lower()
            if "gzip" in encoding:
                import gzip as _gzip
                try:
                    final_content = _gzip.decompress(final_content)
                except Exception:
                    pass

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
            error_msg = str(e).lower()
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 0.5
                print(f"⏳ Connection error (attempt {attempt + 1}): {error_msg}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            break
        except Exception as e:
            last_error = e
            break

    # 3. If we're here, all retries failed. 
    # To avoid showing raw JSON error to user, return a friendly "Warming up" HTML 
    # ONLY if it's likely a main page request (no path or html-like path)
    if not path or path.endswith((".html", "/")):
        logger.info(f"🏘️ Proxy failed. Returning 'Warming up' HTML instead of JSON error.")
        return HTMLResponse(content=get_warming_up_html(), status_code=200)

    # For assets/API calls that failed, return the 502 as before
    logger.error(f"❌ Final proxy failure for {target_url}: {last_error}")
    raise HTTPException(status_code=502, detail=f"Proxy error: {str(last_error)}")


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

class GenerateResponse(BaseModel):
    message: str
    code: Optional[str] = None
    project_id: str
    version_id: Optional[str] = None
    preview_url: Optional[str] = None
    tool_calls_log: Optional[List[dict]] = None
    suggestions: Optional[List[str]] = None
    message_id: Optional[str] = None
    version_id: Optional[str] = None
    preview_url: Optional[str] = None
    tool_calls_log: Optional[List[dict]] = None
    suggestions: Optional[List[str]] = None

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
    """Verify HMAC-signed handoff token and return payload."""
    parts = token_str.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError("Malformed handoff token")
    payload_b64, sig = parts
    expected_sig = _hmac.new(HANDOFF_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expected_sig, sig):
        raise ValueError("Invalid handoff token signature")
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    payload = json.loads(_base64.urlsafe_b64decode(payload_b64))
    if payload.get("exp", 0) < int(_time_mod.time()):
        raise ValueError("Handoff token expired")
    return payload


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

    conn = get_auth_db()
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
            password = generate_random_password()
            password_hash, salt = hash_password(password)
            avatar_color = generate_avatar_color(email)
            from datetime import datetime
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
            project_manager.update_project_metadata(project_token, existing)
            project_info = existing
        else:
            project_name = project_context.get("project_name") or f"Project {project_token[:8]}"
            project_manager.create_project_directory(project_token, metadata={
                "name": project_name,
                "description": project_context.get("brd_summary", ""),
                "owner_id": user_id,
            })
            new_project = project_manager.get_project_info(project_token)
            if new_project and project_context:
                new_project["brd_context"] = project_context
                project_manager.update_project_metadata(project_token, new_project)
            project_info = project_manager.get_project_info(project_token)

    return {
        "token": token,
        "user": user_data,
        "project": project_info,
        "message": "SSO login successful",
    }


@app.get("/vibecoding/api")
async def root():
    return {"message": f"{APP_NAME} API is running"}

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
               (id, project_id, container_id, role, content, code, version_id, timestamp, suggestions, tool_calls, image_paths, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.id, project_id, container_id, request.role, request.content, request.code, 
             request.version_id, request.timestamp, 
             json.dumps(request.suggestions) if request.suggestions else None,
             json.dumps(request.tool_calls) if request.tool_calls else None,
             json.dumps(request.images) if request.images else None,
             None)
        )
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()


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
    
    # Autonomously persist user message immediately
    try:
        user_msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        conn = get_db()
        conn.execute(
            """INSERT INTO messages 
               (id, project_id, role, content, timestamp, image_paths)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_msg_id, project_id, "user", request.prompt, datetime.now().isoformat(),
             json.dumps(request.images) if request.images else None)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to auto-save user message: {e}")

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
            
            # Autonomously persist assistant message in discuss mode
            try:
                from auth import get_db
                import uuid
                import time
                msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
                project_info = project_manager.get_project_info(project_id)
                container_id = project_info.get("container_id") if project_info else None
                
                conn = get_db()
                conn.execute(
                    """INSERT INTO messages 
                       (id, project_id, container_id, role, content, code, version_id, timestamp, suggestions, tool_calls, image_paths, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (msg_id, project_id, container_id, "assistant", ai_response, None, None,
                     datetime.now().isoformat(), 
                     json.dumps(suggestions) if suggestions else None,
                     None, None, None)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to auto-save discuss message: {e}")

            return GenerateResponse(
                message=ai_response,
                code=None,
                project_id=project_id,
                version_id=None,
                preview_url=None,
                tool_calls_log=None,
                suggestions=suggestions
            )

        # Get existing code in the workspace - Increased limits for better full-stack context
        workspace_files = project_manager.get_workspace_files(project_id, max_files=100, max_chars_per_file=4000)
        has_existing_code = len(workspace_files) > 0

        # Identify "Chat" intent for short/simple prompts or greetings to keep context light
        simple_chat_words = {'hi', 'hello', 'hey', 'yo', 'sup', 'how are you', 'howdy', 'greeting', 'thanks', 'thank you'}
        p_clean = request.prompt.strip().lower().strip('?!.')
        is_simple_intent = p_clean in simple_chat_words or (len(p_clean) < 12 and not any(c in p_clean for c in ['/', '.', '<', '>', '{', '}']))
        
        # If simple intent, we skip the heavy file content to avoid "over-engineering" the response,
        # but we KEEP the project tree/structure so the AI still knows "where" it is.
        if is_simple_intent:
            workspace_files = {} # Keep codebase light
        
        # Get full project structure (all paths recursively) to help with architectural understanding
        all_paths = project_manager.get_all_workspace_paths(project_id)
        project_tree_str = "\n".join([f"- {p}" for p in all_paths]) if all_paths else "No files yet"
        
        # Detect architecture/stack
        project_info = project_manager.get_project_info(project_id) or {}
        runtime = project_info.get("runtime", "universal")
        arch_type = f"Architecture Detect: {runtime.upper()} project structure."
        
        # Get frozen files list
        frozen_files = project_manager.get_frozen_files(project_id)
        frozen_files_str = "\n".join([f"- {path} (READ-ONLY)" for path in frozen_files]) if frozen_files else "None"

        # Inject BRD project context if available
        brd_context_str = ""
        project_meta = project_manager.get_project_info(project_id)
        brd_data = project_meta.get("brd_context") if project_meta else None
        
        if brd_data:
            parts = []
            if brd_data.get("project_name"):
                parts.append(f"Project Name: {brd_data['project_name']}")
            if brd_data.get("classification"):
                parts.append(f"Governance Classification: {brd_data['classification']}")
            if brd_data.get("recommendation"):
                parts.append(f"Governance Recommendation: {brd_data['recommendation']}")
            if brd_data.get("brd_summary"):
                parts.append(f"BRD Summary: {brd_data['brd_summary']}")
            if brd_data.get("agent_analysis"):
                parts.append(f"Agent Analysis: {brd_data['agent_analysis']}")
            if parts:
                brd_context_str = "\n\n📄 PROJECT CONTEXT (from BRD Analyzer):\n" + "\n".join(parts) + "\n"

        # Build conversation history with appropriate system prompt
        from prompts import get_dynamic_system_prompt
        
        # Determine extra directives based on current user prompt intent
        extra_directives = ""
        p_lower = request.prompt.lower()
        if any(word in p_lower for word in ['redesign', 'premium', 'modernize', 'professional', 'ux', 'ui']):
            extra_directives = "🎯 DESIGN UPGRADE: The user wants a premium, modern, or OS-like redesign. Use deep glassmorphism, subtle micro-animations on hover, and custom layouts that fill the entire screen. Ensure it is RESPONSIVE and mobile-ready."
        elif any(word in p_lower for word in ['simple', 'clean', 'minimalist']):
            extra_directives = "🎯 DESIGN DIRECTIVE: Create a clean, minimalist, but high-fidelity 'Apple-style' UI. High contrast, precise typography (Inter), and plenty of whitespace while still feeling complete."

        # Pass in all data to the dynamic prompt factory
        system_prompt = get_dynamic_system_prompt(
            mode="chat" if (request.discuss_mode or is_simple_intent) else ("edit" if has_existing_code else "generate"),
            frozen_files=frozen_files_str,
            file_list=project_tree_str,
            current_files="".join([f"\n\n// FILE: {path}\n{content}" for path, content in workspace_files.items()]) if (has_existing_code and not is_simple_intent) else "",
            brd_context=brd_data,
            extra_directives=f"{arch_type}\n{extra_directives}" if not is_simple_intent else ""
        )
        
        from datetime import datetime
        now = datetime.now()
        date_context = f"Current date and time: {now.strftime('%A, %B %d, %Y %H:%M:%S')} (UTC{now.astimezone().strftime('%z')})\n\n"
        messages = [{"role": "system", "content": date_context + system_prompt}]
        for msg in request.history:
            messages.append({"role": msg.role, "content": msg.content})
        
        prompt_with_instructions = request.prompt
        if has_existing_code:
            prompt_with_instructions = f"{request.prompt}\n\nIMPORTANT: If this is a small change, output ONLY the files that need to be modified. Do NOT regenerate the entire codebase."
        
        messages.append(build_vision_message(prompt_with_instructions, request.images))

        # Log AI request
        log_prompt = f"User Request: {request.prompt}"
        response = await make_request_with_tools(messages)
        tool_calls_log = response.pop("_tool_calls_log", None)
        
        if "choices" in response and len(response["choices"]) > 0:
            ai_response = response["choices"][0]["message"].get("content") or ""
        else:
            raise Exception("Invalid response format from AI API")
        
        # Fallback for empty responses, especially common during safety filtering or confusion with simple greetings
        if not ai_response.strip() and is_simple_intent:
            ai_response = "Hello! I'm here to help you build or refine your project. What would you like to work on first?"
        
        log_ai_interaction(log_prompt, ai_response, "main_generation")

        # Extract code
        import re as _re
        ai_response = _preprocess_ai_response(ai_response)
        
        has_patch_markers = bool(_re.search(r'//\s*PATCH:\s*', ai_response))
        has_raw_search_replace = (not has_patch_markers and bool(_re.search(r'<<<\s*SEARCH', ai_response)) and bool(_re.search(r'<<<\s*REPLACE', ai_response)))
        has_markers = bool(_re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', ai_response))

        code = None
        if has_patch_markers or has_raw_search_replace:
            code = ai_response
        elif has_markers:
            fenced_blocks = _re.findall(r'```[a-zA-Z]*\n?(.*?)```', ai_response, _re.DOTALL)
            fenced_code = "\n\n".join(b.strip() for b in fenced_blocks).strip() if fenced_blocks else ""
            if fenced_code and _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', fenced_code):
                code = fenced_code
            else:
                cleaned = _re.sub(r'```[a-zA-Z]*\n?', '', ai_response).replace('```', '')
                first_marker = _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', cleaned)
                code = cleaned[first_marker.start():].strip() if first_marker else cleaned.strip()
        else:
            blocks = _re.findall(r'```[a-zA-Z]*\n?(.*?)```', ai_response, _re.DOTALL)
            if blocks:
                import re
                code_match = re.search(r"```(?:\w+)?\n?(.*?)\n?```", ai_response, re.DOTALL)
                code = code_match.group(1).strip() if code_match else "\n\n".join(blocks).strip()
            elif '<html' in ai_response.lower() or '<!doctype' in ai_response.lower():
                code = ai_response.strip()

        # Extract message 
        message = ai_response
        if code:
            if has_patch_markers:
                message = _re.split(r'//\s*PATCH:\s*', ai_response)[0].strip()
            elif has_raw_search_replace:
                message = _re.split(r'<<<\s*SEARCH', ai_response)[0].strip()
            elif has_markers:
                parts = ai_response.split("```")
                preamble = parts[0].strip()
                epilogue = parts[-1].strip() if len(parts) >= 3 else ""
                message = f"{preamble}\n\n{epilogue}".strip() if (epilogue and not _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', epilogue)) else preamble
            else:
                message = ai_response.split("```")[0].strip()
        message = message.replace('```', '').strip()

        # Generate suggestions before persistence
        suggestions = await generate_suggestions(message, code or "", request.prompt)

        # ── Persistence: Save AI response to DB ──────────
        try:
            from auth import get_db
            import uuid
            import json
            import time
            msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
            
            # Get current container ID for logging
            project_info = project_manager.get_project_info(project_id)
            container_id = project_info.get("container_id") if project_info else None
            
            conn = get_db()
            conn.execute(
                """INSERT INTO messages 
                   (id, project_id, container_id, role, content, code, version_id, timestamp, suggestions, tool_calls, image_paths, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, project_id, container_id, "assistant", message, code, 
                 None, # version_id will be updated after git commit if needed
                 datetime.now().isoformat(), 
                 json.dumps(suggestions) if suggestions else None,
                 json.dumps(tool_calls_log) if tool_calls_log else None,
                 None,
                 None)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to auto-save AI response: {e}")

        # Save and Prepare Response
        version_id = None
        preview_url = None
        
        if code:
            try:
                version_id, _ = project_manager.update_workspace_from_code(project_id, code, request.prompt)
            except ValueError as e:
                if str(e).startswith("FROZEN_FILES_VIOLATION:"):
                    frozen_files_str = str(e).split(":", 1)[1]
                    violation_list = "\n".join([f"  - {f}" for f in list(set(frozen_files_str.split(",")))])
                    error_message = f"Cannot complete this request. The following files are frozen:\n\n{violation_list}\n\nPlease unfreeze them if you want to make changes."
                    return GenerateResponse(message=error_message, code=None, project_id=project_id, version_id=None, preview_url=None, tool_calls_log=tool_calls_log, suggestions=None)
                raise
            
            # Save chat history
            try:
                status = git_manager.get_status(project_id)
                current_branch = status.get("branch", "main") if status["status"] == "success" else "main"
                history = [{"role": msg.role, "content": msg.content} for msg in request.history]
                history.append({"role": "user", "content": request.prompt})
                history.append({"role": "assistant", "content": message})
                await project_manager.save_chat_version(project_id, current_branch, history)
            except Exception as e:
                print(f"Failed to save chat history: {e}")
            
            # Final Response setup
            preview_url = project_manager.get_preview_url(project_id)
            if project_manager.docker_client:
                project_manager._current_user_prompt = request.prompt
                background_tasks.add_task(project_manager.create_container_for_code, project_id, "workspace")
                logger.info(f"🚀 Started container for {project_id} in background")
                
                # Kick off verification background task
                if code and preview_url:
                    background_tasks.add_task(
                        verify_generated_preview, 
                        project_id, 
                        msg_id, 
                        preview_url, 
                        request.prompt, 
                        code
                    )
            else:
                preview_url = None
        
        # Return unified response
        return GenerateResponse(
            message=message,
            code=code,
            project_id=project_id,
            version_id=version_id,
            preview_url=preview_url,
            tool_calls_log=tool_calls_log,
            suggestions=suggestions,
            message_id=msg_id
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
    """Check if a project's container is healthy and serving HTTP requests."""
    port = get_container_port(project_id)
    if not port:
        return {"healthy": False, "reason": "no_container"}

    # Check Docker container status
    container_name = f"vibecoding_{project_id}"
    docker_status = "unknown"
    try:
        if project_manager.docker_client:
            container = project_manager.docker_client.containers.get(container_name)
            docker_status = container.status
            if docker_status != "running":
                return {"healthy": False, "reason": "container_not_running", "docker_status": docker_status}
    except Exception:
        return {"healthy": False, "reason": "container_not_found"}

    # First, try the dedicated health endpoint on port 9090
    try:
        health_resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
        if health_resp.status_code == 200:
            health_data = health_resp.json()
            if health_data.get("status") == "healthy":
                return {"healthy": True, "docker_status": docker_status, "health_check": "passed"}
            return {"healthy": False, "reason": "health_check_failed", "docker_status": docker_status}
    except requests.exceptions.RequestException:
        # Health endpoint not available, fall back to probing the main app port
        pass

    # Fallback: Probe the actual app port
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/", timeout=3)
        if resp.status_code < 500:
            return {"healthy": True, "docker_status": docker_status, "http_status": resp.status_code}
        return {"healthy": False, "reason": "http_error", "http_status": resp.status_code}
    except requests.exceptions.ConnectionError:
        return {"healthy": False, "reason": "connection_refused", "docker_status": docker_status}
    except requests.exceptions.Timeout:
        return {"healthy": False, "reason": "timeout", "docker_status": docker_status}
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
        result = git_manager.init_repo(request.project_id)
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

@app.get("/vibecoding/api/projects/{project_id}/messages")
async def get_project_messages(project_id: str):
    from auth import get_db
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY timestamp ASC",
            (project_id,)
        ).fetchall()
        
        messages = []
        for row in rows:
            msg = dict(row)
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
            messages.append(msg)
            
        return {"messages": messages}
    finally:
        conn.close()


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
            
        # Checkout the commit
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
        # Create a targeted prompt for a CXO summary
        prompt = f"""Summarize the following code updates into a single professional, justifiable paragraph for a CXO or Business Analyst. 
Focus on the strategic impact and functional achievements. Use a sophisticated, outcome-oriented tone.
Do NOT use technical jargon. Highlight what was understood and how it was functionally executed.

CONTENT: {request.content[:1000]}
CODE SNIPPET: {request.code[:2000] if request.code else "No code provided"}

SUMMARY:"""
        
        messages = [
            {"role": "system", "content": "You are a professional business strategist and product manager. Your job is to translate technical code changes into business-value summaries for non-technical leadership."},
            {"role": "user", "content": prompt}
        ]
        
        response = ai_config.make_request(messages)
        
        if "choices" in response and len(response["choices"]) > 0:
            summary = response["choices"][0]["message"].get("content", "").strip()
            # Remove any intro text if LLM was chatty
            if ":" in summary and len(summary.split(":")[0]) < 20:
                summary = ":".join(summary.split(":")[1:]).strip()
        else:
            summary = "The requested updates were implemented successfully to ensure system stability and performance."
            
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

ARTIFACTS_DIR = Path(os.getenv('ARTIFACTS_DIR', './project_artifacts'))

def get_container_port(project_id: str) -> str:
    """Get the container port for a project by reading its container info"""
    try:
        # Check running containers registry
        registry_file = ARTIFACTS_DIR / '.container_registry.json'
        print(f"Looking for registry at: {registry_file}")
        
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                container_name = f"vibecoding_{project_id}"
                if container_name in registry:
                    return registry[container_name]['port']
    except Exception as e:
        print(f"Error reading container registry: {e}")
    return None




# ─── Catch-all Proxy for Absolute Assets ──────────────────────────────────────
# CRITICAL: This MUST stay at the very end of the file to avoid intercepting other routes
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def asset_fallback_proxy(path: str, request: Request):
    """
    Handles requests for absolute paths (e.g. /assets/foo.js) by using the Referer 
    header to determine which container the request belongs to.
    """
    referer = request.headers.get("referer", "")
    if not referer:
        # We don't log here to avoid noise from direct hits, but assets MUST have referer
        raise HTTPException(status_code=404)

    # Check if referer is one of our app proxy URLs
    # Matches both /vibecoding/app/{token}/ AND /app/{token}/
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
