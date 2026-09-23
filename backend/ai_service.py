"""
DSuite BRD Analyzer - Root Shim for AI Service
Maintains backward compatibility for legacy imports (import ai_service).
"""
import sys
from app.services.ai.ai_service import *
from app.services.ai import ai_service as _mod

sys.modules["ai_service"] = _mod
