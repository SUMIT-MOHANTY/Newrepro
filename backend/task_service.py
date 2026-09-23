"""
DSuite BRD Analyzer - Root Shim for Task Service
Maintains backward compatibility for legacy imports (import task_service).
"""
import sys
from app.services.agents.task_service import *
from app.services.agents import task_service as _mod

sys.modules["task_service"] = _mod
