"""
DSuite BRD Analyzer - Application Package
Structured following 8-Layer Clean Architecture.
"""

import os
import sys

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Compatibility paths for legacy direct module imports (e.g. llm_gateway)
_compat_paths = [
    os.path.join(_backend_dir, "app", "integrations", "llm"),
    os.path.join(_backend_dir, "app", "services", "agents"),
    os.path.join(_backend_dir, "app", "workers"),
    os.path.join(_backend_dir, "scripts"),
]

for _p in _compat_paths:
    if _p not in sys.path and os.path.isdir(_p):
        sys.path.append(_p)

# Root backend directory must always have highest precedence in sys.path
if _backend_dir in sys.path:
    sys.path.remove(_backend_dir)
sys.path.insert(0, _backend_dir)
