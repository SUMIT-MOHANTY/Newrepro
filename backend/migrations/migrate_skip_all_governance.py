"""Migration script to update roadmap data for existing skip-all governance projects.

This script finds all governance responses where classification == "ENTERPRISE" 
and weighted_score == 5.0 (skip-all cases) and updates their roadmap data to 
set Governance step as "active" instead of "completed".
"""
import json
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

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

GOVERNANCE_IDX = 2


def migrate():
    """Update roadmap data for skip-all governance projects."""
    db: Session = SessionLocal()
    
    try:
        # Find all skip-all governance cases
        skip_all_projects = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.classification == "ENTERPRISE",
            models.GovernanceResponse.weighted_score == 5.0
        ).all()
        
        print(f"Found {len(skip_all_projects)} skip-all governance projects")
        
        updated_count = 0
        for project in skip_all_projects:
            print(f"\nProcessing project: {project.project_name} (ID: {project.id}, Token: {project.project_token})")
            
            # Create step_statuses array with Governance as active
            step_statuses = ["pending"] * len(STEP_LABELS)
            step_statuses[0] = "completed"  # Project Initiation
            step_statuses[1] = "completed"  # Requirement Screening
            step_statuses[GOVERNANCE_IDX] = "active"  # Governance (skip-all case)
            # All subsequent steps remain "pending"
            
            # Create or update steps_data
            steps_data = {
                "steps": STEP_LABELS,
                "step_statuses": step_statuses,
                "current_step": GOVERNANCE_IDX,  # Governance step index
                "current_step_label": "Governance",
                "failed_step": None,
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            # Update the project's steps_data
            project.steps_data = steps_data
            db.commit()
            
            updated_count += 1
            print(f"  ✓ Updated roadmap: Governance set as active, current_step={GOVERNANCE_IDX}")
        
        print(f"\n{'='*60}")
        print(f"Migration completed successfully!")
        print(f"Updated {updated_count} skip-all governance project(s)")
        print(f"{'='*60}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during migration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("="*60)
    print("Skip-All Governance Roadmap Migration Script")
    print("="*60)
    print("\nThis script will update roadmap data for all skip-all")
    print("governance projects (ENTERPRISE classification with score 5.0)")
    print("to set Governance step as 'active' instead of 'completed'.\n")
    
    migrate()
