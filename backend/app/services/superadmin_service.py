"""
SuperAdmin & Billing Service Layer
Business logic for SuperAdmin dashboard telemetry, organization capacity governance,
billing email execution, and Todo application admin statistics.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from django.db import models as django_models
from django.utils import timezone

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.agent import CapacityIncreaseRequest, OrganizationAgentQuota
from backend.models import User
from app.todos.models import Todo, Category
from app.repositories.billing_repository import billing_repository
from app.schemas.billing import (
    SuperAdminDashboardStatsResponse,
    SuperAdminCapUpdate,
    CapacityIncreaseRequestReview,
    OrganizationCostSummary,
)
from app.schemas.admin import (
    SystemStatsSerializer,
    UserActivitySerializer,
    TodoAnalyticsSerializer,
    UserActivitySummary,
    PriorityDistributionItem,
    StatusDistributionItem,
    CategoryDistributionItem,
    RecentActivityItem,
    SystemHealthStatus,
)
from app.workers.daily_billing_worker import daily_billing_worker

logger = logging.getLogger(__name__)


class SuperAdminService:
    def __init__(self):
        self.repo = billing_repository
        self.billing_worker = daily_billing_worker

    def assert_super_admin(self, user: User) -> None:
        """Enforce strict SuperAdmin authorization."""
        if not getattr(user, "is_super_admin", False):
            raise ForbiddenException("SuperAdmin privileges are required for this action")

    def get_dashboard_stats(self, db, user: User) -> SuperAdminDashboardStatsResponse:
        self.assert_super_admin(user)
        stats = self.repo.get_platform_dashboard_stats(db)
        return SuperAdminDashboardStatsResponse(**stats)

    def list_organizations(self, db, user: User) -> List[OrganizationCostSummary]:
        self.assert_super_admin(user)
        raw_summaries = self.repo.list_organization_costs(db)
        return [OrganizationCostSummary(**s) for s in raw_summaries]

    def update_organization_capacity(
        self,
        db,
        user: User,
        org_name: str,
        payload: SuperAdminCapUpdate,
    ) -> OrganizationAgentQuota:
        self.assert_super_admin(user)
        if payload.max_agent_capacity <= 0:
            raise ValidationException("Agent capacity must be a positive integer")

        quota = self.repo.update_organization_capacity(db, org_name, payload.max_agent_capacity)
        return quota

    def list_capacity_requests(
        self,
        db,
        user: User,
        status: Optional[str] = None,
    ) -> List[CapacityIncreaseRequest]:
        self.assert_super_admin(user)
        return self.repo.list_capacity_requests(db, status=status)

    def review_capacity_request(
        self,
        db,
        user: User,
        request_id: int,
        action: str,  # 'approve' or 'reject'
        review_data: Optional[CapacityIncreaseRequestReview] = None,
    ) -> CapacityIncreaseRequest:
        self.assert_super_admin(user)
        if action not in ["approve", "reject"]:
            raise ValidationException(f"Invalid review action '{action}'")

        status = "approved" if action == "approve" else "rejected"
        approved_capacity = review_data.approved_capacity if review_data else None
        comment = review_data.comment if review_data else None

        req = self.repo.review_capacity_request(
            db=db,
            request_id=request_id,
            status=status,
            reviewer_id=user.id,
            approved_capacity=approved_capacity,
            comment=comment,
        )
        if not req:
            raise NotFoundException(f"Capacity request {request_id} not found")
        return req

    # ── Daily Billing Controls & Triggers ───────────────────────────────────────

    def get_email_controls(self, user: User) -> Dict[str, Any]:
        self.assert_super_admin(user)
        return self.billing_worker.get_controls()

    def update_email_controls(self, user: User, controls: Dict[str, Any]) -> Dict[str, Any]:
        self.assert_super_admin(user)
        success = self.billing_worker.update_controls(controls)
        return {"success": success, "controls": controls}

    async def trigger_billing_emails(self, db, user: User) -> Dict[str, Any]:
        self.assert_super_admin(user)
        return await self.billing_worker.trigger_dispatch(db)


class AdminService:
    """
    AdminService for Todo Application Statistics
    Provides aggregation queries for system monitoring and admin dashboard.
    Uses Django ORM for database queries.
    """

    def __init__(self):
        pass

    def _check_superuser(self, user: User) -> None:
        """Verify user has superuser privileges."""
        if not getattr(user, "is_superuser", False) and not getattr(user, "is_super_admin", False):
            raise ForbiddenException("Superuser privileges are required for this action")

    def get_system_stats(self, db, user: User, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive system statistics for admin dashboard.
        
        Args:
            db: Database session (unused, Django ORM manages its own connections)
            user: Current user (must be superuser)
            days: Number of days to include in stats (default 30)
            
        Returns:
            Dictionary containing system statistics
        """
        self._check_superuser(user)
        
        now = timezone.now()
        cutoff_date = now - timedelta(days=days)
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        
        # User Statistics
        user_stats = self._get_user_activity_stats(cutoff_date, last_7_days, last_30_days)
        
        # Todo Statistics
        todo_stats = self._get_todo_analytics(cutoff_date, last_7_days, last_30_days)
        
        # Recent Activity
        recent_activity = self._get_recent_activity(limit=50)
        
        # System Health
        system_health = self._get_system_health_status()
        
        return {
            "timestamp": now,
            "system_health": system_health,
            "user_stats": user_stats,
            "todo_stats": todo_stats,
            "recent_activity": recent_activity,
            "generated_at": now,
            "version": "1.0.0"
        }

    def _get_user_activity_stats(
        self, 
        cutoff_date: datetime,
        last_7_days: datetime,
        last_30_days: datetime
    ) -> Dict[str, Any]:
        """Calculate user activity statistics using Django ORM."""
        
        # Total users
        total_users = User.objects.count()
        
        # Active users (users who have created or updated todos recently)
        active_users_7d = Todo.objects.filter(
            django_models.Q(created_at__gte=last_7_days) |
            django_models.Q(updated_at__gte=last_7_days)
        ).values('user').distinct().count()
        
        active_users_30d = Todo.objects.filter(
            django_models.Q(created_at__gte=last_30_days) |
            django_models.Q(updated_at__gte=last_30_days)
        ).values('user').distinct().count()
        
        # New users (registered recently) - using date_joined
        new_users_7d = User.objects.filter(
            date_joined__gte=last_7_days
        ).count()
        
        new_users_30d = User.objects.filter(
            date_joined__gte=last_30_days
        ).count()
        
        # Top users by todo count
        top_by_todos_query = Todo.objects.values('user').annotate(
            todo_count=django_models.Count('id')
        ).order_by('-todo_count')[:10]
        
        top_users_by_todos = []
        for item in top_by_todos_query:
            try:
                user_obj = User.objects.filter(id=item['user']).first()
                if not user_obj:
                    continue
                
                todo_count = item['todo_count']
                completed = Todo.objects.filter(
                    user=user_obj,
                    is_completed=True
                ).count()
                
                pending = todo_count - completed
                completion_rate = (completed / todo_count * 100) if todo_count > 0 else 0
                
                last_activity_result = Todo.objects.filter(
                    user=user_obj
                ).aggregate(
                    last_activity=django_models.Max('updated_at')
                )['last_activity']
                
                # Build display name from available fields
                first_name = getattr(user_obj, 'first_name', '') or ''
                last_name = getattr(user_obj, 'last_name', '') or ''
                email = getattr(user_obj, 'email', '') or ''
                display_name = f"{first_name} {last_name}".strip() or email or "Unknown"
                
                top_users_by_todos.append({
                    "user_id": str(user_obj.id),
                    "username": display_name,
                    "email": email,
                    "total_todos": todo_count,
                    "completed_todos": completed,
                    "pending_todos": pending,
                    "completion_rate": round(completion_rate, 2),
                    "last_activity": last_activity_result
                })
            except Exception:
                continue
        
        # Top users by completion rate (min 5 todos)
        users_with_counts = Todo.objects.values('user').annotate(
            total=django_models.Count('id'),
            completed=django_models.Count(
                django_models.Case(
                    django_models.When(is_completed=True, then=1),
                    output_field=django_models.IntegerField()
                )
            )
        ).filter(total__gte=5)
        
        top_by_completion = []
        for item in users_with_counts:
            total = item['total']
            completed = item['completed']
            if total >= 5:
                completion_rate = (completed / total * 100)
                try:
                    user_obj = User.objects.filter(id=item['user']).first()
                    if not user_obj:
                        continue
                    
                    last_activity_result = Todo.objects.filter(
                        user=user_obj
                    ).aggregate(
                        last_activity=django_models.Max('updated_at')
                    )['last_activity']
                    
                    first_name = getattr(user_obj, 'first_name', '') or ''
                    last_name = getattr(user_obj, 'last_name', '') or ''
                    email = getattr(user_obj, 'email', '') or ''
                    display_name = f"{first_name} {last_name}".strip() or email or "Unknown"
                    
                    top_by_completion.append({
                        "user_id": str(user_obj.id),
                        "username": display_name,
                        "email": email,
                        "total_todos": total,
                        "completed_todos": completed,
                        "pending_todos": total - completed,
                        "completion_rate": round(completion_rate, 2),
                        "last_activity": last_activity_result
                    })
                except Exception:
                    continue
        
        # Sort by completion rate descending and take top 10
        top_by_completion.sort(key=lambda x: x['completion_rate'], reverse=True)
        top_by_completion = top_by_completion[:10]
        
        return {
            "total_users": total_users,
            "active_users_last_7_days": active_users_7d,
            "active_users_last_30_days": active_users_30d,
            "new_users_last_7_days": new_users_7d,
            "new_users_last_30_days": new_users_30d,
            "top_users_by_todos": top_users_by_todos,
            "top_users_by_completion_rate": top_by_completion
        }

    def _get_todo_analytics(
        self,
        cutoff_date: datetime,
        last_7_days: datetime,
        last_30_days: datetime
    ) -> Dict[str, Any]:
        """Calculate todo analytics and statistics using Django ORM."""
        
        now = timezone.now()
        today = now.date()
        
        # Basic counts
        total_todos = Todo.objects.count()
        completed_todos = Todo.objects.filter(is_completed=True).count()
        pending_todos = total_todos - completed_todos
        
        # Overdue todos
        overdue_todos = Todo.objects.filter(
            is_completed=False,
            due_date__lt=today
        ).count()
        
        # Completion rate
        completion_rate = (completed_todos / total_todos) if total_todos > 0 else 0.0
        
        # Average completion time (for completed todos with completed_at)
        avg_completion_time = None
        completed_with_time = Todo.objects.filter(
            is_completed=True,
            completed_at__isnull=False
        )
        
        if completed_with_time.exists():
            # Calculate average duration in hours using Django ORM
            durations = []
            for todo_item in completed_with_time:
                if todo_item.created_at and todo_item.completed_at:
                    duration = (todo_item.completed_at - todo_item.created_at).total_seconds() / 3600
                    durations.append(duration)
            if durations:
                avg_completion_time = sum(durations) / len(durations)
        
        # Todos by priority
        todos_by_priority = []
        priority_counts = Todo.objects.values('priority').annotate(
            count=django_models.Count('id')
        ).order_by('priority')
        
        for item in priority_counts:
            todos_by_priority.append({
                "priority": item['priority'] or "unspecified",
                "count": item['count']
            })
        
        # Todos by status
        todos_by_status = [
            {"status": "completed", "count": completed_todos},
            {"status": "pending", "count": pending_todos},
            {"status": "overdue", "count": overdue_todos}
        ]
        
        # Todos by category
        todos_by_category = []
        category_counts = Todo.objects.filter(
            category__isnull=False
        ).values('category__name').annotate(
            count=django_models.Count('id')
        ).order_by('category__name')
        
        for item in category_counts:
            todos_by_category.append({
                "category": item['category__name'] or "uncategorized",
                "count": item['count']
            })
        
        # Time-based statistics
        created_last_7d = Todo.objects.filter(
            created_at__gte=last_7_days
        ).count()
        
        created_last_30d = Todo.objects.filter(
            created_at__gte=last_30_days
        ).count()
        
        completed_last_7d = Todo.objects.filter(
            is_completed=True,
            completed_at__gte=last_7_days
        ).count()
        
        completed_last_30d = Todo.objects.filter(
            is_completed=True,
            completed_at__gte=last_30_days
        ).count()
        
        return {
            "total_todos": total_todos,
            "completed_todos": completed_todos,
            "pending_todos": pending_todos,
            "overdue_todos": overdue_todos,
            "completion_rate": round(completion_rate, 4),
            "average_completion_time_hours": round(avg_completion_time, 2) if avg_completion_time else None,
            "todos_by_priority": todos_by_priority,
            "todos_by_status": todos_by_status,
            "todos_by_category": todos_by_category,
            "created_last_7_days": created_last_7d,
            "created_last_30_days": created_last_30d,
            "completed_last_7_days": completed_last_7d,
            "completed_last_30_days": completed_last_30d
        }

    def _get_recent_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent system activity using Django ORM."""
        
        # Get recent todos with activity
        recent_todos = Todo.objects.order_by('-updated_at')[:limit]
        
        activity_items = []
        for todo_item in recent_todos:
            # Determine activity type based on todo state
            # Access the actual Todo model instance attributes directly
            if todo_item.is_completed and todo_item.completed_at:
                activity_type = "completed"
                timestamp = todo_item.completed_at
            elif todo_item.created_at == todo_item.updated_at:
                activity_type = "created"
                timestamp = todo_item.created_at
            else:
                activity_type = "updated"
                timestamp = todo_item.updated_at
            
            # Get user display name from the related user object
            todo_user = todo_item.user
            if todo_user:
                first_name = getattr(todo_user, 'first_name', '') or ''
                last_name = getattr(todo_user, 'last_name', '') or ''
                email = getattr(todo_user, 'email', '') or ''
                display_name = f"{first_name} {last_name}".strip() or email or "Unknown"
            else:
                display_name = "Unknown"
                email = ""
            
            activity_items.append({
                "activity_type": activity_type,
                "todo_id": str(todo_item.id),
                "todo_title": todo_item.title,
                "user_id": str(todo_item.user.id) if todo_item.user else "",
                "username": display_name,
                "timestamp": timestamp,
                "details": None
            })
        
        return activity_items

    def _get_system_health_status(self) -> Dict[str, Any]:
        """Check system health indicators."""
        
        # Check database connection
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_status = "healthy"
        except Exception:
            db_status = "unhealthy"
        
        return {
            "database_status": db_status,
            "api_status": "healthy",
            "last_checked": timezone.now()
        }

    def get_user_activity(self, db, user: User, days: int = 30) -> Dict[str, Any]:
        """
        Get user activity statistics.
        
        Args:
            db: Database session (unused, Django ORM manages its own connections)
            user: Current user (must be superuser)
            days: Number of days to include in stats
            
        Returns:
            User activity statistics
        """
        self._check_superuser(user)
        
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        cutoff_date = now - timedelta(days=days)
        
        return self._get_user_activity_stats(cutoff_date, last_7_days, last_30_days)

    def get_todo_analytics(self, db, user: User, days: int = 30) -> Dict[str, Any]:
        """
        Get todo analytics and statistics.
        
        Args:
            db: Database session (unused, Django ORM manages its own connections)
            user: Current user (must be superuser)
            days: Number of days to include in stats
            
        Returns:
            Todo analytics statistics
        """
        self._check_superuser(user)
        
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        cutoff_date = now - timedelta(days=days)
        
        return self._get_todo_analytics(cutoff_date, last_7_days, last_30_days)


# Global service instances
superadmin_service = SuperAdminService()
admin_service = AdminService()
