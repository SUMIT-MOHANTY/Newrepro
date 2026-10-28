"""
Todo Model Proxy
This module re-exports the Todo domain models from app.todos.models
for backward compatibility and import convenience.
"""
from app.todos.models import Todo, Category, Tag

__all__ = ["Todo", "Category", "Tag"]
