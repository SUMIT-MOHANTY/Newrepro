from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class GovernanceQuestionOptionBase(BaseModel):
    label: str
    score: int


class GovernanceQuestionOptionCreate(GovernanceQuestionOptionBase):
    pass


class GovernanceQuestionOption(GovernanceQuestionOptionBase):
    id: int
    question_id: int

    class Config:
        from_attributes = True


class GovernanceQuestionBase(BaseModel):
    dimension: str
    question_text: str
    order: int = 0
    is_active: bool = True


class GovernanceQuestion(GovernanceQuestionBase):
    id: int
    options: List[GovernanceQuestionOption] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GovernanceAnswer(BaseModel):
    question_id: int
    score: int
    selected_option: str


class GovernanceSubmission(BaseModel):
    project_name: str
    answers: List[GovernanceAnswer]
    project_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class GovernanceDimensionScores(BaseModel):
    business_value: Optional[float] = 0.0
    data_sensitivity: Optional[float] = 0.0
    integration_complexity: Optional[float] = 0.0
    operational_impact: Optional[float] = 0.0
    ai_risk: Optional[float] = 0.0
    ownership: Optional[float] = 0.0


class ProjectTagSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class GovernanceResult(BaseModel):
    id: int
    project_token: str
    project_name: Optional[str] = ""
    submission_date: Optional[datetime] = None
    tags: Optional[List[ProjectTagSchema]] = Field(default_factory=list)
    dimension_scores: Optional[GovernanceDimensionScores] = None
    weighted_score: Optional[float] = 0.0
    classification: Optional[str] = "SANDBOX"
    classification_description: Optional[str] = ""
    recommendation: Optional[str] = ""
    hard_stops: List[str] = Field(default_factory=list)
    pending_revision_reason: Optional[str] = None
    answers: Optional[List[GovernanceAnswer]] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


__all__ = [
    "GovernanceQuestionOptionBase",
    "GovernanceQuestionOptionCreate",
    "GovernanceQuestionOption",
    "GovernanceQuestionBase",
    "GovernanceQuestion",
    "GovernanceAnswer",
    "GovernanceSubmission",
    "GovernanceDimensionScores",
    "ProjectTagSchema",
    "GovernanceResult",
]
