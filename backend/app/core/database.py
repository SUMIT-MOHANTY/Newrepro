import importlib.util
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Ensure 'database' always resolves to the root backend/database.py, never to app/core/database.py
if "database" in sys.modules and hasattr(sys.modules["database"], "Base"):
    _root_db = sys.modules["database"]
else:
    db_path = os.path.join(backend_dir, "database.py")
    spec = importlib.util.spec_from_file_location("database", db_path)
    _root_db = importlib.util.module_from_spec(spec)
    sys.modules["database"] = _root_db
    spec.loader.exec_module(_root_db)

Base = _root_db.Base
engine = _root_db.engine
SessionLocal = _root_db.SessionLocal
get_db = _root_db.get_db
SQLALCHEMY_DATABASE_URL = _root_db.SQLALCHEMY_DATABASE_URL
DEFAULT_DB_PATH = _root_db.DEFAULT_DB_PATH

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "SQLALCHEMY_DATABASE_URL",
    "DEFAULT_DB_PATH",
]
