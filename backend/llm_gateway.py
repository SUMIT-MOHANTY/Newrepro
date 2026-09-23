"""
DSuite BRD Analyzer - Root Shim for LLM Gateway
Maintains backward compatibility for legacy imports (import llm_gateway).
"""
import sys
from app.integrations.llm.llm_gateway import *
from app.integrations.llm import llm_gateway as _mod

sys.modules["llm_gateway"] = _mod
