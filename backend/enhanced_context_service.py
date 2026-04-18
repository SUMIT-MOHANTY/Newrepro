"""
Enhanced Context Sharing Service for Multi-Agent Coordination

Provides structured context sharing with semantic tagging, querying,
snapshots, and dependency tracking for better agent collaboration.
"""

import asyncio
import logging
import fnmatch
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ContextMessageType(Enum):
    """Types of context messages agents can post"""
    ANNOUNCEMENT = "announcement"
    QUESTION = "question"
    ANSWER = "answer"
    WARNING = "warning"
    COMPLETION = "completion"
    BLOCKER = "blocker"


@dataclass
class AgentContextUpdate:
    """Standardized context format for agent updates"""
    
    # Agent identification
    agent_id: str
    timestamp: str
    
    # Current work
    current_task: Optional[str] = None
    current_files: List[str] = field(default_factory=list)
    status: str = "working"
    
    # Completed work
    completed_tasks: List[str] = field(default_factory=list)
    created_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    
    # Technical artifacts
    api_endpoints: List[Dict[str, Any]] = field(default_factory=list)
    database_tables: List[str] = field(default_factory=list)
    environment_vars: List[str] = field(default_factory=list)
    dependencies_added: List[str] = field(default_factory=list)
    config_changes: List[Dict[str, Any]] = field(default_factory=list)
    
    # Shared knowledge
    shared_utilities: List[str] = field(default_factory=list)  # ["module.py::function_name"]
    integration_points: List[Dict[str, Any]] = field(default_factory=list)
    patterns_used: List[str] = field(default_factory=list)
    
    # Coordination info
    blocked_on: Optional[str] = None
    needs_review: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Semantic tags
    tags: List[str] = field(default_factory=list)


class EnhancedContextService:
    """Enhanced context sharing service with semantic tagging and querying"""
    
    def __init__(self):
        self.project_contexts: Dict[str, Dict[str, Any]] = {}
        self.context_locks = {}
        
    async def initialize_project_context(
        self,
        project_token: str,
        agents_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Initialize enhanced context for a project"""
        
        context = {
            "project_token": project_token,
            "initialized_at": datetime.utcnow().isoformat(),
            
            # Agent-specific contexts
            "agent_contexts": {
                agent_id: {
                    "agent_id": agent_id,
                    "last_updated": None,
                    "current_task": None,
                    "current_files": [],
                    "completed_tasks": [],
                    "created_files": [],
                    "modified_files": [],
                    "api_endpoints": [],
                    "database_tables": [],
                    "shared_utilities": [],
                    "tags": []
                }
                for agent_id in agents_config.keys()
            },
            
            # Semantic index (tag -> list of context updates)
            "context_index": {},
            
            # File ownership tracking
            "file_ownership": {},  # file_path -> agent_id
            
            # API endpoint registry
            "api_registry": [],  # [{method, path, agent, handler}]
            
            # Database schema tracking
            "database_schema": {
                "tables": {},  # table_name -> {agent, columns, created_at}
                "migrations": []
            },
            
            # Dependency graph
            "dependencies": {
                "agent_dependencies": {},  # agent_id -> [depends_on_agent_ids]
                "task_dependencies": {},   # task_id -> [depends_on_task_ids]
                "resolved": []
            },
            
            # Memory board (agent communication)
            "memory_board": [],
            
            # Context snapshots at sync points
            "snapshots": [],
            
            # Integration points
            "integration_points": [],
            
            # Shared patterns and conventions
            "patterns": {
                "coding_standards": [],
                "naming_conventions": [],
                "architecture_patterns": []
            }
        }
        
        self.project_contexts[project_token] = context
        logger.info(f"✅ Enhanced context initialized for project {project_token}")
        return context
    
    async def update_agent_context(
        self,
        project_token: str,
        context_update: AgentContextUpdate
    ) -> bool:
        """Update agent context with structured data"""
        
        if project_token not in self.project_contexts:
            logger.warning(f"Project {project_token} not initialized")
            return False
        
        context = self.project_contexts[project_token]
        agent_id = context_update.agent_id
        
        if agent_id not in context["agent_contexts"]:
            logger.warning(f"Agent {agent_id} not found in project {project_token}")
            return False
        
        # Update agent's context
        agent_ctx = context["agent_contexts"][agent_id]
        agent_ctx.update({
            "last_updated": context_update.timestamp,
            "current_task": context_update.current_task,
            "current_files": context_update.current_files,
            "status": context_update.status,
            "completed_tasks": list(set(agent_ctx.get("completed_tasks", []) + context_update.completed_tasks)),
            "created_files": list(set(agent_ctx.get("created_files", []) + context_update.created_files)),
            "modified_files": list(set(agent_ctx.get("modified_files", []) + context_update.modified_files)),
            "api_endpoints": agent_ctx.get("api_endpoints", []) + context_update.api_endpoints,
            "database_tables": list(set(agent_ctx.get("database_tables", []) + context_update.database_tables)),
            "shared_utilities": list(set(agent_ctx.get("shared_utilities", []) + context_update.shared_utilities)),
            "tags": list(set(agent_ctx.get("tags", []) + context_update.tags))
        })
        
        # Update file ownership
        for file_path in context_update.created_files:
            context["file_ownership"][file_path] = agent_id
        
        # Update API registry
        for endpoint in context_update.api_endpoints:
            context["api_registry"].append({
                **endpoint,
                "agent": agent_id,
                "registered_at": context_update.timestamp
            })
        
        # Update database schema
        for table in context_update.database_tables:
            if table not in context["database_schema"]["tables"]:
                context["database_schema"]["tables"][table] = {
                    "agent": agent_id,
                    "created_at": context_update.timestamp
                }
        
        # Index by semantic tags
        for tag in context_update.tags:
            if tag not in context["context_index"]:
                context["context_index"][tag] = []
            context["context_index"][tag].append({
                "agent_id": agent_id,
                "timestamp": context_update.timestamp,
                "update": context_update.__dict__
            })
        
        # Check dependency resolution
        await self._check_dependency_resolution(project_token, agent_id, context_update)
        
        logger.info(f"📝 Context updated for {agent_id} in {project_token} with tags: {context_update.tags}")
        return True
    
    async def query_context(
        self,
        project_token: str,
        query_type: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query shared context with various query types"""
        
        if project_token not in self.project_contexts:
            return {"error": "Project not found"}
        
        context = self.project_contexts[project_token]
        filters = filters or {}
        
        if query_type == "file_owner":
            # Find who created/owns specific files
            pattern = filters.get("file_pattern", "*")
            return {
                agent_id: [
                    f for f in ctx.get("created_files", [])
                    if fnmatch.fnmatch(f, pattern)
                ]
                for agent_id, ctx in context["agent_contexts"].items()
                if any(fnmatch.fnmatch(f, pattern) for f in ctx.get("created_files", []))
            }
        
        elif query_type == "api_endpoints":
            # Get all registered API endpoints
            return {
                "endpoints": context["api_registry"],
                "total": len(context["api_registry"])
            }
        
        elif query_type == "database_schema":
            # Get database schema information
            return context["database_schema"]
        
        elif query_type == "by_tag":
            # Query by semantic tag
            tag = filters.get("tag")
            return {
                "tag": tag,
                "updates": context["context_index"].get(tag, [])
            }
        
        elif query_type == "agent_status":
            # Get status of all agents
            return {
                agent_id: {
                    "status": ctx.get("status"),
                    "current_task": ctx.get("current_task"),
                    "completed_tasks": len(ctx.get("completed_tasks", [])),
                    "created_files": len(ctx.get("created_files", []))
                }
                for agent_id, ctx in context["agent_contexts"].items()
            }
        
        elif query_type == "module_status":
            # Check if anyone is working on a specific module
            module = filters.get("module", "")
            working_agents = []
            for agent_id, ctx in context["agent_contexts"].items():
                current_task = ctx.get("current_task", "")
                if module.lower() in current_task.lower():
                    working_agents.append({
                        "agent_id": agent_id,
                        "task": current_task,
                        "status": ctx.get("status")
                    })
            return {
                "module": module,
                "agents_working": working_agents,
                "status": "in_progress" if working_agents else "available"
            }
        
        elif query_type == "shared_utilities":
            # Get all shared utilities
            utilities = {}
            for agent_id, ctx in context["agent_contexts"].items():
                for util in ctx.get("shared_utilities", []):
                    utilities[util] = agent_id
            return {"utilities": utilities}
        
        elif query_type == "integration_points":
            # Get integration points between modules
            return {"integration_points": context["integration_points"]}
        
        elif query_type == "dependencies":
            # Get dependency information
            agent_id = filters.get("agent_id")
            if agent_id:
                return {
                    "agent_id": agent_id,
                    "depends_on": context["dependencies"]["agent_dependencies"].get(agent_id, []),
                    "depended_by": [
                        aid for aid, deps in context["dependencies"]["agent_dependencies"].items()
                        if agent_id in deps
                    ]
                }
            return context["dependencies"]
        
        return {"error": "Unknown query type"}
    
    async def post_to_memory_board(
        self,
        project_token: str,
        agent_id: str,
        message_type: ContextMessageType,
        content: str,
        tags: Optional[List[str]] = None,
        reply_to: Optional[str] = None
    ) -> str:
        """Post message to shared memory board"""
        
        if project_token not in self.project_contexts:
            return None
        
        context = self.project_contexts[project_token]
        
        message_id = f"msg_{len(context['memory_board']) + 1}"
        message = {
            "id": message_id,
            "agent_id": agent_id,
            "type": message_type.value,
            "content": content,
            "tags": tags or [],
            "reply_to": reply_to,
            "timestamp": datetime.utcnow().isoformat(),
            "replies": []
        }
        
        # If this is a reply, add to parent's replies
        if reply_to:
            for msg in context["memory_board"]:
                if msg["id"] == reply_to:
                    msg["replies"].append(message_id)
                    break
        
        context["memory_board"].append(message)
        
        # Emit appropriate emoji based on message type
        emoji_map = {
            ContextMessageType.ANNOUNCEMENT: "📢",
            ContextMessageType.QUESTION: "❓",
            ContextMessageType.ANSWER: "💡",
            ContextMessageType.WARNING: "⚠️",
            ContextMessageType.COMPLETION: "✅",
            ContextMessageType.BLOCKER: "🚫"
        }
        emoji = emoji_map.get(message_type, "💬")
        
        logger.info(f"{emoji} Memory Board [{agent_id}]: {content[:100]}")
        return message_id
    
    async def declare_dependency(
        self,
        project_token: str,
        agent_id: str,
        depends_on: Dict[str, List[str]]
    ) -> bool:
        """Declare dependencies on other agents' work"""
        
        if project_token not in self.project_contexts:
            return False
        
        context = self.project_contexts[project_token]
        
        # Store agent dependencies
        context["dependencies"]["agent_dependencies"][agent_id] = []
        
        for dep_agent_id, requirements in depends_on.items():
            context["dependencies"]["agent_dependencies"][agent_id].append({
                "agent": dep_agent_id,
                "requirements": requirements,
                "resolved": False
            })
        
        logger.info(f"🔗 Dependencies declared for {agent_id}: {list(depends_on.keys())}")
        return True
    
    async def create_context_snapshot(
        self,
        project_token: str,
        sync_point: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create context snapshot at sync point"""
        
        if project_token not in self.project_contexts:
            return {"error": "Project not found"}
        
        context = self.project_contexts[project_token]
        
        snapshot = {
            "sync_point": sync_point,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            
            # Agent contexts at this point
            "agent_contexts": {
                agent_id: {
                    "completed_tasks": ctx.get("completed_tasks", []),
                    "created_files": ctx.get("created_files", []),
                    "api_endpoints": ctx.get("api_endpoints", []),
                    "database_tables": ctx.get("database_tables", []),
                    "status": ctx.get("status")
                }
                for agent_id, ctx in context["agent_contexts"].items()
            },
            
            # Project-wide state
            "file_ownership": context["file_ownership"].copy(),
            "api_registry": context["api_registry"].copy(),
            "database_schema": context["database_schema"].copy(),
            "integration_points": context["integration_points"].copy(),
            
            # Statistics
            "stats": {
                "total_files_created": len(context["file_ownership"]),
                "total_api_endpoints": len(context["api_registry"]),
                "total_database_tables": len(context["database_schema"]["tables"]),
                "agents_active": sum(
                    1 for ctx in context["agent_contexts"].values()
                    if ctx.get("status") not in ["idle", "completed"]
                )
            }
        }
        
        context["snapshots"].append(snapshot)
        logger.info(f"📸 Context snapshot created at {sync_point} for {project_token}")
        return snapshot
    
    async def get_agent_context_view(
        self,
        project_token: str,
        agent_id: str
    ) -> Dict[str, Any]:
        """Get context view for specific agent"""
        
        if project_token not in self.project_contexts:
            return {"error": "Project not found"}
        
        context = self.project_contexts[project_token]
        
        if agent_id not in context["agent_contexts"]:
            return {"error": "Agent not found"}
        
        # Build comprehensive view for this agent
        my_context = context["agent_contexts"][agent_id]
        
        return {
            "agent_id": agent_id,
            "my_context": my_context,
            
            # What others are doing
            "other_agents": {
                aid: {
                    "status": ctx.get("status"),
                    "current_task": ctx.get("current_task"),
                    "current_files": ctx.get("current_files", []),
                    "completed_tasks_count": len(ctx.get("completed_tasks", []))
                }
                for aid, ctx in context["agent_contexts"].items()
                if aid != agent_id
            },
            
            # Shared resources
            "api_endpoints": context["api_registry"],
            "database_tables": list(context["database_schema"]["tables"].keys()),
            "shared_utilities": await self.query_context(project_token, "shared_utilities"),
            
            # My dependencies
            "my_dependencies": context["dependencies"]["agent_dependencies"].get(agent_id, []),
            
            # Recent memory board messages
            "recent_messages": context["memory_board"][-20:],
            
            # Files I can use
            "available_files": {
                path: owner
                for path, owner in context["file_ownership"].items()
                if owner != agent_id
            }
        }
    
    async def _check_dependency_resolution(
        self,
        project_token: str,
        agent_id: str,
        context_update: AgentContextUpdate
    ):
        """Check if this update resolves any dependencies"""
        
        context = self.project_contexts[project_token]
        dependencies = context["dependencies"]["agent_dependencies"]
        
        # Check all agents waiting on this agent
        for waiting_agent_id, deps in dependencies.items():
            if waiting_agent_id == agent_id:
                continue
            
            for dep in deps:
                if isinstance(dep, dict) and dep.get("agent") == agent_id:
                    # Check if requirements are met
                    requirements = dep.get("requirements", [])
                    completed = context_update.completed_tasks
                    
                    if any(req in completed for req in requirements):
                        dep["resolved"] = True
                        context["dependencies"]["resolved"].append({
                            "waiting_agent": waiting_agent_id,
                            "resolved_by": agent_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        logger.info(f"✅ Dependency resolved: {waiting_agent_id} ← {agent_id}")


# Global instance
enhanced_context_service = EnhancedContextService()


# Helper functions for easy integration

async def initialize_enhanced_context(
    project_token: str,
    agents_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Initialize enhanced context for project"""
    return await enhanced_context_service.initialize_project_context(
        project_token,
        agents_config
    )


async def update_agent_context(
    project_token: str,
    agent_id: str,
    **kwargs
) -> bool:
    """Update agent context with keyword arguments"""
    context_update = AgentContextUpdate(
        agent_id=agent_id,
        timestamp=datetime.utcnow().isoformat(),
        **kwargs
    )
    return await enhanced_context_service.update_agent_context(
        project_token,
        context_update
    )


async def query_agent_context(
    project_token: str,
    query_type: str,
    **filters
) -> Dict[str, Any]:
    """Query context with filters"""
    return await enhanced_context_service.query_context(
        project_token,
        query_type,
        filters
    )
