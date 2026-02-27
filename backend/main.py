import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Optional, List, Dict, Any

from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Header
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

import auth
import models
import schemas
import ingestion
import ai_service
import governance_scoring
import github_service
import agent_service
import rag_service
import context_manager
import knowledge_graph_service as kg_service
from database import engine, get_db, SessionLocal
from config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="BRD Analysis API", version="1.0.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import StreamingResponse

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
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    return current_user

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
    allowed_extensions = {".pdf", ".docx", ".pptx", ".html", ".htm", ".png", ".jpg", ".jpeg"}
    
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

# --- History Endpoints ---

@app.get("/history", response_model=List[schemas.Document])
def get_user_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
):
    """Retrieve user's document history."""
    return db.query(models.Document).filter(models.Document.owner_id == current_user.id).order_by(models.Document.upload_date.desc()).offset(skip).limit(limit).all()

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

@app.get("/governance/questions")
async def get_governance_questions():
    """
    Get all 17 governance questionnaire questions.
    No authentication required for viewing questions.
    """
    return {
        "total_questions": len(governance_scoring.GOVERNANCE_QUESTIONS),
        "questions": governance_scoring.GOVERNANCE_QUESTIONS,
        "dimension_weights": governance_scoring.DIMENSION_WEIGHTS,
    }


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
    
    # Perform complete scoring
    scoring_result = governance_scoring.score_governance_response(answers_dict)
    
    detailed_answers = {
        str(answer.question_id): {
            "score": answer.score,
            "selected_option": answer.selected_option,
        }
        for answer in request.answers
    }

    recommendation_text = _generate_recommendation(scoring_result, answers_dict)

    # Save response to database
    db_response = models.GovernanceResponse(
        owner_id=current_user.id,
        project_token=str(uuid.uuid4()),
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
    )


@app.get("/governance/history")
async def get_governance_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get submission history for the current user.
    """
    responses = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    ).order_by(models.GovernanceResponse.submission_date.desc()).all()
    
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
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
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
        classification_description=_classification_description(response.classification),
        recommendation=response.recommendation,
        pending_revision_reason=response.pending_revision_reason,
        hard_stops=[],
        answers=answers_list if answers_list else None,
        client_id=response.client_id,
        client_secret=response.client_secret,
    )


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

@app.get("/governance/{identifier}/roadmap-step")
async def get_project_roadmap_step(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None),
):
    """
    Get the current roadmap step for a project.

    Steps:
        0 - Project Setup                (project named)
        1 - Requirement Screening        (governance assessment completed)
        2 - AI Analysis                  (BRD uploaded & analysis completed)
        3 - Prerequisite Classification  (prerequisites / credentials identified)
        4 - Task Creation                (tasks auto-generated via external API)
        5 - Agent Execution              (agents working on tasks)
        6 - Complete                     (all tasks completed)

    Returns a `step_statuses` array with per-step status:
        "completed" | "active" | "pending" | "failed"
    And a `failed_step` index (null if none failed).
    """
    STEP_LABELS = [
        "Project Setup",
        "Requirement Screening",
        "AI Analysis",
        "Prerequisite Classification",
        "Task Creation",
        "Agent Execution",
        "Complete",
    ]

    # 1. Check governance response exists for this user
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    )
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    # Step 0 (Project Setup) is always complete once a governance response exists
    # Step 1 (Requirement Screening) is complete: governance submitted
    current_step = 2  # user is now at "AI Analysis"
    failed_step = None

    # 2. Find documents linked to this governance result
    project_name = governance.project_name or ""
    user_documents = db.query(models.Document).filter(
        models.Document.owner_id == current_user.id,
    ).all()

    linked_docs = []
    for doc in user_documents:
        if not doc.analysis_result:
            continue
        try:
            import json
            analysis = json.loads(doc.analysis_result)
            gov_ctx = analysis.get("governanceContext") or {}
            proj_meta = analysis.get("projectMeta") or {}
            doc_result_id = proj_meta.get("governance_result_id") or gov_ctx.get("result_id")
            doc_token_id = proj_meta.get("project_token") or gov_ctx.get("project_token")
            doc_project_name = proj_meta.get("project_name") or gov_ctx.get("project_name") or ""

            if (doc_result_id is not None and str(doc_result_id) == str(governance.id)) or \
               (doc_token_id and str(doc_token_id) == str(governance.project_token)) or \
               (project_name and doc_project_name.strip().lower() == project_name.strip().lower()):
                linked_docs.append(doc)
        except (json.JSONDecodeError, AttributeError):
            continue

    has_analysis = False
    if linked_docs:
        has_analysis = any(
            _doc_has_completed_analysis(doc) for doc in linked_docs
        )
        if has_analysis:
            current_step = 3  # AI Analysis complete, now at "Prerequisite Classification"

            # Check if prerequisites were acknowledged
            if governance.prerequisites_completed_at is not None:
                current_step = 4  # Prerequisites done, now at "Task Creation"

    # 3. Check external task management for task creation & agent execution
    has_tasks = False
    all_tasks_complete = False
    any_agent_working = False

    if has_analysis and x_task_token:
        try:
            existing_page = await task_service.get_tasks(page=1, task_token=x_task_token)
            if isinstance(existing_page, list):
                page_results = existing_page
            elif isinstance(existing_page, dict):
                page_results = existing_page.get("results") if isinstance(existing_page.get("results"), list) else []
            else:
                page_results = []

            if page_results:
                has_tasks = True
                current_step = 5  # Tasks created, now at "Agent Execution"

                # Check if any agent is actively working (has progress or is assigned)
                any_agent_working = any(
                    (t.get("status") or "").lower() in ("in_progress", "in progress", "working", "assigned", "started")
                    or (t.get("completion_percentage") or 0) > 0
                    for t in page_results
                )

                if any_agent_working:
                    current_step = 5  # Still at Agent Execution (active)

                # Check if ALL tasks are completed
                all_tasks_complete = all(
                    (t.get("status") or "").lower() in ("completed", "done", "closed", "complete")
                    or (t.get("completion_percentage") or 0) >= 100
                    for t in page_results
                )

                if all_tasks_complete:
                    current_step = 6  # Complete
        except Exception as e:
            print(f"Roadmap: Failed to check tasks for {identifier}: {e}")
            # If task check fails, we don't mark it as failed - just stay at current step

    # Build per-step statuses
    step_statuses = []
    for i in range(len(STEP_LABELS)):
        if failed_step is not None and i == failed_step:
            step_statuses.append("failed")
        elif i < current_step:
            step_statuses.append("completed")
        elif i == current_step:
            step_statuses.append("active")
        else:
            step_statuses.append("pending")

    return {
        "result_id": governance.id,
        "project_token": governance.project_token or str(governance.id),
        "project_name": governance.project_name,
        "current_step": current_step,
        "current_step_label": STEP_LABELS[current_step] if current_step < len(STEP_LABELS) else "Complete",
        "total_steps": len(STEP_LABELS),
        "steps": STEP_LABELS,
        "step_statuses": step_statuses,
        "failed_step": failed_step,
        "classification": governance.classification,
    }


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
    
    if hard_stops:
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


class RepoContextRequest(BaseModel):
    owner: str
    repo: str
    branch: str = "main"
    token: Optional[str] = None


@app.post("/github/repo-context")
async def github_repo_context(
    payload: RepoContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch repository source code and return a structured text context
    suitable for feeding into the AI model alongside the BRD.
    """
    try:
        # Prioritize explicitly provided token (for private links), fallback to OAuth token
        token_to_use = payload.token if payload.token else current_user.github_token

        context = await github_service.build_repo_context(
            token_to_use,
            payload.owner,
            payload.repo,
            payload.branch,
        )
        return {"context": context, "repo": f"{payload.owner}/{payload.repo}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build repo context: {e}")


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


# Seed sample tasks on startup
@app.on_event("startup")
async def startup_event():
    agent_service.seed_sample_tasks()
    db = SessionLocal()
    try:
        _ensure_agent_project_columns()
        _ensure_default_agents(db)
        agents = db.query(models.Agent).filter(models.Agent.project_token.is_(None)).all()
        agent_service.initialize_agents_from_records(_runtime_agent_records(agents, None))
    finally:
        db.close()


def _get_agent_credentials_map(
    db: Session,
    user_id: int,
    project_token: Optional[str],
) -> Dict[str, models.AgentCredential]:
    creds_query = db.query(models.AgentCredential).filter(
        models.AgentCredential.owner_id == user_id
    )
    if project_token:
        creds_query = creds_query.filter(models.AgentCredential.project_token == project_token)
    else:
        creds_query = creds_query.filter(models.AgentCredential.project_token.is_(None))
    creds = creds_query.all()
    return {c.agent_id: c for c in creds}


def _ensure_default_agents(db: Session, project_token: Optional[str] = None) -> None:
    project_token = _normalize_project_token(project_token)
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


def _upsert_agent_credentials(
    db: Session,
    user_id: int,
    agent_id: str,
    git_repo_url: Optional[str] = None,
    git_token: Optional[str] = None,
    project_token: Optional[str] = None,
) -> models.AgentCredential:
    project_token = _normalize_project_token(project_token)
    cred_query = (
        db.query(models.AgentCredential)
        .filter(
            models.AgentCredential.owner_id == user_id,
            models.AgentCredential.agent_id == agent_id,
        )
    )
    if project_token:
        cred_query = cred_query.filter(models.AgentCredential.project_token == project_token)
    else:
        cred_query = cred_query.filter(models.AgentCredential.project_token.is_(None))
    cred = cred_query.first()
    if not cred:
        cred = models.AgentCredential(
            owner_id=user_id,
            agent_id=agent_id,
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


def _sanitize_agent_for_user(
    agent: Dict[str, Any],
    cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    safe_agent = dict(agent)
    if cred and cred.git_repo_url:
        safe_agent["git_repo_url"] = cred.git_repo_url
    safe_agent["has_git_token"] = bool(cred and cred.git_token)
    if "git_token" in safe_agent:
        safe_agent["git_token"] = None
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
):
    """Get status of all AI agents."""
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    query = db.query(models.Agent)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    records = query.all()
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

    creds_map = _get_agent_credentials_map(db, current_user.id, project_token)
    agents = [
        _sanitize_agent_for_user(agent, creds_map.get(agent.get("id")))
        for agent in agent_service.get_all_agents(project_token)
    ]
    return {"agents": agents}


@app.get("/agents/tasks")
async def get_pending_tasks(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """Get all pending tasks waiting to be picked up by agents."""
    project_token = _normalize_project_token(project_token)
    return {
        "pending_tasks": agent_service.get_pending_tasks(project_token),
        "completed_tasks": agent_service.get_completed_tasks(project_token),
    }


@app.post("/agents/tasks")
async def create_agent_task(
    request: CreateTaskRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Create a new pending task for agents to pick up."""
    task = agent_service.create_task(
        title=request.title,
        description=request.description,
        priority=request.priority,
    )
    return {"task": task}


@app.get("/agents/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """Get the current status and details of a specific agent."""
    try:
        project_token = _normalize_project_token(project_token)
        agent = agent_service.get_agent_status(agent_id, project_token)
        return {"agent": agent}
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

    cred = None
    if git_repo_url or git_token:
        cred = _upsert_agent_credentials(
            db,
            current_user.id,
            agent_id,
            git_repo_url=git_repo_url,
            git_token=git_token,
            project_token=project_token,
        )
    else:
        cred = _get_agent_credentials_map(db, current_user.id, project_token).get(agent_id)

    effective_repo = git_repo_url or (cred.git_repo_url if cred else None)
    effective_token = git_token or (cred.git_token if cred else None)

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
    Start all idle agents simultaneously in the BACKGROUND.
    Returns immediately — frontend polls /agents for real-time updates.
    """
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    query = db.query(models.Agent)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    records = query.all()
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

    idle_agents = [
        a for a in agent_service.get_all_agents(project_token)
        if a["status"] == "idle" and a["id"] != "agent_03"
    ]
    if not idle_agents:
        raise HTTPException(status_code=400, detail="No idle agents. Reset agents or add new ones.")

    agents_config = dict(request.agents_config) if request and request.agents_config else {}
    if agents_config:
        for agent_id, cfg in agents_config.items():
            if not cfg:
                continue
            _upsert_agent_credentials(
                db,
                current_user.id,
                agent_id,
                git_repo_url=cfg.get("git_repo_url"),
                git_token=cfg.get("git_token"),
                project_token=project_token,
            )

    creds_map = _get_agent_credentials_map(db, current_user.id, project_token)
    for agent in idle_agents:
        if agent["id"] in agents_config:
            continue
        cred = creds_map.get(agent["id"])
        if cred and cred.git_repo_url and cred.git_token:
            agents_config[agent["id"]] = {
                "git_repo_url": cred.git_repo_url,
                "git_token": cred.git_token,
            }

    # Fire-and-forget: all agents run in background
    # Note: run_all_agents synchronously marks them as "running" as its first step.
    bg_task = asyncio.create_task(
        agent_service.run_all_agents(
            agents_config=agents_config if agents_config else None,
            project_token=project_token,
            task_token=x_task_token,
        )
    )
    bg_task.add_done_callback(_log_background_task_result)

    return {
        "started": True,
        "agents": [a["id"] for a in idle_agents],
    }


class AddAgentRequest(BaseModel):
    name: Optional[str] = None
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None


@app.post("/agents/add")
async def add_agent(
    request: Optional[AddAgentRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    project_token: Optional[str] = None,
):
    """Dynamically add a new agent."""
    name = request.name if request else None
    git_repo_url = request.git_repo_url if request else None
    git_token = request.git_token if request else None
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    query = db.query(models.Agent)
    if project_token:
        query = query.filter(models.Agent.project_token == project_token)
    else:
        query = query.filter(models.Agent.project_token.is_(None))
    records = query.all()
    agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

    agent = agent_service.add_agent(
        name=name,
        git_repo_url=git_repo_url,
        git_token=git_token,
        project_token=project_token,
    )
    _upsert_agent_record(db, agent["id"], agent.get("name"), agent.get("type"), project_token)
    if git_repo_url or git_token:
        _upsert_agent_credentials(
            db,
            current_user.id,
            agent["id"],
            git_repo_url=git_repo_url,
            git_token=git_token,
            project_token=project_token,
        )
    return {"agent": agent}


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
            _upsert_agent_credentials(
                db,
                current_user.id,
                agent_id,
                git_repo_url=request.git_repo_url,
                git_token=request.git_token,
                project_token=project_token,
            )
        creds_map = _get_agent_credentials_map(db, current_user.id, project_token)
        return {"agent": _sanitize_agent_for_user(agent, creds_map.get(agent.get("id")))}
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
            _upsert_agent_credentials(
                db,
                current_user.id,
                agent_id,
                git_repo_url=request.git_repo_url,
                git_token=request.git_token,
                project_token=project_token,
            )
        creds_map = _get_agent_credentials_map(db, current_user.id, project_token)
        return {"agent": _sanitize_agent_for_user(agent, creds_map.get(agent.get("id")))}
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
        _ensure_default_agents(db, project_token)
        query = db.query(models.Agent)
        if project_token:
            query = query.filter(models.Agent.project_token == project_token)
        else:
            query = query.filter(models.Agent.project_token.is_(None))
        records = query.all()
        agent_service.ensure_project_initialized(project_token, _runtime_agent_records(records, project_token))

        agent_service.remove_agent(agent_id, project_token)
        _delete_agent_record(db, agent_id, project_token)
        return {"success": True, "removed": agent_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
# ─────────────────────────────── Task Management Integration ──────────────────────────

from task_service import task_service

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
    assignees: List[int]
    wallet: int
    deadline: str
    startdate: str
    task_type: str
    priority: str

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

@app.post("/api/agent/tasks/")
async def create_external_agent_task(
    task: AgentTaskCreate,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Create a new task in the external task management API."""
    try:
        result = await task_service.create_task(task.dict(), task_token=x_task_token)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create task: {e}")


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
    Fetch the list of tasks from the external task management API.
    """
    try:
        tasks = await task_service.get_tasks(page=page, task_token=x_task_token)
        return tasks
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {repr(e)}")

@app.get("/api/agent/project-info/")
async def get_agent_project_info(
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None)
):
    """Fetch project info (deadline, wallet, team) from the external task management API."""
    try:
        info = await task_service.get_project_info(task_token=x_task_token)
        return info
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch project info: {repr(e)}")

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

class AutoGenerateRequest(BaseModel):
    project_token: str
    prerequisites: Optional[List[Dict[str, Any]]] = None

@app.post("/api/agent/auto-generate/")
async def auto_generate_project_tasks(
    request: AutoGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    x_task_token: Optional[str] = Header(None)
):
    """
    Auto-generate tasks based on a BRD analysis, 
    using real project deadline and wallet from the external API.
    """
    try:
        # 1. Fetch initial project info from external API
        project_info = await task_service.get_project_info(task_token=x_task_token)
        project_data = project_info.get("project", {})
        project_deadline = project_data.get("deadline", "2026-12-31")
        project_wallet = project_data.get("project_wallet", 100)

        # 2. Fetch the governance response and BRD analysis from DB
        gov_response = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == request.project_token,
            models.GovernanceResponse.owner_id == current_user.id
        ).first()

        if not gov_response:
            raise HTTPException(status_code=404, detail="Project not found")

        user_documents = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id
        ).all()

        analysis_report = ""
        prerequisites_context = ""
        project_name = gov_response.project_name or ""

        for doc in user_documents:
            if not doc.analysis_result:
                continue
            import json as json_mod
            try:
                analysis = json_mod.loads(doc.analysis_result)
                gov_ctx = analysis.get("governanceContext") or {}
                proj_meta = analysis.get("projectMeta") or {}
                doc_result_id = proj_meta.get("governance_result_id") or gov_ctx.get("result_id")
                doc_token_id = proj_meta.get("project_token") or gov_ctx.get("project_token")
                doc_project_name = proj_meta.get("project_name") or gov_ctx.get("project_name") or ""

                if (doc_result_id is not None and str(doc_result_id) == str(gov_response.id)) or \
                   (doc_token_id and str(doc_token_id) == str(gov_response.project_token)) or \
                   (project_name and doc_project_name.strip().lower() == project_name.strip().lower()):
                    analysis_report = analysis.get("analysis", "")

                    # Extract prerequisites if available
                    prereqs = analysis.get("prerequisites", [])
                    if prereqs and isinstance(prereqs, list):
                        prereq_lines = ["\n\nPREREQUISITES & CREDENTIALS (confirmed by the team):"]
                        for p in prereqs:
                            name = p.get("name", "Unknown")
                            desc = p.get("description", "")
                            cat = p.get("category", "other")
                            priority = p.get("priority", "medium")
                            provided = p.get("provided", False)
                            status_str = "PROVIDED" if provided else "NOT YET PROVIDED"
                            notes = p.get("userNotes", "")
                            prereq_lines.append(
                                f"- [{status_str}] {name} ({cat}, {priority}): {desc}"
                                + (f" — Notes: {notes}" if notes else "")
                            )
                        prerequisites_context = "\n".join(prereq_lines)

                    if analysis_report:
                        break
            except (ValueError, AttributeError):
                continue

        if not analysis_report:
            raise HTTPException(status_code=400, detail="No BRD analysis found for this project.")

        # Append prerequisites context to the analysis report for task generation
        # Prefer prerequisites from stored analysis; if missing, use the ones sent from frontend
        if prerequisites_context:
            analysis_report += prerequisites_context
        elif request.prerequisites and isinstance(request.prerequisites, list) and len(request.prerequisites) > 0:
            prereq_lines = ["\n\nPREREQUISITES & CREDENTIALS (confirmed by the team):"]
            for p in request.prerequisites:
                name = p.get("name", "Unknown")
                desc = p.get("description", "")
                cat = p.get("category", "other")
                priority = p.get("priority", "medium")
                provided = p.get("provided", False)
                status_str = "PROVIDED" if provided else "NOT YET PROVIDED"
                notes = p.get("userNotes", "")
                prereq_lines.append(
                    f"- [{status_str}] {name} ({cat}, {priority}): {desc}"
                    + (f" — Notes: {notes}" if notes else "")
                )
            analysis_report += "\n".join(prereq_lines)

        # 3. Fetch Agents from external API
        team_members = project_info.get("team_members", [])
        if team_members:
            agents = team_members
        else:
            agents = await task_service.get_agents(task_token=x_task_token)
        
        # Ensure agent_ids is always defined by extracting from whichever list we got
        agent_ids = [a.get("user_id") or a.get("id") for a in agents if a.get("user_id") or a.get("id")]
        
        if not agent_ids:
            raise HTTPException(status_code=400, detail="No active agents found in the external system.")

        # 4. Build context from existing tasks so AI avoids duplicates across runs.
        existing_tasks_context: List[Dict[str, Any]] = []
        known_task_name_keys = set()
        existing_wallet_used = 0
        try:
            page = 1
            while True:
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

                for t in page_results:
                    task_name = (t.get("taskName") or t.get("title") or "").strip()
                    if not task_name:
                        continue
                    name_key = task_name.lower()
                    if name_key in known_task_name_keys:
                        continue
                    known_task_name_keys.add(name_key)

                    wallet_raw = t.get("task_wallet", t.get("wallet", 0))
                    try:
                        wallet_val = int(wallet_raw or 0)
                    except (TypeError, ValueError):
                        wallet_val = 0
                    existing_wallet_used += max(wallet_val, 0)

                    existing_tasks_context.append({
                        "taskName": task_name,
                        "task_type": t.get("task_type", "TASK"),
                        "wallet": max(wallet_val, 0),
                        "startdate": t.get("startdate"),
                        "deadline": t.get("deadline"),
                    })

                if not has_next:
                    break
                page += 1
        except Exception as e:
            logger.warning(f"Failed to fetch existing tasks for duplicate-context: {e}")

        try:
            project_wallet_int = int(project_wallet or 100)
        except (TypeError, ValueError):
            project_wallet_int = 100
        project_wallet_int = max(project_wallet_int, 0)

        remaining_wallet = max(project_wallet_int - existing_wallet_used, 0)
        if remaining_wallet <= 0:
            return {
                "status": "success",
                "message": (
                    "No wallet remaining for additional tasks. "
                    f"Existing tasks already consume ~{existing_wallet_used} wallet points."
                ),
                "tasks_created": 0,
                "batches_processed": 0,
                "duplicates_skipped": 0,
                "existing_tasks_considered": len(existing_tasks_context),
                "checklists_generated_for": 0,
                "checklists_attached": 0,
                "checklist_attach_failures": [],
                "project_deadline": project_deadline,
                "project_wallet": project_wallet_int,
                "remaining_wallet": remaining_wallet,
            }

        # 5. Generate tasks in incremental batches of up to 5, then attach checklists per batch.
        generation_context = list(existing_tasks_context)
        created_tasks: List[Dict[str, Any]] = []
        checklists_generated_for = 0
        checklists_attached = 0
        checklist_attach_failures: List[Dict[str, str]] = []
        duplicates_skipped = 0
        batches_processed = 0
        batch_number = 1
        max_batches = 20

        while remaining_wallet > 0 and batch_number <= max_batches:
            batch_tasks = await ai_service.generate_task_batch(
                analysis_report=analysis_report,
                agents=agents,
                project_deadline=project_deadline,
                remaining_wallet=remaining_wallet,
                total_project_wallet=project_wallet_int,
                already_created_tasks=generation_context,
                batch_number=batch_number,
            )
            if not batch_tasks:
                break
            # Hard guard: process max 5 per batch even if model returns more.
            batch_tasks = batch_tasks[:5]

            batches_processed += 1
            batch_created_tasks: List[Dict[str, Any]] = []
            batch_wallet_used = 0

            for task_data in batch_tasks:
                task_name = (task_data.get("taskName") or "").strip()
                if not task_name:
                    continue
                task_name_key = task_name.lower()
                if task_name_key in known_task_name_keys:
                    duplicates_skipped += 1
                    continue

                res = await task_service.create_task(task_data, task_token=x_task_token)
                if isinstance(res, dict) and "id" in res:
                    # Preserve generated values for downstream checklist generation / context.
                    res["taskName"] = task_name
                    res["description"] = task_data.get("description", "")
                    res["task_type"] = task_data.get("task_type", "")
                    res["priority"] = task_data.get("priority", "")
                    batch_created_tasks.append(res)
                    created_tasks.append(res)

                    wallet_raw = task_data.get("wallet", 1)
                    try:
                        wallet_val = int(wallet_raw or 1)
                    except (TypeError, ValueError):
                        wallet_val = 1
                    wallet_val = max(1, min(10, wallet_val))
                    batch_wallet_used += wallet_val

                    generation_context.append({
                        "taskName": task_name,
                        "task_type": task_data.get("task_type", "TASK"),
                        "wallet": wallet_val,
                        "startdate": task_data.get("startdate"),
                        "deadline": task_data.get("deadline"),
                    })
                    known_task_name_keys.add(task_name_key)
                else:
                    created_tasks.append(res)

            remaining_wallet = max(remaining_wallet - batch_wallet_used, 0)

            # Attach checklist immediately for this batch.
            if batch_created_tasks:
                try:
                    checklists_map = await ai_service.generate_checklists_for_tasks(
                        tasks_with_ids=batch_created_tasks,
                        analysis_report=analysis_report
                    )
                    if checklists_map:
                        for str_task_id, checklist_items in checklists_map.items():
                            if checklist_items:
                                checklists_generated_for += 1
                                try:
                                    await task_service.add_checklist_to_task(
                                        task_id=str_task_id,
                                        checklist_items=checklist_items,
                                        task_token=x_task_token
                                    )
                                    checklists_attached += 1
                                except Exception as checklist_err:
                                    checklist_attach_failures.append({
                                        "task_id": str(str_task_id),
                                        "error": str(checklist_err),
                                    })
                except Exception as e:
                    logger.warning(f"Failed checklist generation/attach for batch {batch_number}: {e}")

            # Avoid infinite loop when everything in a batch is duplicate/invalid.
            if not batch_created_tasks:
                break
            batch_number += 1

        message = (
            f"Successfully created {len(created_tasks)} task(s) across {batches_processed} batch(es) of up to 5. "
            f"Skipped {duplicates_skipped} duplicate task suggestion(s). "
        )
        if checklists_attached:
            message += f"Attached checklists to {checklists_attached} task(s)."
        elif checklists_generated_for:
            message += "Checklist generation succeeded but checklist attach failed."
        else:
            message += "No checklists were generated."

        return {
             "status": "success",
             "message": message,
             "tasks_created": len(created_tasks),
             "batches_processed": batches_processed,
             "duplicates_skipped": duplicates_skipped,
             "existing_tasks_considered": len(existing_tasks_context),
             "checklists_generated_for": checklists_generated_for,
             "checklists_attached": checklists_attached,
             "checklist_attach_failures": checklist_attach_failures,
             "project_deadline": project_deadline,
             "project_wallet": project_wallet_int,
             "remaining_wallet": remaining_wallet,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
