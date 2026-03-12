from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
from dotenv import load_dotenv
from ai_config import ai_config
from project_manager import project_manager

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
    version_id: str
    preview_url: Optional[str] = None

class ProjectCreateRequest(BaseModel):
    name: Optional[str] = None

class ProjectResponse(BaseModel):
    project_id: str
    name: str
    created_at: str
    versions: List[dict]
    current_version: Optional[str] = None

class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]

# AI Configuration is now handled by ai_config.py

SYSTEM_PROMPT = """You are an expert full-stack developer and AI assistant for Bourtec VibeCoding platform.
Your role is to help users build web applications, components, and interfaces through natural language.

IMPORTANT: Always generate ACTUAL WORKING CODE, not installation instructions or setup guides.

When a user asks you to create something:
1. Generate complete, working code (HTML/CSS/JS for web, Python for Flask/Django, etc.)
2. Make it fully functional and interactive
3. Include all necessary imports and dependencies
4. For web apps: use inline styles and scripts (everything in one file) OR provide complete multi-file structure
5. For Python apps: provide complete .py file with all imports and main execution
6. Add responsive design and good UX practices

CRITICAL: 
- NEVER respond with just installation instructions like "pip install flask"
- ALWAYS provide the complete, runnable code
- For Flask apps: include the full Python code with app.route(), imports, etc.
- For web pages: include complete HTML with CSS and JavaScript

Always respond with:
- A brief explanation of what you created
- The COMPLETE working code in proper code blocks

Make code production-ready, beautiful, and fully functional."""

@app.get("/")
async def root():
    return {"message": "Bourtec VibeCoding API is running"}

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest):
    try:
        # Get or create project ID
        project_id = request.project_id or project_manager.generate_project_id()
        
        # Build conversation history with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current prompt
        messages.append({
            "role": "user",
            "content": request.prompt
        })

        # Call AI API
        response = ai_config.make_request(messages)
        
        # Extract AI response
        if "choices" in response and len(response["choices"]) > 0:
            ai_response = response["choices"][0]["message"]["content"]
        else:
            raise Exception("Invalid response format from AI API")

        # Extract code if present
        code = None
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
        
        # Check if extracted content is actually code or just instructions
        if code and (
            not code.strip().startswith(('from', 'import', 'def', 'class', 'app =', '<!DOCTYPE', '<html', 'from flask')) and
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
            preview_url=preview_url
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# Project Management Endpoints

@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest):
    try:
        project_id = project_manager.generate_project_id()
        project_dir = project_manager.create_project_directory(project_id)
        
        project_info = project_manager.get_project_info(project_id)
        project_info["name"] = request.name or f"Project {project_id[:8]}"
        
        # Update project metadata with name
        with open(project_dir / "metadata.json", "w") as f:
            import json
            json.dump(project_info, f, indent=2)
        
        return ProjectResponse(**project_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects", response_model=ProjectListResponse)
async def list_projects():
    try:
        projects = project_manager.list_projects()
        return ProjectListResponse(projects=projects)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
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
        preview_url = await project_manager.create_container_for_code(project_id, version_id)
        if not preview_url:
            raise HTTPException(status_code=500, detail="Failed to create preview")
        return {"preview_url": preview_url}
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

@app.post("/api/cleanup")
async def cleanup_containers():
    try:
        project_manager.cleanup_old_containers()
        return {"message": "Cleanup completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
