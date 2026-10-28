"""
Service layer for Todo domain
Implements business logic and orchestrates repository operations
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound, PermissionDenied

from app.todos.models import Todo, Category, Tag
from app.repositories.todo_repository import TodoRepository, CategoryRepository, TagRepository

User = get_user_model()


class TodoService:
    """
    Service for Todo business logic.
    Orchestrates repository operations and enforces business rules.
    """
    
    def __init__(self):
        self.repository = TodoRepository()
    
    def list_todos(
        self,
        user: User,
        is_completed: Optional[bool] = None,
        priority: Optional[str] = None,
        category: Optional[UUID] = None,
        tags: Optional[List[UUID]] = None,
        due_before = None,
        due_after = None,
        search: Optional[str] = None,
        ordering: str = "-created_at",
    ):
        """List todos with filtering and ordering."""
        queryset = self.repository.get_user_todos(user)
        queryset = self.repository.filter_todos(
            queryset,
            is_completed=is_completed,
            priority=priority,
            category=category,
            tags=tags,
            due_before=due_before,
            due_after=due_after,
            search=search,
        )
        return self.repository.order_todos(queryset, ordering)
    
    def get_todo(self, todo_id: UUID, user: User) -> Todo:
        """Get a specific todo, raising NotFound if not found."""
        todo = self.repository.get_todo_by_id(todo_id, user)
        if not todo:
            raise NotFound(f"Todo with ID {todo_id} not found")
        return todo
    
    def create_todo(self, user: User, **data) -> Todo:
        """Create a new todo."""
        tag_ids = data.pop("tag_ids", [])
        
        todo = Todo.objects.create(user=user, **data)
        
        # Set tags if provided
        if tag_ids:
            tags = Tag.objects.filter(id__in=tag_ids, user=user)
            todo.tags.set(tags)
        
        return todo
    
    def update_todo(self, todo_id: UUID, user: User, **data) -> Todo:
        """Update an existing todo."""
        todo = self.get_todo(todo_id, user)
        tag_ids = data.pop("tag_ids", None)
        
        # Update fields
        for attr, value in data.items():
            setattr(todo, attr, value)
        
        todo.save()
        
        # Update tags if provided
        if tag_ids is not None:
            tags = Tag.objects.filter(id__in=tag_ids, user=user)
            todo.tags.set(tags)
        
        return todo
    
    def delete_todo(self, todo_id: UUID, user: User) -> None:
        """Delete a todo."""
        todo = self.get_todo(todo_id, user)
        todo.delete()
    
    def toggle_complete(self, todo_id: UUID, user: User) -> Todo:
        """Toggle todo completion status."""
        todo = self.get_todo(todo_id, user)
        todo.toggle_complete()
        return todo
    
    def bulk_delete(self, todo_ids: List[UUID], user: User) -> int:
        """Bulk delete todos."""
        return self.repository.bulk_delete(todo_ids, user)
    
    def bulk_complete(
        self, 
        todo_ids: List[UUID], 
        user: User, 
        is_completed: bool = True
    ) -> int:
        """Bulk mark todos as complete/incomplete."""
        return self.repository.bulk_complete(todo_ids, user, is_completed)
    
    def get_overdue_todos(self, user: User):
        """Get overdue todos for a user."""
        return self.repository.get_overdue_todos(user)
    
    def get_todos_due_today(self, user: User):
        """Get todos due today for a user."""
        return self.repository.get_todos_due_today(user)
    
    def get_todos_due_this_week(self, user: User):
        """Get todos due this week for a user."""
        return self.repository.get_todos_due_this_week(user)
    
    def get_statistics(self, user: User) -> Dict[str, Any]:
        """Get todo statistics for a user."""
        return self.repository.get_statistics(user)
    
    def validate_ownership(self, todo_id: UUID, user: User) -> bool:
        """Validate that a user owns a specific todo."""
        try:
            todo = Todo.objects.get(id=todo_id, user=user)
            return True
        except Todo.DoesNotExist:
            return False


class CategoryService:
    """
    Service for Category business logic.
    """
    
    def __init__(self):
        self.repository = CategoryRepository()
    
    def list_categories(self, user: User):
        """List all categories for a user."""
        return self.repository.get_user_categories(user)
    
    def get_category(self, category_id: UUID, user: User) -> Category:
        """Get a specific category."""
        category = self.repository.get_category_by_id(category_id, user)
        if not category:
            raise NotFound(f"Category with ID {category_id} not found")
        return category
    
    def create_category(self, user: User, **data) -> Category:
        """Create a new category."""
        return Category.objects.create(user=user, **data)
    
    def update_category(self, category_id: UUID, user: User, **data) -> Category:
        """Update an existing category."""
        category = self.get_category(category_id, user)
        
        for attr, value in data.items():
            setattr(category, attr, value)
        
        category.save()
        return category
    
    def delete_category(self, category_id: UUID, user: User) -> None:
        """Delete a category."""
        category = self.get_category(category_id, user)
        category.delete()


class TagService:
    """
    Service for Tag business logic.
    """
    
    def __init__(self):
        self.repository = TagRepository()
    
    def list_tags(self, user: User):
        """List all tags for a user."""
        return self.repository.get_user_tags(user)
    
    def get_tag(self, tag_id: UUID, user: User) -> Tag:
        """Get a specific tag."""
        tag = self.repository.get_tag_by_id(tag_id, user)
        if not tag:
            raise NotFound(f"Tag with ID {tag_id} not found")
        return tag
    
    def create_tag(self, user: User, **data) -> Tag:
        """Create a new tag."""
        return Tag.objects.create(user=user, **data)
    
    def update_tag(self, tag_id: UUID, user: User, **data) -> Tag:
        """Update an existing tag."""
        tag = self.get_tag(tag_id, user)
        
        for attr, value in data.items():
            setattr(tag, attr, value)
        
        tag.save()
        return tag
    
    def delete_tag(self, tag_id: UUID, user: User) -> None:
        """Delete a tag."""
        tag = self.get_tag(tag_id, user)
        tag.delete()
    
    def get_or_create_tag(self, name: str, user: User, color: str = "#6B7280") -> Tag:
        """Get or create a tag."""
        return self.repository.get_or_create_tag(name, user, color)


__all__ = [
    "TodoService",
    "CategoryService",
    "TagService",
]
