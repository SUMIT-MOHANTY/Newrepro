from typing import Optional
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

from datetime import datetime

class DocumentBase(BaseModel):
    filename: str
    content_preview: Optional[str] = None
    full_content: Optional[str] = None
    analysis_result: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    upload_date: datetime
    owner_id: int

    class Config:
        from_attributes = True

class GovernanceRevisionReason(BaseModel):
    reason: Optional[str] = None

# ===== GOVERNANCE QUESTIONNAIRE =====

class GovernanceAnswer(BaseModel):
    """Single answer to a governance question"""
    question_id: int  # 1-17
    score: int        # 0-3, or special values like +2
    selected_option: str  # The text of the selected option

class GovernanceSubmission(BaseModel):
    """User submits answers to all 17 questions"""
    project_name: str
    answers: list[GovernanceAnswer]  # All 17 answers

class GovernanceDimensionScores(BaseModel):
    """Calculated dimension scores (each 0-10)"""
    business_value: float
    data_sensitivity: float
    integration_complexity: float
    operational_impact: float
    ai_risk: float
    ownership: float

class GovernanceResult(BaseModel):
    """Final governance scoring result"""
    id: int
    project_token: str
    project_name: str
    submission_date: datetime
    
    # Individual dimension scores (0-10)
    dimension_scores: GovernanceDimensionScores
    
    # Weighted composite score (0-10)
    weighted_score: float
    
    # Classification
    classification: str  # SANDBOX, CONTROLLED_SANDBOX, ENTERPRISE
    classification_description: str
    
    # Recommendation with reasoning
    recommendation: str
    
    # Hard stops triggered (if any)
    hard_stops: list[str] = []
    
    # Active revision reason attached directly to the project
    pending_revision_reason: Optional[str] = None
    
    # Original question answers (optional, included when fetching detailed result)
    answers: Optional[list[GovernanceAnswer]] = None
    
    class Config:
        from_attributes = True