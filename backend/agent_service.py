"""Shim redirecting legacy imports to clean AgentService."""
import sys
from app.services.agents.agent_service import *
from app.services.agents import agent_service as _mod

sys.modules["agent_service"] = _mod
