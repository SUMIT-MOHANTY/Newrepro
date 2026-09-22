"""
DSuite BRD Analyzer - Domain Router: Governance & Compliance & Project Revisions
Auto-extracted enterprise clean architecture domain router.
"""

import asyncio
import base64
import concurrent.futures
import hashlib
import html as html_lib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import requests
from fastapi import (
    APIRouter, Depends, File, Form, Header, HTTPException, Query,
    Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

import auth
import models
import schemas
from config import settings
from database import SessionLocal, engine, get_db

import governance_scoring


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Governance & Compliance"])

# --- Extracted Block (Lines 7941-8148) ---
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

@router.get("/governance/questions")
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

@router.get("/governance/questions/all", response_model=list[schemas.GovernanceQuestion])
async def get_all_governance_questions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not _can_manage_governance(db, current_user):
        raise HTTPException(status_code=403, detail="Only org admins or authorized governance roles can manage questions")
    
    return db.query(models.GovernanceQuestion).order_by(models.GovernanceQuestion.order).all()

@router.post("/governance/questions", response_model=schemas.GovernanceQuestion)
async def create_governance_question(
    question: schemas.GovernanceQuestionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not _can_manage_governance(db, current_user):
        raise HTTPException(status_code=403, detail="Only org admins or authorized governance roles can manage questions")
    
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

@router.put("/governance/questions/{question_id}", response_model=schemas.GovernanceQuestion)
async def update_governance_question(
    question_id: int,
    question_update: schemas.GovernanceQuestionUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not _can_manage_governance(db, current_user):
        raise HTTPException(status_code=403, detail="Only org admins or authorized governance roles can manage questions")
    
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

@router.delete("/governance/questions/{question_id}")
async def delete_governance_question(
    question_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not _can_manage_governance(db, current_user):
        raise HTTPException(status_code=403, detail="Only org admins or authorized governance roles can manage questions")
    
    db_question = db.query(models.GovernanceQuestion).filter(models.GovernanceQuestion.id == question_id).first()
    if not db_question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    db.delete(db_question)
    db.commit()
    return {"detail": "Question deleted"}

def _update_project_tags(db: Session, project: models.GovernanceResponse, tags_list: list[str]):
    # Delete existing tags
    db.query(models.ProjectTag).filter(models.ProjectTag.project_id == project.id).delete()
    db.flush()
    # Add new tags
    for t in tags_list:
        t_stripped = t.strip()
        if t_stripped:
            db.add(models.ProjectTag(name=t_stripped, project_id=project.id))
    db.flush()


# --- Extracted Block (Lines 8352-8809) ---
@router.post("/governance/submit", response_model=schemas.GovernanceResult)
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
            # Check if another user has this token
            conflicting_response = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token,
            ).first()
            if conflicting_response and conflicting_response.owner_id != current_user.id:
                # Generate a new unique token for this user instead of throwing an error
                # This handles cases where tokens might collide (e.g., cached tokens, incognito mode)
                project_token = str(uuid.uuid4())
                # Verify the new token is unique
                while db.query(models.GovernanceResponse).filter(
                    models.GovernanceResponse.project_token == project_token
                ).first():
                    project_token = str(uuid.uuid4())

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
        if not db_response.organization_name:
            db_response.organization_name = current_user.organization_name
        if request.client_id:
            db_response.client_id = request.client_id
        if request.client_secret:
            db_response.client_secret = request.client_secret
    else:
        db_response = models.GovernanceResponse(
            owner_id=current_user.id,
            project_token=project_token,
            organization_name=current_user.organization_name,
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
            current_revision_version=1,
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


@router.get("/governance/history")
async def get_governance_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get submission history for the current user.
    """
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))

    # Base filter: exclude archived projects
    not_archived = or_(
        models.GovernanceResponse.is_archived == None,
        models.GovernanceResponse.is_archived == False
    )

    if not organization_name:
        responses = (
            db.query(models.GovernanceResponse)
            .filter(
                models.GovernanceResponse.owner_id == current_user.id,
                not_archived
            )
            .order_by(models.GovernanceResponse.submission_date.desc())
            .all()
        )
    else:
        role_name, allowed_paths = _get_user_allowed_paths(db, current_user)
        can_view_org_governance = (
            bool(getattr(current_user, "is_org_admin", False))
            or "/governance-management" in (allowed_paths or [])
            or "/new-project/governance" in (allowed_paths or [])
        )
        
        if can_view_org_governance:
            responses = (
                db.query(models.GovernanceResponse)
                .filter(
                    func.lower(models.GovernanceResponse.organization_name) == organization_name.lower(),
                    not_archived
                )
                .order_by(models.GovernanceResponse.submission_date.desc())
                .all()
            )
        else:
            associated_tokens = db.query(models.UserProjectAssociation.project_token).filter(
                models.UserProjectAssociation.user_id == current_user.id
            ).scalar_subquery()
            responses = (
                db.query(models.GovernanceResponse)
                .filter(
                    func.lower(models.GovernanceResponse.organization_name) == organization_name.lower(),
                    not_archived,
                    or_(
                        models.GovernanceResponse.owner_id == current_user.id,
                        models.GovernanceResponse.project_token.in_(associated_tokens)
                    )
                )
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
                "classification": r.classification or 'PENDING',
                "pending_revision_reason": r.pending_revision_reason,
                "client_id": r.client_id,
                "client_secret": r.client_secret,
                # Include owner_id so frontend can distinguish pre-governance projects
                "owner_id": r.owner_id,
                "tags": [{"id": t.id, "name": t.name} for t in r.tags]
            }
            for r in responses
        ]
    }

class TagUpdateRequest(BaseModel):
    name: str

@router.get("/api/governance/projects/{project_token}/tags")
def get_project_tags(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    project_token = _normalize_project_token(project_token)
    project = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == project_token
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Permission check on organization
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if organization_name:
        if project.organization_name and project.organization_name.lower() != organization_name.lower():
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
            
    return [{"id": t.id, "name": t.name} for t in project.tags]

@router.put("/api/governance/tags/{tag_id}")
def update_project_tag(
    tag_id: int,
    payload: TagUpdateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    tag = db.query(models.ProjectTag).filter(models.ProjectTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
        
    project = tag.project
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if organization_name:
        if project.organization_name and project.organization_name.lower() != organization_name.lower():
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
            
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Tag name cannot be empty")
        
    # Check duplicate on same project
    exists = db.query(models.ProjectTag).filter(
        func.lower(models.ProjectTag.name) == new_name.lower(),
        models.ProjectTag.project_id == project.id,
        models.ProjectTag.id != tag_id
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Tag already exists in this project")
        
    tag.name = new_name
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name}

@router.delete("/api/governance/tags/{tag_id}")
def delete_project_tag(
    tag_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    tag = db.query(models.ProjectTag).filter(models.ProjectTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
        
    project = tag.project
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if organization_name:
        if project.organization_name and project.organization_name.lower() != organization_name.lower():
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
            
    db.delete(tag)
    db.commit()
    return {"success": True, "detail": "Tag deleted"}


@router.get("/governance/result/{identifier}")
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
        role_name, allowed_paths = _get_user_allowed_paths(db, current_user)
        can_view_org_governance = (
            bool(getattr(current_user, "is_org_admin", False))
            or "/governance-management" in (allowed_paths or [])
            or "/new-project/governance" in (allowed_paths or [])
        )
        if can_view_org_governance:
            query = db.query(models.GovernanceResponse).filter(
                func.lower(models.GovernanceResponse.organization_name) == organization_name.lower()
            )
        else:
            associated_tokens = db.query(models.UserProjectAssociation.project_token).filter(
                models.UserProjectAssociation.user_id == current_user.id
            ).scalar_subquery()
            query = db.query(models.GovernanceResponse).filter(
                func.lower(models.GovernanceResponse.organization_name) == organization_name.lower(),
                or_(
                    models.GovernanceResponse.owner_id == current_user.id,
                    models.GovernanceResponse.project_token.in_(associated_tokens)
                )
            )
    
    if identifier.isdigit():
        response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # Convert stored answers dict to list of GovernanceAnswer objects
    answers_list = []
    if response.answers and isinstance(response.answers, dict):
        for question_id, answer_data in response.answers.items():
            try:
                q_id_int = int(question_id)
            except (ValueError, TypeError):
                continue
            if isinstance(answer_data, dict):
                answers_list.append(schemas.GovernanceAnswer(
                    question_id=q_id_int,
                    score=answer_data.get('score', 0),
                    selected_option=answer_data.get(
                        'selected_option',
                        _lookup_selected_option(q_id_int, answer_data.get('score', 0))
                    )
                ))
            elif isinstance(answer_data, (int, float)):
                score_value = int(answer_data)
                answers_list.append(schemas.GovernanceAnswer(
                    question_id=q_id_int,
                    score=score_value,
                    selected_option=_lookup_selected_option(q_id_int, score_value),
                ))

    all_answers_skipped = _all_answers_skipped_from_payload(response.answers)
    classification_description = (
        ALL_SKIPPED_GOVERNANCE_MESSAGE
        if all_answers_skipped
        else _classification_description(response.classification or "")
    )
    hard_stops = [ALL_SKIPPED_HARD_STOP] if all_answers_skipped else []

    return schemas.GovernanceResult(
        id=response.id,
        project_token=response.project_token or str(response.id),
        project_name=response.project_name or "",
        submission_date=response.submission_date,
        dimension_scores=schemas.GovernanceDimensionScores(
            business_value=response.business_value_score or 0.0,
            data_sensitivity=response.data_sensitivity_score or 0.0,
            integration_complexity=response.integration_complexity_score or 0.0,
            operational_impact=response.operational_impact_score or 0.0,
            ai_risk=response.ai_risk_score or 0.0,
            ownership=response.ownership_score or 0.0,
        ),
        weighted_score=response.weighted_score or 0.0,
        classification=response.classification or "SANDBOX",
        classification_description=classification_description,
        recommendation=response.recommendation or "",
        pending_revision_reason=response.pending_revision_reason,
        hard_stops=hard_stops,
        answers=answers_list if answers_list else None,
        client_id=response.client_id,
        client_secret=response.client_secret,
        prerequisites_data=response.prerequisites_data,
        tags=[schemas.ProjectTagSchema(id=t.id, name=t.name) for t in response.tags],
    )


@router.get("/governance/prerequisites/{project_token}")
async def get_governance_prerequisites(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    gov = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == project_token
    ).first()
    if not gov:
        return {"prerequisites": []}
    return {"prerequisites": gov.prerequisites_data or []}


@router.post("/governance/prerequisites/{project_token}")
@router.post("/governance/prerequisites/complete/{project_token}")
async def save_governance_prerequisites(
    project_token: str,
    payload: Optional[schemas.PrerequisitesSaveRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    gov = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == project_token
    ).first()
    if not gov:
        gov = models.GovernanceResponse(
            project_token=project_token,
            owner_id=current_user.id,
            organization_name=_normalized_text(getattr(current_user, "organization_name", None)),
            project_name=f"Project {project_token[:8]}",
            submission_date=datetime.utcnow(),
            classification="PENDING"
        )
        db.add(gov)

    if payload and payload.prerequisites is not None:
        gov.prerequisites_data = payload.prerequisites

    gov.prerequisites_completed_at = datetime.utcnow()
    db.commit()
    db.refresh(gov)
    return {"status": "success", "prerequisites": gov.prerequisites_data or []}


# ─── NXDune Manual Sync Endpoints ───────────────────────────────────────────────

# --- Extracted Block (Lines 9121-9548) ---
@router.delete("/governance/{identifier}")
async def delete_governance_project(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Archive (soft-delete) a project — hides it from the UI but keeps all data in the database.
    """
    query = _governance_query_for_user(db, current_user)
    
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        # Fallback: try direct lookup by project_token or id (bypasses org scoping)
        # This handles pre-governance projects that may have been created
        # via ensure_project_exists but aren't yet visible to org-scoped queries.
        if identifier.isdigit():
            governance = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.id == int(identifier)
            ).first()
        else:
            governance = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == identifier
            ).first()

        if not governance:
            raise HTTPException(status_code=404, detail="Project not found")


    # Permission check: only the project owner OR an org admin can delete
    if governance.owner_id != current_user.id and not bool(getattr(current_user, 'is_org_admin', False)):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this project. Only the project owner or an organization admin can delete projects."
        )

    project_token = _normalize_project_token(governance.project_token or str(governance.id))
    archived_project_name = governance.project_name or "Untitled Project"
    archived_project_token = governance.project_token or str(governance.id)
    archived_result_id = governance.id

    # Soft-delete: set is_archived flag on governance and any linked share project
    governance.is_archived = True
    if archived_project_token:
        share_projs = db.query(models.ShareProject).filter(
            or_(
                models.ShareProject.project_token == archived_project_token,
                models.ShareProject.project_token == str(archived_result_id)
            )
        ).all()
        for sp in share_projs:
            sp.is_archived = True
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
        "status": "archived",
        "result_id": archived_result_id,
        "project_token": archived_project_token,
        "project_name": archived_project_name,
    }
    if cleanup_warnings:
        response["warnings"] = cleanup_warnings

    return response





@router.post("/governance/{identifier}/revision-reason")
async def update_revision_reason(
    identifier: str,
    payload: schemas.GovernanceRevisionReason,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the pending revision reason attached to a project.
    """
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="Project not found")
        
    response.pending_revision_reason = payload.reason
    db.commit()
    return {"status": "success", "pending_revision_reason": payload.reason}


# ===== REVISION MANAGEMENT ENDPOINTS =====

@router.get("/governance/{identifier}/revisions", response_model=List[schemas.RevisionResponse])
async def get_project_revisions(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all revision records for a project.
    """
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="Project not found")
    
    revisions = db.query(models.Revision).filter(
        models.Revision.project_token == response.project_token
    ).order_by(models.Revision.version_number.desc()).all()
    
    return revisions


@router.post("/governance/{identifier}/revisions", response_model=schemas.RevisionResponse)
async def create_revision(
    identifier: str,
    payload: schemas.RevisionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new revision for a project.
    
    This snapshots the current screening_inputs and document IDs,
    increments the revision version counter, and stores a new Revision record.
    """
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        gov_response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        gov_response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not gov_response:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_token = gov_response.project_token
    
    # Determine the next version number
    if payload.version_number is not None:
        next_version = payload.version_number
    else:
        # Auto-increment from current_revision_version
        next_version = (gov_response.current_revision_version or 0) + 1
    
    # Snapshot current screening_inputs from documents linked to this project
    linked_docs = db.query(models.Document).filter(
        models.Document.project_token == project_token
    ).all()
    
    doc_ids = [d.id for d in linked_docs]
    screening_inputs_snapshot = {}
    for d in linked_docs:
        if d.screening_inputs:
            screening_inputs_snapshot[str(d.id)] = d.screening_inputs
    
    # Snapshot the governance answers
    answers_snapshot = gov_response.answers if gov_response.answers else {}
    
    # Create the revision record
    revision = models.Revision(
        project_token=project_token,
        version_number=next_version,
        reason=payload.reason,
        screening_snapshot={
            "screening_inputs": screening_inputs_snapshot,
            "answers": answers_snapshot,
            "project_name": gov_response.project_name,
        },
        document_snapshots=doc_ids,
        created_by_user_id=current_user.id,
    )
    db.add(revision)
    
    # Update the project's current revision version
    gov_response.current_revision_version = next_version
    
    db.commit()
    db.refresh(revision)
    
    return revision


@router.post("/governance/{identifier}/revision-version")
async def update_current_revision_version(
    identifier: str,
    payload: schemas.RevisionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explicitly update the current revision version on a project.
    This is useful when starting a new revision cycle before uploading documents.
    """
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        gov_response = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        gov_response = query.filter(models.GovernanceResponse.project_token == identifier).first()
    
    if not gov_response:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if payload.version_number is not None:
        gov_response.current_revision_version = payload.version_number
    else:
        gov_response.current_revision_version = (gov_response.current_revision_version or 1) + 1
    
    if payload.reason:
        gov_response.pending_revision_reason = payload.reason
    
    db.commit()
    
    return {
        "status": "success",
        "project_token": gov_response.project_token,
        "current_revision_version": gov_response.current_revision_version,
        "pending_revision_reason": gov_response.pending_revision_reason,
    }


@router.post("/governance/{identifier}/prerequisites-complete")
async def mark_prerequisites_complete(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark prerequisites as completed for a project."""
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    governance.prerequisites_completed_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "completed_at": governance.prerequisites_completed_at.isoformat()}


@router.post("/governance/{identifier}/claude-md-files")
async def save_claude_md_files(
    identifier: str,
    files: List[Dict[str, Any]],
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save claude.md files for a project (always loaded for all agents)."""
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    governance.claude_md_files = files
    db.commit()

    return {"status": "ok", "files_count": len(files)}


@router.get("/governance/{identifier}/claude-md-files")
async def get_claude_md_files(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Get claude.md files for a project."""
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"files": governance.claude_md_files or []}


@router.post("/governance/{identifier}/skills-md-files")
async def save_skills_md_files(
    identifier: str,
    files: List[Dict[str, Any]],
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save skills.md files for a project (selectively loaded based on task relevance)."""
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    governance.skills_md_files = files
    db.commit()

    return {"status": "ok", "files_count": len(files)}


@router.get("/governance/{identifier}/skills-md-files")
async def get_skills_md_files(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Get skills.md files for a project."""
    query = _governance_query_for_user(db, current_user)
    if identifier.isdigit():
        governance = query.filter(models.GovernanceResponse.id == int(identifier)).first()
    else:
        governance = query.filter(models.GovernanceResponse.project_token == identifier).first()

    if not governance:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"files": governance.skills_md_files or []}


def parse_markdown_techniques(content: str) -> List[Dict[str, str]]:
    """Parse elicitation techniques from markdown skills files."""
    import re
    techniques = []
    if not content:
        return techniques

    lines = content.split('\n')
    current_name = None
    current_desc = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check for headings (# Name or ## Name or ### Name)
        if stripped.startswith('#'):
            if current_name:
                desc_str = '\n'.join(current_desc).strip()
                # Clean up "description:" or similar prefixes if any
                desc_str = re.sub(r'^(description|instructions?)\s*:\s*', '', desc_str, flags=re.IGNORECASE)
                techniques.append({
                    "name": current_name,
                    "description": desc_str
                })
            current_name = stripped.lstrip('#').strip()
            current_desc = []
        else:
            if current_name is not None:
                current_desc.append(stripped)

    if current_name and current_desc:
        desc_str = '\n'.join(current_desc).strip()
        desc_str = re.sub(r'^(description|instructions?)\s*:\s*', '', desc_str, flags=re.IGNORECASE)
        techniques.append({
            "name": current_name,
            "description": desc_str
        })

    # If heading-based parsing found techniques, return them
    if techniques:
        return techniques

    # Fallback to list-based parsing:
    # - **Brainstorming**: Generate divergent ideas...
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('-', '*', '+')) or (stripped and stripped[0].isdigit() and '. ' in stripped[:4]):
            # Remove list bullet
            item = re.sub(r'^[\-\*\+\d\.\s]+', '', stripped).strip()
            
            # Match formats like:
            # **Name**: Desc
            # **Name** - Desc
            # Name: Desc
            # Name -> Desc
            match = re.match(r'^\*?\*?([^\*:\-\>]+)\*?\*?\s*(?::|-|->)\s*(.+)$', item)
            if match:
                name = match.group(1).strip()
                desc = match.group(2).strip()
                techniques.append({
                    "name": name,
                    "description": desc
                })
                
    return techniques



# --- Extracted Block (Lines 9825-10290) ---
@router.get("/governance/{identifier}/roadmap-step")
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


