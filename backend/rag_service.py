"""
DSuite BRD Analyzer - Root Shim for RAG Service
Maintains backward compatibility for legacy imports (import rag_service).
"""
import sys
from app.services.ai.rag_service import *
from app.services.ai import rag_service as _mod

sys.modules["rag_service"] = _mod
