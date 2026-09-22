import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import (
    Base,
    DEFAULT_DB_PATH,
    SQLALCHEMY_DATABASE_URL,
    SessionLocal,
    engine,
    get_db,
)

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "SQLALCHEMY_DATABASE_URL",
    "DEFAULT_DB_PATH",
]
