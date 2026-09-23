import importlib.util
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Ensure 'config' always resolves to the root backend/config.py, never to app/core/config.py
if "config" in sys.modules and hasattr(sys.modules["config"], "settings"):
    _root_config = sys.modules["config"]
else:
    config_path = os.path.join(backend_dir, "config.py")
    if os.path.isfile(config_path):
        spec = importlib.util.spec_from_file_location("config", config_path)
        _root_config = importlib.util.module_from_spec(spec)
        sys.modules["config"] = _root_config
        spec.loader.exec_module(_root_config)
    else:
        _root_config = None

if _root_config and hasattr(_root_config, "settings"):
    settings = _root_config.settings
    Settings = _root_config.Settings
else:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        host: str = "0.0.0.0"
        port: int = 8000

    settings = Settings()

__all__ = ["settings", "Settings"]
