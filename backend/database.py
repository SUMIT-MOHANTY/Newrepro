"""
Backward-compatibility shim for backend/database.py.
Authoritative implementation resides in app.core.database.
"""
from app.core.database import (
    Base,
    engine,
    SessionLocal,
    get_db,
    SQLALCHEMY_DATABASE_URL,
    DEFAULT_DB_PATH,
)

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "SQLALCHEMY_DATABASE_URL",
    "DEFAULT_DB_PATH",
]
