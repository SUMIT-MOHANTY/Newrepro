import json
import hashlib
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
import re as _re
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

async def wait_for_container_ready(base_url: str, max_attempts: int = 5, delay: float = 0.2):
    """
    Wait for container to be ready by checking if it responds to requests.
    This handles the case where containers are dynamically starting.
    """
    import asyncio
    import time
    
    for attempt in range(max_attempts):
        try:
            session = get_proxy_session()
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

class GenerateResponse(BaseModel):
    message: str
    code: Optional[str] = None
    project_id: str
    version_id: Optional[str] = None
    preview_url: Optional[str] = None
    tool_calls_log: Optional[List[dict]] = None

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

# AI Configuration is now handled by ai_config.py

SYSTEM_PROMPT = MAIN_SYSTEM_PROMPT

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


@app.post("/vibecoding/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest):
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

    try:
        # ── Discuss mode: pure conversation, no code generation ──────────
        if request.discuss_mode:
            from prompts import CHAT_SYSTEM_PROMPT
            messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append(build_vision_message(request.prompt, request.images))

            response = ai_config.make_request(messages)
            ai_response = response["choices"][0]["message"].get("content", "") if "choices" in response else ""
            return GenerateResponse(
                message=ai_response,
                code=None,
                project_id=project_id,
                version_id=None,
                preview_url=None,
                tool_calls_log=None
            )

        # Check if there's existing code in the workspace
        workspace_files = project_manager.get_workspace_files(project_id, max_files=15, max_chars_per_file=1500)
        has_existing_code = len(workspace_files) > 0
        
        # Get frozen files list
        frozen_files = project_manager.get_frozen_files(project_id)
        frozen_files_str = "\n".join([f"- {path} (READ-ONLY)" for path in frozen_files]) if frozen_files else "None"

        # Inject BRD project context if available
        brd_context_str = ""
        project_meta = project_manager.get_project_info(project_id)
        if project_meta and project_meta.get("brd_context"):
            brd = project_meta["brd_context"]
            parts = []
            if brd.get("project_name"):
                parts.append(f"Project Name: {brd['project_name']}")
            if brd.get("classification"):
                parts.append(f"Governance Classification: {brd['classification']}")
            if brd.get("recommendation"):
                parts.append(f"Governance Recommendation: {brd['recommendation']}")
            if brd.get("brd_summary"):
                parts.append(f"BRD Summary: {brd['brd_summary']}")
            if brd.get("agent_analysis"):
                parts.append(f"Agent Analysis: {brd['agent_analysis']}")
            if parts:
                brd_context_str = "\n\n📄 PROJECT CONTEXT (from BRD Analyzer):\n" + "\n".join(parts) + "\n"

        # Build conversation history with appropriate system prompt
        if has_existing_code:
            # Provide context about existing code and let AI decide whether to do incremental or full edit
            file_list = "\n".join([f"- {path}" for path in workspace_files.keys()])
            
            # Format current files for context
            current_files_str = ""
            for path, content in workspace_files.items():
                current_files_str += f"\n\n// FILE: {path}\n{content}"
            
            from prompts import INCREMENTAL_EDIT_PROMPT
            system_prompt = INCREMENTAL_EDIT_PROMPT.replace("{{file_list}}", file_list).replace("{{current_files}}", current_files_str).replace("{{frozen_files}}", frozen_files_str)
            logger.info(f"📝 Existing codebase detected - AI will decide edit scope")
        else:
            system_prompt = SYSTEM_PROMPT.replace("{{frozen_files}}", frozen_files_str)
            logger.info(f"🆕 New project - full generation mode")
        
        from datetime import datetime
        now = datetime.now()
        date_context = f"Current date and time: {now.strftime('%A, %B %d, %Y %H:%M:%S')} (UTC{now.astimezone().strftime('%z')})\n\n"
        messages = [{"role": "system", "content": date_context + system_prompt + brd_context_str}]
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current prompt with explicit instructions for incremental edits
        if has_existing_code:
            # Add a reminder to the user's prompt for incremental edits
            prompt_with_instructions = f"""{request.prompt}

IMPORTANT: If this is a small change (like changing colors, text, or adding a simple feature), output ONLY the files that need to be modified. Do NOT regenerate the entire codebase."""
        else:
            prompt_with_instructions = request.prompt
        if any(word in request.prompt.lower() for word in ['search', 'web', 'internet', 'look up', 'fetch', 'url', 'http']):
            prompt_with_instructions += "\n\n(IMPORTANT: Use your `web_search` or `fetch_page_content` tool to fulfill this request. After you have gathered the necessary information about the page, you MUST generate the COMPLETE project code with ALL necessary files using the `// FILE: path/to/file.ext` format. DO NOT just describe the page; build it.)"
            
        messages.append(build_vision_message(prompt_with_instructions, request.images))

        # Call AI API with function calling support (web search + page fetch)
        response = await make_request_with_tools(messages)
        
        # Extract tool calls log if any tools were used
        tool_calls_log = response.pop("_tool_calls_log", None)
        
        # Extract AI response
        if "choices" in response and len(response["choices"]) > 0:
            ai_response = response["choices"][0]["message"].get("content") or ""
        else:
            raise Exception("Invalid response format from AI API")

        # Extract code if present
        import re as _re
        code = None
        
        # ── Preprocess: fix mixed AI format (// FILE: + SEARCH/REPLACE) ──
        # Some models output "// FILE: path" headers for SEARCH/REPLACE blocks
        # instead of "// PATCH: path". Detect and convert before the main parser.
        ai_response = _preprocess_ai_response(ai_response)
        
        has_patch_markers = bool(_re.search(r'//\s*PATCH:\s*', ai_response))
        has_raw_search_replace = (
            not has_patch_markers
            and bool(_re.search(r'<<<\s*SEARCH', ai_response))
            and bool(_re.search(r'<<<\s*REPLACE', ai_response))
        )
        has_markers = bool(_re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', ai_response))

        if has_patch_markers or has_raw_search_replace:
            code = ai_response
        elif has_markers:
            # Extract code ONLY from within markdown fences to avoid including
            # preamble / epilogue narrative in the preview iframe.
            fenced_blocks = _re.findall(r'```[a-zA-Z]*\n?(.*?)```', ai_response, _re.DOTALL)
            fenced_code = "\n\n".join(b.strip() for b in fenced_blocks).strip() if fenced_blocks else ""

            if fenced_code and _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', fenced_code):
                code = fenced_code
            else:
                # Fallback: strip fences, then take only from the first file marker onward.
                cleaned = _re.sub(r'```[a-zA-Z]*\n?', '', ai_response)
                cleaned = cleaned.replace('```', '')
                first_marker = _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', cleaned)
                if first_marker:
                    code = cleaned[first_marker.start():].strip()
                else:
                    code = cleaned.strip()
        else:
            # No file markers. Extract all markdown code blocks and join them.
            blocks = _re.findall(r'```[a-zA-Z]*\n?(.*?)```', ai_response, _re.DOTALL)
            if blocks:
                # Universal Code Extraction (Regex)
                import re
                code_match = re.search(r"```(?:\w+)?\n?(.*?)\n?```", ai_response, re.DOTALL)
                if code_match:
                    code = code_match.group(1).strip()
                else:
                    code = "\n\n".join(blocks).strip()
            elif '<html' in ai_response.lower() or '<!doctype' in ai_response.lower():
                # Fallback if no markdown but HTML is present
                code = ai_response.strip()
        
        # Clean up integrity/crossorigin attributes and stray patch markers
        if code:
            import re
            # Remove integrity attributes
            code = re.sub(r'\s+integrity="[^"]*"', '', code)
            code = re.sub(r"\s+integrity='[^']*'", '', code)
            # Remove crossorigin attributes
            code = re.sub(r'\s+crossorigin="[^"]*"', '', code)
            code = re.sub(r"\s+crossorigin='[^']*'", '', code)
            code = re.sub(r'\s+crossorigin(?=\s|>)', '', code)

            # If this is clearly a full HTML/file output (not patch mode), strip accidental PATCH tokens
            # that sometimes leak into the generated HTML (e.g. bare "<<<REPLACE" lines).
            if (not has_patch_markers) and (not has_raw_search_replace):
                looks_like_html = '<!doctype' in code.lower() or '<html' in code.lower()
                if looks_like_html and ('<<<REPLACE' in code or '<<<SEARCH' in code):
                    code = re.sub(r'^\s*(<<<SEARCH|<<<REPLACE|>>>)\s*$', '', code, flags=re.MULTILINE)
                    code = re.sub(r'\n{3,}', '\n\n', code).strip()
        
        # Initialize message variable
        message = ai_response
        
        # Check if AI returned instructions instead of actual code
        # (skip this check for patch responses — they never start with code prefixes)
        is_any_patch = has_patch_markers or has_raw_search_replace
        if code and not is_any_patch and (
            not code.strip().startswith(('from', 'import', 'def', 'class', 'app =', '<!DOCTYPE', '<html', '{', '[')) and
            len(code.strip().split('\n')) < 5
        ):
            code = None
            message = ai_response

        # Clean message (remove code blocks and patch blocks — show only narrative)
        if code:
            if has_patch_markers:
                message = _re.split(r'//\s*PATCH:\s*', ai_response)[0].strip()
            elif has_raw_search_replace:
                message = _re.split(r'<<<\s*SEARCH', ai_response)[0].strip()
            elif has_markers:
                # Capture both preamble (before first fence) and epilogue (after last fence)
                parts = ai_response.split("```")
                preamble = parts[0].strip()
                epilogue = parts[-1].strip() if len(parts) >= 3 else ""
                if epilogue and not _re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', epilogue):
                    message = f"{preamble}\n\n{epilogue}".strip()
                else:
                    message = preamble
            else:
                message = ai_response.split("```")[0].strip()
            # Remove stray markdown fences from the message portion
            message = message.replace('```', '').strip()

        # Save code version if code was generated
        version_id = None
        preview_url = None
        
        if code:
            # Use git-based workspace update (auto-detects incremental vs full)
            try:
                version_id, _ = project_manager.update_workspace_from_code(project_id, code, request.prompt)
            except ValueError as e:
                # Check if it's a frozen file violation
                if str(e).startswith("FROZEN_FILES_VIOLATION:"):
                    frozen_files_str = str(e).split(":", 1)[1]
                    frozen_list = frozen_files_str.split(",")
                    # Remove duplicates
                    frozen_list = list(set(frozen_list))
                    violation_list = "\n".join([f"  - {f}" for f in frozen_list])
                    error_message = f"Cannot complete this request. The following files are frozen (read-only) and cannot be modified:\n\n{violation_list}\n\nPlease unfreeze these files if you want to make changes, or rephrase your request to avoid modifying them."
                    
                    return GenerateResponse(
                        message=error_message,
                        code=None,
                        project_id=project_id,
                        version_id=None,
                        preview_url=None,
                        tool_calls_log=tool_calls_log
                    )
                else:
                    raise
            
            # Save chat history for the current branch (not commit hash)
            try:
                # Get current branch name
                status = git_manager.get_status(project_id)
                current_branch = status.get("branch", "main") if status["status"] == "success" else "main"
                
                history = [{"role": msg.role, "content": msg.content} for msg in request.history]
                history.append({"role": "user", "content": request.prompt})
                history.append({"role": "assistant", "content": message if message else "I've generated the code for you!"})
                
                # Save with branch name so it persists across commits in the same branch
                await project_manager.save_chat_version(project_id, current_branch, history)
                logger.info(f"💾 Saved chat history to branch: {current_branch}")
            except Exception as e:
                print(f"Failed to save chat history: {e}")
            
            # Check if Docker is available before attempting to create container
            if project_manager.docker_client is None:
                print("⚠️ Docker not available - preview functionality disabled")
                preview_url = None
            else:
                # Pass user prompt so the container's ai-agent knows the intent
                project_manager._current_user_prompt = request.prompt
                try:
                    preview_url = await project_manager.create_container_for_code(project_id, "workspace")
                except Exception as e:
                    print(f"Failed to create container: {str(e)}")
                    preview_url = None

        return GenerateResponse(
            message=message if message else "I've generated the code for you!",
            code=code,
            project_id=project_id,
            version_id=version_id,
            preview_url=preview_url,
            tool_calls_log=tool_calls_log
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return error response with valid project_id
        return GenerateResponse(
            message=f"I encountered an error: {str(e)}. Please try again or rephrase your request.",
            code=None,
            project_id=project_id,
            version_id=None,
            preview_url=None,
            tool_calls_log=None
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

    # Probe the actual app port
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
        project_id = request.project_id or project_manager.generate_project_id()
        user_id = user["id"]
        
        # Check if project already exists
        project_info = project_manager.get_project_info(project_id)
        if project_info:
            # If project exists but has no owner, claim it for this user
            if project_info.get("owner_id") is None:
                project_info["owner_id"] = user_id
                project_manager.update_project_metadata(project_id, project_info)
            return ProjectResponse(**project_info)
            
        project_manager.create_project_directory(project_id, metadata={
            "name": request.name,
            "description": request.description,
            "owner_id": user_id
        })
        
        project_info = project_manager.get_project_info(project_id)
        return ProjectResponse(**project_info)
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
        return {"history": history}
    except Exception as e:
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
        print(f"Registry exists: {registry_file.exists()}")
        
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                print(f"Registry contents: {registry}")
                container_name = f"vibecoding_{project_id}"
                print(f"Looking for container: {container_name}")
                if container_name in registry:
                    return registry[container_name]['port']
    except Exception as e:
        print(f"Error reading container registry: {e}")
    print(f"No port found for project_id: {project_id}")
    return None

async def proxy_request(target_base: str, request: Request, forward_path: str):
    """Generic proxy handler with connection pooling"""
    target_url = target_base + forward_path
    
    # Forward query params
    if request.url.query:
        target_url += "?" + request.url.query
    
    # Forward headers (excluding host and content-length)
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ["host", "x-forwarded-for", "x-forwarded-proto", "content-length"]:
            headers[key] = value
    
    # Add referer if not present (helps with iframe requests)
    has_referer = any(k.lower() == "referer" for k in headers.keys())
    if not has_referer:
        headers["referer"] = str(request.base_url)
    
    print(f"🔄 Proxying {request.method} to {target_url}")
    print(f"📋 Headers forwarded: {list(headers.keys())}")
    print(f"🌐 Request origin: {request.client}, User-Agent: {headers.get('user-agent', 'unknown')}")
    
    try:
        # Read request body
        body = await request.body()
        
        # Wait for container to be ready (in case it's just starting)
        print(f"⏳ Checking if container is ready at {target_base}...")
        is_ready = await wait_for_container_ready(target_base, max_attempts=3, delay=0.1)
        if not is_ready:
            print(f"⚠️ Container not responding after 3 attempts, attempting request anyway...")
        
        # Use session with connection pooling
        session = get_or_create_proxy_session()
        
        print(f"⏳ Attempting connection to {target_url} with timeout (10s connect, 60s read)")
        resp = session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body if body else None,
            allow_redirects=False,
            timeout=(3, 30)  # 3s connect, 30s read - faster fail for starting containers
        )
        
        print(f"✅ Got response: {resp.status_code} {len(resp.content)} bytes")
        
        # Headers to exclude from response (remove iframe/frame options)
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
            "x-frame-options",  # Allow iframe embedding
            "content-security-policy",  # Allow iframe embedding
        ]
        
        response_headers = {}
        for name, value in resp.headers.items():
            if name.lower() not in excluded_headers:
                response_headers[name] = value
        
        # Allow embedding in iframe by setting proper headers
        response_headers["X-Frame-Options"] = "ALLOWALL"
        response_headers["Access-Control-Allow-Origin"] = "*"
        
        return StreamingResponse(
            iter([resp.content]),
            status_code=resp.status_code,
            headers=response_headers
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
        error_str = str(e)
        print(f"❌ Connection error to {target_url}: {error_str}")
        # Check if it's a protocol error (container not ready)
        if "ProtocolError" in error_str or "Connection refused" in error_str:
            print(f"⏳ Container at {target_url} may still be starting up... Retried 3 times")
            detail = f"Container is starting. Please wait a moment and retry."
        else:
            detail = f"Cannot connect to container at {target_url}. Verify container is running."
        raise HTTPException(status_code=502, detail=detail)
    except requests.exceptions.Timeout as e:
        print(f"⏱️ Timeout to {target_url}: {str(e)}")
        print(f"⏳ Container is slow to respond. It may still be starting.")
        raise HTTPException(status_code=504, detail=f"Container is slow to respond. Please try again in a moment.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Proxy error to {target_url}: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error in proxy: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal proxy error: {str(e)}")

@app.api_route("/vibecoding/app/{token}/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.api_route("/vibecoding/app/{token}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def route_proxy(token: str, request: Request, path: str = ""):
    """Route requests to the appropriate container based on project token"""
    # Get container port for this project
    port = get_container_port(token)
    print(f"📌 Proxy request for token {token}: port={port}, path={path or '/'}, client={request.client}")
    if not port:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{token}' not found or container not running"
        )
    
    # Use localhost instead of 127.0.0.1 for better compatibility
    target = f"http://localhost:{port}"
    forward_path = "/" + path if path else "/"
    print(f"🎯 Target container: {target}{forward_path}")
    return await proxy_request(target, request, forward_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
