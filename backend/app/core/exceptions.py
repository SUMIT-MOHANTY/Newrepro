from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainException(Exception):
    """Base exception for all domain-level business errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(DomainException):
    """Raised when a requested resource/entity does not exist."""
    pass


class PermissionDeniedError(DomainException):
    """Raised when an action violates authorization / RBAC rules."""
    pass


class BusinessRuleViolationError(DomainException):
    """Raised when a domain validation or workflow invariant fails."""
    pass


class ConflictError(DomainException):
    """Raised when a resource already exists or violates uniqueness constraints."""
    pass


# Convenient aliases
NotFoundException = EntityNotFoundError
ForbiddenException = PermissionDeniedError
ValidationException = BusinessRuleViolationError


def register_exception_handlers(app: FastAPI) -> None:
    """Registers standard HTTP converters for domain exceptions."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "type": "EntityNotFound", "details": exc.details},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "type": "PermissionDenied", "details": exc.details},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "type": "Conflict", "details": exc.details},
        )

    @app.exception_handler(BusinessRuleViolationError)
    async def business_rule_handler(request: Request, exc: BusinessRuleViolationError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "type": "BusinessRuleViolation", "details": exc.details},
        )


__all__ = [
    "DomainException",
    "EntityNotFoundError",
    "PermissionDeniedError",
    "BusinessRuleViolationError",
    "ConflictError",
    "NotFoundException",
    "ForbiddenException",
    "ValidationException",
    "register_exception_handlers",
]
