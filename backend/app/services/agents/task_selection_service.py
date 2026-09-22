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
            (models.Task.selected == True) | (models.Task.synced_to_nxdune == True)
        ).all()
    
    @staticmethod
    def get_selected_sprints(db: Session, project_token: str, owner_id: int) -> List[str]:
        """Get list of sprint IDs that have selected tasks"""
        tasks = TaskSelectionService.get_selected_tasks(db, project_token, owner_id)
        return list({t.sprint for t in tasks if t.sprint})
    
    @staticmethod
    def get_selected_milestones(db: Session, project_token: str, owner_id: int) -> List[str]:
        """Get list of milestone IDs that have selected tasks"""
        tasks = TaskSelectionService.get_selected_tasks(db, project_token, owner_id)
        return list({t.milestone for t in tasks if t.milestone})
    
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
        
        task.selected = selected
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
        """Toggle selection status for all tasks in a sprint"""
        tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id,
            models.Task.sprint == sprint_id
        ).all()
        
        affected_tasks = 0
        for task in tasks:
            task.selected = selected
            affected_tasks += 1
        
        db.commit()
        logger.info(f"Sprint {sprint_id} selection set to {selected}, affected {affected_tasks} tasks")
        
        return {
            "sprint_id": sprint_id,
            "affected_tasks": affected_tasks,
            "selected": selected
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
        """Toggle selection status for all tasks in a milestone"""
        tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id,
            models.Task.milestone == milestone_id
        ).all()
        
        affected_tasks = 0
        for task in tasks:
            task.selected = selected
            affected_tasks += 1
        
        db.commit()
        logger.info(f"Milestone {milestone_id} selection set to {selected}, affected {affected_tasks} tasks")
        
        return {
            "milestone_id": milestone_id,
            "affected_tasks": affected_tasks,
            "selected": selected
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
            task.selected = selected
        
        db.commit()
        
        logger.info(f"Bulk updated {len(tasks)} tasks selection to {selected}")
        return len(tasks)
    
    @staticmethod
    def get_selection_summary(db: Session, project_token: str, owner_id: int) -> Dict[str, Any]:
        """Get summary of selected items for a project"""
        all_tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.owner_id == owner_id
        ).all()
        
        total_tasks = len(all_tasks)
        selected_tasks = len([t for t in all_tasks if t.selected or t.synced_to_nxdune])
        
        sprints = {t.sprint for t in all_tasks if t.sprint}
        selected_sprints = {t.sprint for t in all_tasks if t.sprint and (t.selected or t.synced_to_nxdune)}
        
        milestones = {t.milestone for t in all_tasks if t.milestone}
        selected_milestones = {t.milestone for t in all_tasks if t.milestone and (t.selected or t.synced_to_nxdune)}
        
        return {
            "tasks": {
                "total": total_tasks,
                "selected": selected_tasks,
                "unselected": total_tasks - selected_tasks
            },
            "sprints": {
                "total": len(sprints),
                "selected": len(selected_sprints),
                "unselected": len(sprints) - len(selected_sprints)
            },
            "milestones": {
                "total": len(milestones),
                "selected": len(selected_milestones),
                "unselected": len(milestones) - len(selected_milestones)
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
