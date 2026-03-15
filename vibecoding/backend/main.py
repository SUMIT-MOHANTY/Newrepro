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

load_dotenv()

app = FastAPI(title="Bourtec VibeCoding API")

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

# AI Configuration is now handled by ai_config.py

SYSTEM_PROMPT = """You are an expert full-stack developer and AI assistant for Bourtec VibeCoding platform.
Your role is to help users build web applications, components, and interfaces through natural language.

🌐 WEB TOOLS AVAILABLE:
You have access to web tools that you can call dynamically:
1. **web_search(query)** - Search the web using DuckDuckGo to find documentation, tutorials, examples, API references, or any real-time information.
2. **fetch_page_content(url)** - Fetch and read the content of any web page to get detailed information, code examples, or documentation.

Use these tools when:
- The user asks about a library, API, or tool you're not sure about
- You need current documentation or latest versions of packages
- The user asks you to research something before building
- You need to verify API endpoints, syntax, or best practices
- The user explicitly asks you to search the web

🚨 CRITICAL RULES - NEVER BREAK THESE:
1. ALWAYS generate MULTIPLE files with file markers - NEVER just one file
2. ALWAYS include ALL necessary files (HTML, CSS, JS, config files, etc.)
3. ALWAYS write ACTUAL CODE in every file - NEVER descriptions or comments only
4. ALWAYS use file markers: // FILE: path/to/filename.ext
5. 🗣️ NON-TECHNICAL NARRATION (CRITICAL): When explaining what you have built or answering the user, use non-technical, user-friendly language. DO NOT include code snippets, file markers (like // FILE:), or technical jargon in your conversational response. ONLY include the code behind the // FILE: markers at the end of your response.
6. 🤫 HIDE THE PLUMBING: The user is non-technical. Do not talk about "rendering templates", "API endpoints", or "backend logic". Describe features in terms of what the USER sees and experiences (e.g., "I've added a contact form" instead of "I've created a POST route for the contact form").


7. NO TECH-SPECIFIC LOCK-IN: Build everything from static landing pages to complex full-stack apps using the most appropriate tools for the job.
8. AUTOMATIC ENTRY POINT: Always ensure there is a clear entry point (e.g., app.py, main.py, index.html) that can be run immediately.

CRITICAL: Generate ACTUAL CODE for EVERY FILE, not folder structure descriptions or comments!

FILE MARKER FORMAT:
Use this EXACT format to separate files:
// FILE: path/to/filename.ext

Response format:
1. Brief non-technical explanation (1-2 sentences)
2. Complete code with file markers
3. NO folder structure diagrams"""

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
    return {"message": "Bourtec VibeCoding API is running"}

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
            
            return {
                "message": result.get("message", ""),
                "code": result.get("code"),
                "project_id": project_id,
                "version_id": None,
                "preview_url": result.get("preview_url"),
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
        # Build conversation history with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current prompt with a strict tool-calling enforcement
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
                code = "\n\n".join(blocks).strip()
            elif '<html' in ai_response.lower() or '<!doctype' in ai_response.lower():
                # Fallback if no markdown but HTML is present
                code = ai_response.strip()
        
        # Validate that code has multiple files with file markers
        if code:
            file_marker_count = len(_re.findall(r'//\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*', code))
            
            # If less than 3 file markers, regenerate with stronger prompt
            if file_marker_count < 3:
                print(f"⚠️ Warning: Only {file_marker_count} files detected. Requesting complete structure...")
                
                # Add a follow-up message demanding complete structure
                messages.append({
                    "role": "assistant",
                    "content": ai_response
                })
                messages.append({
                    "role": "user",
                    "content": f"""Please provide a COMPLETE project structure with ALL necessary files.

REQUIRED:
- Use file markers: // FILE: path/to/file.ext
- Include MINIMUM 5 files:
  1. Main entry point/application file
  2. Project configuration and dependency files
  3. All necessary template and component files
  4. Styling/CSS files
  5. Script/JavaScript files

Generate the COMPLETE structure with ACTUAL CODE in every file."""
                })
                
                # Make another API call (without tools for the follow-up)
                response = ai_config.make_request(messages)
                if "choices" in response and len(response["choices"]) > 0:
                    ai_response = response["choices"][0]["message"]["content"]
                    
                    # Re-extract code
                    if "```python" in ai_response:
                        code_start = ai_response.find("```python") + 10
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
                    elif "```html" in ai_response:
                        code_start = ai_response.find("```html") + 7
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
                    elif "```" in ai_response:
                        code_start = ai_response.find("```") + 3
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
        
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
            version_id, _ = project_manager.save_code_version(project_id, code, request.prompt)
            
            # Check if Docker is available before attempting to create container
            if project_manager.docker_client is None:
                print("⚠️ Docker not available - preview functionality disabled")
                print("Please ensure Docker Desktop is installed and running")
                preview_url = None
            else:
                # Create container for preview
                try:
                    preview_url = await project_manager.create_container_for_code(project_id, version_id)
                except Exception as e:
                    print(f"Failed to create container: {str(e)}")
                    # Continue without container if it fails

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

@app.post("/api/projects/{project_id}/versions/{version_id}/preview")
async def create_preview(project_id: str, version_id: str):
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            raise HTTPException(
                status_code=503,
                detail="Docker not available. Please ensure Docker Desktop is installed and running."
            )
        
        preview_url = await project_manager.create_container_for_code(project_id, version_id)
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
