"""
Backward-compatibility shim for backend/config.py.
Authoritative implementation resides in app.core.config.
"""
from app.core.config import Settings, get_settings, settings

__all__ = ["Settings", "get_settings", "settings"]
