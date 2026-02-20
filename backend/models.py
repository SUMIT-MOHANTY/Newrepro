from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, JSON, Float
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

    documents = relationship("Document", back_populates="owner")
    governance_responses = relationship("GovernanceResponse", back_populates="owner")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    content_preview = Column(String, nullable=True) # First few chars of extraction
    full_content = Column(String, nullable=True)    # Full markdown content
    analysis_result = Column(String, nullable=True) # JSON string of analysis
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="documents")

class GovernanceResponse(Base):
    __tablename__ = "governance_responses"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    project_name = Column(String, index=True)
    submission_date = Column(DateTime, default=datetime.utcnow)
    
    # Store all 17 question answers as JSON
    answers = Column(JSON)  # Dict mapping question_id -> score
    
    # Computed scores
    business_value_score = Column(Float, nullable=True)
    data_sensitivity_score = Column(Float, nullable=True)
    integration_complexity_score = Column(Float, nullable=True)
    operational_impact_score = Column(Float, nullable=True)
    ai_risk_score = Column(Float, nullable=True)
    ownership_score = Column(Float, nullable=True)
    
    # Final weighted score (0-10)
    weighted_score = Column(Float, nullable=True)
    
    # Classification result
    classification = Column(String)  # SANDBOX, CONTROLLED_SANDBOX, ENTERPRISE
    # Recommendation with reasoning
    recommendation = Column(Text)  # Detailed recommendation text

    # Tracks an active request to start a new BRD revision on this project
    pending_revision_reason = Column(String, nullable=True)

    owner = relationship("User", back_populates="governance_responses")
