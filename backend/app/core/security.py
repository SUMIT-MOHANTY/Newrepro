import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from auth import (
    create_access_token,
    get_password_hash,
    oauth2_scheme,
    pwd_context,
    verify_password,
    verify_token,
)

__all__ = [
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "verify_token",
    "pwd_context",
    "oauth2_scheme",
]
