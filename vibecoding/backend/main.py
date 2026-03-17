from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
from auth import SignupRequest, LoginRequest, signup_user, login_user, get_current_user
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

class Message(BaseModel):
    role: str
    content: str
    code: Optional[str] = None

class GenerateRequest(BaseModel):
    prompt: str
    history: List[Message] = []
    project_id: Optional[str] = None
    discuss_mode: bool = False

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
@app.post("/api/auth/signup")
async def signup(request: SignupRequest):
    """Register a new user."""
    return signup_user(request)


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Login with email and password."""
    return login_user(request)


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current authenticated user."""
    return user


@app.get("/api/auth/verify")
async def verify_token(user: dict = Depends(get_current_user)):
    """Verify if the current token is valid."""
    return {"valid": True, "user": user}


@app.get("/")
async def root():
    return {"message": f"{APP_NAME} API is running"}

@app.post("/api/chat/dual-agent")
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
                # Use git-based workspace update (auto-detects incremental vs full)
                version_id, _ = project_manager.update_workspace_from_code(project_id, code, request.prompt)
                
                # Save chat history for the current branch (not commit hash)
                # Get current branch name
                status = git_manager.get_status(project_id)
                current_branch = status.get("branch", "main") if status["status"] == "success" else "main"
                
                history.append({"role": "user", "content": request.prompt})
                history.append({"role": "assistant", "content": result.get("message", "")})
                await project_manager.save_chat_version(project_id, current_branch, history)
                
                # Create or switch container to workspace mode and get preview URL
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

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest):
    # Get or create project ID at the start
    project_id = request.project_id or project_manager.generate_project_id()
    
    try:
        # ── Discuss mode: pure conversation, no code generation ──────────
        if request.discuss_mode:
            from prompts import CHAT_SYSTEM_PROMPT
            messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": request.prompt})

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
        
        # Build conversation history with appropriate system prompt
        if has_existing_code:
            # Provide context about existing code and let AI decide whether to do incremental or full edit
            file_list = "\n".join([f"- {path}" for path in workspace_files.keys()])
            
            # Format current files for context
            current_files_str = ""
            for path, content in workspace_files.items():
                current_files_str += f"\n\n// FILE: {path}\n{content}"
            
            from prompts import INCREMENTAL_EDIT_PROMPT
            system_prompt = INCREMENTAL_EDIT_PROMPT.replace("{{file_list}}", file_list).replace("{{current_files}}", current_files_str)
            logger.info(f"📝 Existing codebase detected - AI will decide edit scope")
        else:
            system_prompt = SYSTEM_PROMPT
            logger.info(f"🆕 New project - full generation mode")
        
        messages = [{"role": "system", "content": system_prompt}]
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
            
        messages.append({
            "role": "user",
            "content": prompt_with_instructions
        })

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
        
        has_markers = bool(_re.search(r'(?i)(?://|#|<!--)\s*FILE:\s*', ai_response))
        if has_markers:
            # AI provided file markers. Keep the entire response but strip markdown code wrappers
            # so the frontend can split by file markers cleanly without including ` ```html ` in the file content.
            cleaned = _re.sub(r'```[a-zA-Z]*\n?', '', ai_response)
            cleaned = cleaned.replace('```', '')
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
        
        # Clean up integrity and crossorigin attributes from CDN links
        if code:
            import re
            # Remove integrity attributes
            code = re.sub(r'\s+integrity="[^"]*"', '', code)
            code = re.sub(r"\s+integrity='[^']*'", '', code)
            # Remove crossorigin attributes
            code = re.sub(r'\s+crossorigin="[^"]*"', '', code)
            code = re.sub(r"\s+crossorigin='[^']*'", '', code)
            code = re.sub(r'\s+crossorigin(?=\s|>)', '', code)
        
        # Initialize message variable
        message = ai_response
        
        # Check if AI returned instructions instead of actual code
        if code and (
            not code.strip().startswith(('from', 'import', 'def', 'class', 'app =', '<!DOCTYPE', '<html', '{', '[')) and
            len(code.strip().split('\n')) < 5
        ):
            # This looks like instructions, not actual code
            code = None
            message = ai_response  # Show full response including instructions

        # Clean message (remove code blocks)
        if code:
            message = ai_response.split("```")[0].strip()

        # Save code version if code was generated
        version_id = None
        preview_url = None
        
        if code:
            # Use git-based workspace update (auto-detects incremental vs full)
            version_id, _ = project_manager.update_workspace_from_code(project_id, code, request.prompt)
            
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

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# Project Management Endpoints

@app.post("/api/projects", response_model=ProjectResponse)
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

@app.get("/api/projects", response_model=ProjectListResponse)
async def list_projects(user: dict = Depends(get_current_user)):
    try:
        user_id = user["id"]
        projects = project_manager.list_projects(owner_id=user_id)
        return ProjectListResponse(projects=projects)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
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

@app.get("/api/projects/{project_id}/versions")
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

@app.get("/api/projects/{project_id}/versions/{version_id}/code")
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

@app.get("/api/projects/{project_id}/versions/{version_id}/files")
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

@app.post("/api/projects/{project_id}/versions/{version_id}/preview")
async def create_preview(project_id: str, version_id: str):
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            raise HTTPException(
                status_code=503,
                detail="Docker not available. Please ensure Docker Desktop is installed and running."
            )
        
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
        # create_container_for_code handles both new creation and version switching
        preview_url = await project_manager.create_container_for_code(project_id, "workspace")
        
        if not preview_url:
            raise HTTPException(status_code=500, detail="Failed to create preview")
        return {"preview_url": preview_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/projects/{project_id}/versions/{version_id}/preview")
async def stop_preview(project_id: str, version_id: str):
    try:
        project_manager.stop_container(project_id, version_id)
        return {"message": "Preview stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/download")
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

@app.get("/api/projects/{project_id}/chat/{version_id}")
async def get_chat_history(project_id: str, version_id: str):
    try:
        history = await project_manager.get_chat_version(project_id, version_id)
        if history is None:
            return {"history": []}
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/chat/{version_id}")
async def save_chat_history(project_id: str, version_id: str, request: dict):
    try:
        history = request.get("history", [])
        await project_manager.save_chat_version(project_id, version_id, history)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Git Integration Endpoints

@app.post("/api/git/status")
async def git_status(request: GitRequest):
    try:
        status = git_manager.get_status(request.project_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/init")
async def git_init(request: GitRequest):
    try:
        result = git_manager.init_repo(request.project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/add")
async def git_add(request: GitRequest):
    try:
        result = git_manager.add_files(request.project_id, request.files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/commit")
async def git_commit(request: GitRequest):
    try:
        if not request.message:
            raise HTTPException(status_code=400, detail="Commit message is required")
        result = git_manager.commit(request.project_id, request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/branch")
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

@app.post("/api/git/checkout")
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

@app.post("/api/git/branches")
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

@app.get("/api/projects/{project_id}/branches")
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

@app.get("/api/projects/{project_id}/branches/{branch_name}/commits")
async def get_branch_commits(project_id: str, branch_name: str):
    """Get all commits for a specific branch (checkpoints in chat)"""
    try:
        # Save current branch
        current_status = git_manager.get_status(project_id)
        current_branch = current_status.get("branch", "")
        
        # Checkout the requested branch
        if branch_name != current_branch:
            checkout_result = git_manager.checkout_branch(project_id, branch_name)
            if checkout_result["status"] != "success":
                raise HTTPException(status_code=404, detail=f"Branch {branch_name} not found")
        
        # Get commits
        commits_result = git_manager.get_commit_history(project_id)
        
        # Switch back to original branch
        if branch_name != current_branch and current_branch:
            git_manager.checkout_branch(project_id, current_branch)
        
        if commits_result["status"] != "success":
            return {"commits": []}
        
        return {"commits": commits_result.get("commits", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/remote")
async def git_remote(request: GitRequest):
    try:
        if not request.remote_url:
            raise HTTPException(status_code=400, detail="Remote URL is required")
        result = git_manager.add_remote(request.project_id, request.remote_url, request.remote_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/git/push")
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

@app.post("/api/chat/new")
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

@app.post("/api/git/checkpoint")
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

@app.post("/api/cleanup")
async def cleanup_containers():
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            return {"message": "Docker not available - no containers to clean up"}
        
        project_manager.cleanup_old_containers()
        return {"message": "Cleanup completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
