"""
DSuite BRD Analyzer - Application Package
Structured following 8-Layer Clean Architecture.
"""

import os
import sys

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_subpackages = [
    _backend_dir,
    os.path.join(_backend_dir, "scripts"),
    os.path.join(_backend_dir, "app"),
    os.path.join(_backend_dir, "app", "core"),
    os.path.join(_backend_dir, "app", "models"),
    os.path.join(_backend_dir, "app", "schemas"),
    os.path.join(_backend_dir, "app", "repositories"),
    os.path.join(_backend_dir, "app", "services"),
    os.path.join(_backend_dir, "app", "services", "ai"),
    os.path.join(_backend_dir, "app", "services", "agents"),
    os.path.join(_backend_dir, "app", "workers"),
    os.path.join(_backend_dir, "app", "integrations"),
    os.path.join(_backend_dir, "app", "integrations", "vcs"),
    os.path.join(_backend_dir, "app", "integrations", "llm"),
    os.path.join(_backend_dir, "app", "routers"),
]

for _p in _subpackages:
    if _p not in sys.path and os.path.isdir(_p):
        sys.path.insert(0, _p)
