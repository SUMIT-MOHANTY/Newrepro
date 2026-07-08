"""
Task Selection Service
Manages which tasks, sprints, and milestones are selected for execution by agents
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import models
import logging

logger = logging.getLogger(__name__)


class TaskSelectionService:
    """Service for managing task, sprint, and milestone selection"""
    
    @staticmethod
    def get_selected_tasks(db: Session, project_token: str, owner_id: int) -> List[models.Task]:
        """Get all tasks that are selected for execution"""
        return db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id,
            models.Task.is_selected_for_execution == True
        ).all()
    
    @staticmethod
    def get_selected_sprints(db: Session, project_token: str, owner_id: int) -> List[models.Sprint]:
        """Get all sprints that are selected for execution"""
        return db.query(models.Sprint).filter(
            models.Sprint.project_token == project_token,
            models.Sprint.owner_id == owner_id,
            models.Sprint.is_selected_for_execution == True
        ).all()
    
    @staticmethod
    def get_selected_milestones(db: Session, project_token: str, owner_id: int) -> List[models.Milestone]:
        """Get all milestones that are selected for execution"""
        return db.query(models.Milestone).filter(
            models.Milestone.project_token == project_token,
            models.Milestone.owner_id == owner_id,
            models.Milestone.is_selected_for_execution == True
        ).all()
    
    @staticmethod
    def toggle_task_selection(db: Session, task_id: str, project_token: str, owner_id: int, selected: bool) -> models.Task:
        """Toggle task selection status"""
        task = db.query(models.Task).filter(
            models.Task.task_id == task_id,
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id
        ).first()
        
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        task.is_selected_for_execution = selected
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task {task_id} selection set to {selected}")
        return task
    
    @staticmethod
    def toggle_sprint_selection(
        db: Session, 
        sprint_id: str, 
        project_token: str, 
        owner_id: int, 
        selected: bool,
        cascade_to_tasks: bool = True
    ) -> Dict[str, Any]:
        """
        Toggle sprint selection status
        
        Args:
            db: Database session
            sprint_id: Sprint identifier
            project_token: Project token
            owner_id: Owner user ID
            selected: Whether to select or deselect
            cascade_to_tasks: If True, also update all tasks in this sprint
        
        Returns:
            Dict with sprint and affected task count
        """
        sprint = db.query(models.Sprint).filter(
            models.Sprint.sprint_id == sprint_id,
            models.Sprint.project_token == project_token,
            models.Sprint.owner_id == owner_id
        ).first()
        
        if not sprint:
            raise ValueError(f"Sprint {sprint_id} not found")
        
        sprint.is_selected_for_execution = selected
        
        affected_tasks = 0
        if cascade_to_tasks:
            # Update all tasks in this sprint
            tasks = db.query(models.Task).filter(
                models.Task.project_token == project_token,
                models.Task.owner_id == owner_id,
                models.Task.sprint == sprint_id
            ).all()
            
            for task in tasks:
                task.is_selected_for_execution = selected
                affected_tasks += 1
        
        db.commit()
        db.refresh(sprint)
        
        logger.info(f"Sprint {sprint_id} selection set to {selected}, affected {affected_tasks} tasks")
        
        return {
            "sprint": sprint,
            "affected_tasks": affected_tasks
        }
    
    @staticmethod
    def toggle_milestone_selection(
        db: Session,
        milestone_id: str,
        project_token: str,
        owner_id: int,
        selected: bool,
        cascade_to_tasks: bool = True
    ) -> Dict[str, Any]:
        """
        Toggle milestone selection status
        
        Args:
            db: Database session
            milestone_id: Milestone identifier
            project_token: Project token
            owner_id: Owner user ID
            selected: Whether to select or deselect
            cascade_to_tasks: If True, also update all tasks in this milestone
        
        Returns:
            Dict with milestone and affected task count
        """
        milestone = db.query(models.Milestone).filter(
            models.Milestone.milestone_id == milestone_id,
            models.Milestone.project_token == project_token,
            models.Milestone.owner_id == owner_id
        ).first()
        
        if not milestone:
            raise ValueError(f"Milestone {milestone_id} not found")
        
        milestone.is_selected_for_execution = selected
        
        affected_tasks = 0
        if cascade_to_tasks:
            # Update all tasks in this milestone
            tasks = db.query(models.Task).filter(
                models.Task.project_token == project_token,
                models.Task.owner_id == owner_id,
                models.Task.milestone == milestone_id
            ).all()
            
            for task in tasks:
                task.is_selected_for_execution = selected
                affected_tasks += 1
        
        db.commit()
        db.refresh(milestone)
        
        logger.info(f"Milestone {milestone_id} selection set to {selected}, affected {affected_tasks} tasks")
        
        return {
            "milestone": milestone,
            "affected_tasks": affected_tasks
        }
    
    @staticmethod
    def bulk_update_task_selection(
        db: Session,
        task_ids: List[str],
        project_token: str,
        owner_id: int,
        selected: bool
    ) -> int:
        """Bulk update task selection status"""
        tasks = db.query(models.Task).filter(
            models.Task.task_id.in_(task_ids),
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id
        ).all()
        
        for task in tasks:
            task.is_selected_for_execution = selected
        
        db.commit()
        
        logger.info(f"Bulk updated {len(tasks)} tasks selection to {selected}")
        return len(tasks)
    
    @staticmethod
    def get_selection_summary(db: Session, project_token: str, owner_id: int) -> Dict[str, Any]:
        """Get summary of selected items for a project"""
        total_tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id
        ).count()
        
        selected_tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id,
            models.Task.is_selected_for_execution == True
        ).count()
        
        total_sprints = db.query(models.Sprint).filter(
            models.Sprint.project_token == project_token,
            models.Sprint.owner_id == owner_id
        ).count()
        
        selected_sprints = db.query(models.Sprint).filter(
            models.Sprint.project_token == project_token,
            models.Sprint.owner_id == owner_id,
            models.Sprint.is_selected_for_execution == True
        ).count()
        
        total_milestones = db.query(models.Milestone).filter(
            models.Milestone.project_token == project_token,
            models.Milestone.owner_id == owner_id
        ).count()
        
        selected_milestones = db.query(models.Milestone).filter(
            models.Milestone.project_token == project_token,
            models.Milestone.owner_id == owner_id,
            models.Milestone.is_selected_for_execution == True
        ).count()
        
        return {
            "tasks": {
                "total": total_tasks,
                "selected": selected_tasks,
                "unselected": total_tasks - selected_tasks
            },
            "sprints": {
                "total": total_sprints,
                "selected": selected_sprints,
                "unselected": total_sprints - selected_sprints
            },
            "milestones": {
                "total": total_milestones,
                "selected": selected_milestones,
                "unselected": total_milestones - selected_milestones
            }
        }
    
    @staticmethod
    def sync_sprint_and_milestone_from_tasks(db: Session, project_token: str, owner_id: int):
        """
        Create Sprint and Milestone records from existing tasks
        This is useful for migrating existing task data
        """
        tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id
        ).all()
        
        sprints_created = 0
        milestones_created = 0
        
        # Extract unique sprints and milestones from tasks
        sprint_ids = set()
        milestone_ids = set()
        
        for task in tasks:
            if task.sprint:
                sprint_ids.add(task.sprint)
            if task.milestone:
                milestone_ids.add(task.milestone)
        
        # Create sprint records
        for sprint_id in sprint_ids:
            existing = db.query(models.Sprint).filter(
                models.Sprint.sprint_id == sprint_id,
                models.Sprint.project_token == project_token,
                models.Sprint.owner_id == owner_id
            ).first()
            
            if not existing:
                sprint = models.Sprint(
                    sprint_id=sprint_id,
                    project_token=project_token,
                    owner_id=owner_id,
                    name=f"Sprint {sprint_id}" if sprint_id != "new" else "Sprint 1",
                    is_selected_for_execution=True
                )
                db.add(sprint)
                sprints_created += 1
        
        # Create milestone records
        for milestone_id in milestone_ids:
            existing = db.query(models.Milestone).filter(
                models.Milestone.milestone_id == milestone_id,
                models.Milestone.project_token == project_token,
                models.Milestone.owner_id == owner_id
            ).first()
            
            if not existing:
                milestone = models.Milestone(
                    milestone_id=milestone_id,
                    project_token=project_token,
                    owner_id=owner_id,
                    name=f"Milestone {milestone_id}" if milestone_id != "main" else "Main Milestone",
                    is_selected_for_execution=True
                )
                db.add(milestone)
                milestones_created += 1
        
        db.commit()
        
        logger.info(f"Synced {sprints_created} sprints and {milestones_created} milestones from tasks")
        
        return {
            "sprints_created": sprints_created,
            "milestones_created": milestones_created
        }


task_selection_service = TaskSelectionService()
