import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import models

Agent = getattr(models, "Agent", None)
AgentNote = getattr(models, "AgentNote", None)
AgentMessage = getattr(models, "AgentMessage", None)
AgentTaskOwnership = getattr(models, "AgentTaskOwnership", None)
AgentExecutionCheckpoint = getattr(models, "AgentExecutionCheckpoint", None)
ProjectRuntimeState = getattr(models, "ProjectRuntimeState", None)
Task = getattr(models, "Task", None)
AgentCredential = getattr(models, "AgentCredential", None)
ChatMessage = getattr(models, "ChatMessage", None)
ProjectCanonicalState = getattr(models, "ProjectCanonicalState", None)
OrganizationAgentMapping = getattr(models, "OrganizationAgentMapping", None)
OrganizationAgentQuota = getattr(models, "OrganizationAgentQuota", None)
ProjectAgentRequest = getattr(models, "ProjectAgentRequest", None)
CapacityIncreaseRequest = getattr(models, "CapacityIncreaseRequest", None)
AIUsageLog = getattr(models, "AIUsageLog", None)

__all__ = [
    "Agent",
    "AgentNote",
    "AgentMessage",
    "AgentTaskOwnership",
    "AgentExecutionCheckpoint",
    "ProjectRuntimeState",
    "Task",
    "AgentCredential",
    "ChatMessage",
    "ProjectCanonicalState",
    "OrganizationAgentMapping",
    "OrganizationAgentQuota",
    "ProjectAgentRequest",
    "CapacityIncreaseRequest",
    "AIUsageLog",
]
