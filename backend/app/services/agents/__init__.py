"""DSuite BRD Analyzer - Agents Service Package.

Exports the global agent_service singleton instance and AgentService class.
"""
from app.services.agents.agent_service import agent_service, AgentService, AVAILABLE_AGENT_TOOLS

__all__ = ["agent_service", "AgentService", "AVAILABLE_AGENT_TOOLS"]
