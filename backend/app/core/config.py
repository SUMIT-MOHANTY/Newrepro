import os
import sys

# Ensure backend root is on sys.path for backward compatibility
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from config import settings, Settings
except ImportError:
    from pydantic_settings import BaseSettings
    class Settings(BaseSettings):
        host: str = "0.0.0.0"
        port: int = 8000
    settings = Settings()

__all__ = ["settings", "Settings"]
