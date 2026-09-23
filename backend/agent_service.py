"""
DSuite BRD Analyzer - Root Shim for Agent Service
Maintains backward compatibility for legacy imports (import agent_service).
"""
import sys
from app.services.agents.agent_service import *
from app.services.agents import agent_service as _mod

sys.modules["agent_service"] = _mod
