import uuid
from datetime import timedelta
from typing import Annotated, Optional, List, Dict, Any

from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

import auth
import models
import schemas
import ingestion
import ai_service
import governance_scoring
import github_service
from database import engine, get_db
from config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="BRD Analysis API", version="1.0.0")

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


@app.get("/governance/{identifier}/roadmap-step")
async def get_project_roadmap_step(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the current roadmap step for a project.

    Steps:
        0 - Governance  (assessment submitted)
        1 - Upload BRD  (document uploaded for this project)
        2 - AI Analysis (analysis completed on the document)
        3 - Complete     (workflow finished)

    The step is determined by inspecting:
        - GovernanceResponse existence → at least step 0 complete
        - Document rows linked to this governance result → step 1 complete
        - analysis_result present on those documents → step 2 complete
        - All of the above → step 3 (complete)
    """
    STEP_LABELS = ["Governance", "Upload BRD", "AI Analysis", "Complete"]

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

    # Step 0 is complete: governance submitted
    current_step = 1  # user is now at "Upload BRD"

    # 2. Find documents linked to this governance result
    #    Documents store a JSON `analysis_result` field that contains
    #    `projectMeta.governance_result_id` matching this result_id.
    #    We also match by project name as a fallback.
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

            # Check matches: numeric ID, project_token or project_name
            if (doc_result_id is not None and str(doc_result_id) == str(governance.id)) or \
               (doc_token_id and str(doc_token_id) == str(governance.project_token)) or \
               (project_name and doc_project_name.strip().lower() == project_name.strip().lower()):
                linked_docs.append(doc)
        except (json.JSONDecodeError, AttributeError):
            continue

    if linked_docs:
        # Step 1 complete: at least one document uploaded
        current_step = 2  # user is now at "AI Analysis"

        # 3. Check if any document has a completed AI analysis
        has_analysis = any(
            _doc_has_completed_analysis(doc) for doc in linked_docs
        )
        if has_analysis:
            current_step = 3  # Workflow complete

    return {
        "result_id": governance.id,
        "project_token": governance.project_token or str(governance.id),
        "project_name": governance.project_name,
        "current_step": current_step,
        "current_step_label": STEP_LABELS[current_step],
        "total_steps": len(STEP_LABELS),
        "steps": STEP_LABELS,
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
        context = await github_service.build_repo_context(
            current_user.github_token,
            payload.owner,
            payload.repo,
            payload.branch,
        )
        return {"context": context, "repo": f"{payload.owner}/{payload.repo}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build repo context: {e}")
