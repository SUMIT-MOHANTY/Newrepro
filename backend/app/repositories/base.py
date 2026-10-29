"""
Base Repository for Django ORM
Provides standardized CRUD operations using Django ORM.
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from django.db import models
from django.db.models import QuerySet

ModelType = TypeVar("ModelType", bound=models.Model)


class BaseRepository(Generic[ModelType]):
    """
    Generic Repository pattern providing standardized CRUD operations.
    Keeps database interaction abstracted from business logic.
    Uses Django ORM instead of SQLAlchemy.
    """

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        try:
            return self.model.objects.get(pk=id)
        except self.model.DoesNotExist:
            return None

    def list(
        self, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Fetch multiple records with pagination."""
        return list(self.model.objects.all()[skip:skip + limit])

    def count(self) -> int:
        """Count total rows in the table."""
        return self.model.objects.count()

    def create(self, *, obj_in: Union[Dict[str, Any], Any]) -> ModelType:
        """Insert a new entity record."""
        if isinstance(obj_in, dict):
            create_data = obj_in
        else:
            # Handle Django model instances or other objects
            create_data = obj_in.__dict__ if hasattr(obj_in, '__dict__') else obj_in
        
        # Remove any internal Django fields
        create_data = {k: v for k, v in create_data.items() if not k.startswith('_')}
        
        db_obj = self.model.objects.create(**create_data)
        return db_obj

    def update(
        self,
        *,
        db_obj: ModelType,
        obj_in: Union[Dict[str, Any], Any],
    ) -> ModelType:
        """Update fields of an existing entity record."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.__dict__ if hasattr(obj_in, '__dict__') else obj_in
        
        # Remove internal fields
        update_data = {k: v for k, v in update_data.items() if not k.startswith('_')}
        
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        db_obj.save()
        return db_obj

    def remove(self, *, id: Any) -> Optional[ModelType]:
        """Delete a record by primary key."""
        obj = self.get(id=id)
        if obj:
            obj.delete()
        return obj

    def filter(self, **kwargs) -> QuerySet[ModelType]:
        """Filter records by given criteria."""
        return self.model.objects.filter(**kwargs)

    def get_by_user(self, user_id: Any) -> QuerySet[ModelType]:
        """Get all records belonging to a specific user."""
        return self.model.objects.filter(user_id=user_id)


__all__ = ["BaseRepository", "ModelType"]
