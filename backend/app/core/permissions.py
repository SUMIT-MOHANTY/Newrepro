"""
Object-level permissions for the Todo Application
Implements IsOwner permission class for enforcing user data isolation
"""
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to access it.
    Assumes the model instance has a `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Check if the object has a user attribute and matches the request user
        return hasattr(obj, 'user') and obj.user == request.user


class IsTodoOwner(IsOwner):
    """
    Permission class specifically for Todo objects.
    Ensures users can only access/modify their own todos.
    """
    pass


class IsCategoryOwner(IsOwner):
    """
    Permission class specifically for Category objects.
    Ensures users can only access/modify their own categories.
    """
    pass


class IsTagOwner(IsOwner):
    """
    Permission class specifically for Tag objects.
    Ensures users can only access/modify their own tags.
    """
    pass


__all__ = [
    "IsOwner",
    "IsTodoOwner",
    "IsCategoryOwner",
    "IsTagOwner",
]
