"""
Repository layer for Todo domain
Implements data access patterns and query building
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from uuid import UUID

from django.db.models import Q, Count, QuerySet
from django.contrib.auth import get_user_model

from app.todos.models import Todo, Category, Tag

User = get_user_model()


class TodoRepository:
    """
    Repository for Todo data access.
    Implements query patterns and data operations for todos.
    """
    
    @staticmethod
    def get_user_todos(user: User) -> QuerySet:
        """Get all todos for a user."""
        return Todo.objects.filter(user=user)
    
    @staticmethod
    def get_todo_by_id(todo_id: UUID, user: User) -> Optional[Todo]:
        """Get a specific todo by ID for a user."""
        try:
            return Todo.objects.get(id=todo_id, user=user)
        except Todo.DoesNotExist:
            return None
    
    @staticmethod
    def filter_todos(
        queryset: QuerySet,
        is_completed: Optional[bool] = None,
        priority: Optional[str] = None,
        category: Optional[UUID] = None,
        tags: Optional[List[UUID]] = None,
        due_before: Optional[date] = None,
        due_after: Optional[date] = None,
        search: Optional[str] = None,
    ) -> QuerySet:
        """Apply filters to a todo queryset."""
        
        if is_completed is not None:
            queryset = queryset.filter(is_completed=is_completed)
        
        if priority:
            queryset = queryset.filter(priority=priority)
        
        if category:
            queryset = queryset.filter(category_id=category)
        
        if tags:
            queryset = queryset.filter(tags__id__in=tags).distinct()
        
        if due_before:
            queryset = queryset.filter(due_date__lte=due_before)
        
        if due_after:
            queryset = queryset.filter(due_date__gte=due_after)
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
        
        return queryset
    
    @staticmethod
    def order_todos(queryset: QuerySet, ordering: str = "-created_at") -> QuerySet:
        """Apply ordering to a todo queryset."""
        valid_orderings = [
            "created_at", "-created_at",
            "due_date", "-due_date",
            "priority", "-priority",
            "title", "-title",
            "sort_order", "-sort_order",
        ]
        
        if ordering in valid_orderings:
            # Special handling for priority ordering
            if ordering == "priority":
                queryset = queryset.order_by(
                    "-priority"  # Django will use the choices order
                )
            elif ordering == "-priority":
                queryset = queryset.order_by("priority")
            else:
                queryset = queryset.order_by(ordering)
        
        return queryset
    
    @staticmethod
    def get_overdue_todos(user: User) -> QuerySet:
        """Get all overdue todos for a user."""
        today = datetime.now().date()
        return Todo.objects.filter(
            user=user,
            is_completed=False,
            due_date__lt=today
        )
    
    @staticmethod
    def get_todos_due_today(user: User) -> QuerySet:
        """Get todos due today for a user."""
        today = datetime.now().date()
        return Todo.objects.filter(
            user=user,
            is_completed=False,
            due_date=today
        )
    
    @staticmethod
    def get_todos_due_this_week(user: User) -> QuerySet:
        """Get todos due this week for a user."""
        from datetime import timedelta
        today = datetime.now().date()
        week_end = today + timedelta(days=7)
        return Todo.objects.filter(
            user=user,
            is_completed=False,
            due_date__gte=today,
            due_date__lte=week_end
        )
    
    @staticmethod
    def bulk_delete(todo_ids: List[UUID], user: User) -> int:
        """Bulk delete todos. Returns number of deleted items."""
        return Todo.objects.filter(
            id__in=todo_ids,
            user=user
        ).delete()[0]
    
    @staticmethod
    def bulk_complete(
        todo_ids: List[UUID], 
        user: User, 
        is_completed: bool = True
    ) -> int:
        """Bulk mark todos as complete/incomplete. Returns number of updated items."""
        from django.utils import timezone
        
        todos = Todo.objects.filter(id__in=todo_ids, user=user)
        count = todos.count()
        
        for todo in todos:
            todo.is_completed = is_completed
            if is_completed:
                todo.completed_at = timezone.now()
            else:
                todo.completed_at = None
            todo.save(update_fields=["is_completed", "completed_at", "updated_at"])
        
        return count
    
    @staticmethod
    def get_statistics(user: User) -> Dict[str, Any]:
        """Get todo statistics for a user."""
        todos = Todo.objects.filter(user=user)
        
        total = todos.count()
        completed = todos.filter(is_completed=True).count()
        pending = total - completed
        
        # Overdue count
        today = datetime.now().date()
        overdue = todos.filter(
            is_completed=False,
            due_date__lt=today
        ).count()
        
        # By priority
        by_priority = dict(
            todos.filter(is_completed=False)
            .values("priority")
            .annotate(count=Count("id"))
            .values_list("priority", "count")
        )
        
        # By category
        by_category = dict(
            todos.filter(is_completed=False, category__isnull=False)
            .values("category__name")
            .annotate(count=Count("id"))
            .values_list("category__name", "count")
        )
        
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "overdue": overdue,
            "by_priority": by_priority,
            "by_category": by_category,
        }


class CategoryRepository:
    """
    Repository for Category data access.
    """
    
    @staticmethod
    def get_user_categories(user: User) -> QuerySet:
        """Get all categories for a user."""
        return Category.objects.filter(user=user)
    
    @staticmethod
    def get_category_by_id(category_id: UUID, user: User) -> Optional[Category]:
        """Get a specific category by ID for a user."""
        try:
            return Category.objects.get(id=category_id, user=user)
        except Category.DoesNotExist:
            return None
    
    @staticmethod
    def get_category_by_name(name: str, user: User) -> Optional[Category]:
        """Get a category by name for a user."""
        try:
            return Category.objects.get(name__iexact=name, user=user)
        except Category.DoesNotExist:
            return None


class TagRepository:
    """
    Repository for Tag data access.
    """
    
    @staticmethod
    def get_user_tags(user: User) -> QuerySet:
        """Get all tags for a user."""
        return Tag.objects.filter(user=user)
    
    @staticmethod
    def get_tag_by_id(tag_id: UUID, user: User) -> Optional[Tag]:
        """Get a specific tag by ID for a user."""
        try:
            return Tag.objects.get(id=tag_id, user=user)
        except Tag.DoesNotExist:
            return None
    
    @staticmethod
    def get_tag_by_name(name: str, user: User) -> Optional[Tag]:
        """Get a tag by name for a user."""
        try:
            return Tag.objects.get(name__iexact=name, user=user)
        except Tag.DoesNotExist:
            return None
    
    @staticmethod
    def get_or_create_tag(name: str, user: User, color: str = "#6B7280") -> Tag:
        """Get or create a tag for a user."""
        tag, created = Tag.objects.get_or_create(
            name__iexact=name,
            user=user,
            defaults={"name": name.strip(), "color": color}
        )
        return tag


__all__ = [
    "TodoRepository",
    "CategoryRepository",
    "TagRepository",
]
