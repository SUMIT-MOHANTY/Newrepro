"""
Master Task Manager - The ONLY controller for all agent coordination
This is the single source of truth for task assignment and agent coordination
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import json

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

class MasterTaskManager:
    """
    The Master Agent that controls ALL other agents
    - Assigns tasks (no self-service)
    - Manages file locks
    - Coordinates sync points
    - Prevents conflicts
    """
    
    def __init__(self):
        self.task_queue: List[Dict[str, Any]] = []
        self.agent_assignments: Dict[str, Optional[Dict[str, Any]]] = {}  # agent_id -> current_task
        self.file_locks: Dict[str, str] = {}  # file_path -> agent_id
        self.agent_status: Dict[str, str] = {}  # agent_id -> status
        self.sync_points: Set[str] = set()  # agents waiting at sync points
        self.project_state: Dict[str, Any] = {}
        
    async def initialize_project(self, project_token: str, tasks: List[Dict[str, Any]], agents: List[str]):
        """Initialize project with tasks and available agents - SCALES TO 1000+ AGENTS"""
        logger.info(f"🎯 Master Task Manager initializing project {project_token}")
        logger.info(f"📊 Scale: {len(tasks)} tasks, {len(agents)} agents")
        
        # 🎯 SCALABLE TASK QUEUE with priorities and dependencies
        self.task_queue = self._prioritize_tasks(tasks)
        
        # 🎯 MASSIVE AGENT POOL MANAGEMENT
        # Initialize all agents as idle with performance tracking
        agent_performance = {}
        for agent_id in agents:
            self.agent_assignments[agent_id] = None
            self.agent_status[agent_id] = "idle"
            
            # Initialize performance tracking for load balancing
            agent_performance[agent_id] = {
                "tasks_completed": 0,
                "average_completion_time": 0,
                "success_rate": 100,
                "specialization_score": self._calculate_specialization_score(agent_id),
                "last_active": None
            }
            
        self.project_state[project_token] = {
            "total_tasks": len(tasks),
            "completed_tasks": 0,
            "active_agents": 0,
            "status": "initialized",
            "agent_performance": agent_performance,
            "max_parallel_tasks": min(len(agents), len(tasks), 20),  # Limit parallel execution
            "agent_pool_size": len(agents)
        }
        
        # 🎯 AGENT CATEGORIZATION for optimal task distribution
        agent_categories = self._categorize_agent_pool(agents)
        logger.info(f"📋 Agent categories: {agent_categories}")
        
        logger.info(f"✅ Project initialized: {len(tasks)} tasks, {len(agents)} agents")
        logger.info(f"🎯 Max parallel tasks: {self.project_state[project_token]['max_parallel_tasks']}")
        
    def _calculate_specialization_score(self, agent_id: str) -> float:
        """Calculate how specialized an agent is (higher = more specialized)"""
        capabilities = self._get_agent_capabilities(agent_id)
        primary_skills = len(capabilities.get("primary", []))
        secondary_skills = len(capabilities.get("secondary", []))
        
        # More specialized agents have fewer primary skills but high expertise
        if primary_skills == 1:
            return 10.0  # Highly specialized
        elif primary_skills == 2:
            return 7.0   # Moderately specialized  
        elif primary_skills >= 3:
            return 5.0   # Generalist
        else:
            return 3.0   # Unknown/fallback
    
    def _categorize_agent_pool(self, agents: List[str]) -> Dict[str, int]:
        """Categorize large agent pools for better management"""
        categories = {
            "frontend_specialists": 0,
            "backend_specialists": 0, 
            "fullstack_agents": 0,
            "devops_specialists": 0,
            "general_agents": 0
        }
        
        for agent_id in agents:
            capabilities = self._get_agent_capabilities(agent_id)
            primary = capabilities.get("primary", [])
            
            if "frontend" in primary and len(primary) == 1:
                categories["frontend_specialists"] += 1
            elif "backend" in primary and len(primary) == 1:
                categories["backend_specialists"] += 1
            elif "setup" in primary or "integration" in primary:
                categories["devops_specialists"] += 1
            elif len(primary) >= 3:
                categories["fullstack_agents"] += 1
            else:
                categories["general_agents"] += 1
                
        return categories
        
    def _prioritize_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Smart task prioritization based on dependencies and type"""
        
        # Categorize tasks by type and priority
        setup_tasks = []      # Database, config, initial setup
        backend_tasks = []    # API, services, business logic  
        frontend_tasks = []   # UI, components, pages
        integration_tasks = [] # Testing, deployment, final integration
        
        for task in tasks:
            task_type = self._classify_task_type(task)
            task["classified_type"] = task_type
            task["assigned_agent"] = None
            task["status"] = "pending"
            
            if task_type == "setup":
                setup_tasks.append(task)
            elif task_type == "backend":
                backend_tasks.append(task)
            elif task_type == "frontend":
                frontend_tasks.append(task)
            else:
                integration_tasks.append(task)
        
        # Return in dependency order: setup → backend → frontend → integration
        prioritized = setup_tasks + backend_tasks + frontend_tasks + integration_tasks
        
        # Add sequence numbers
        for i, task in enumerate(prioritized):
            task["sequence"] = i + 1
            
        return prioritized
    
    def _classify_task_type(self, task: Dict[str, Any]) -> str:
        """Classify task type for proper agent assignment"""
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        
        # Setup tasks (must be done first)
        if any(keyword in title + description for keyword in [
            "database", "config", "setup", "initialize", "install", "environment"
        ]):
            return "setup"
            
        # Backend tasks
        elif any(keyword in title + description for keyword in [
            "api", "endpoint", "service", "model", "database", "auth", "backend"
        ]):
            return "backend"
            
        # Frontend tasks  
        elif any(keyword in title + description for keyword in [
            "ui", "component", "page", "frontend", "react", "vue", "angular", "css", "html"
        ]):
            return "frontend"
            
        # Integration tasks (done last)
        else:
            return "integration"
    
    async def assign_next_task(self, project_token: str) -> Dict[str, Any]:
        """Master assigns the next task to the best available agent - HANDLES 100+ AGENTS"""
        
        # 🎯 SCALABLE AGENT MANAGEMENT
        # Find idle agents (can handle thousands)
        idle_agents = [agent_id for agent_id, status in self.agent_status.items() 
                      if status == "idle"]
        
        if not idle_agents:
            return {"status": "no_idle_agents", "message": f"All {len(self.agent_status)} agents are busy"}
            
        # 🎯 INTELLIGENT TASK QUEUE MANAGEMENT
        # Find next available task with dependency checking
        available_tasks = []
        for task in self.task_queue:
            if task["status"] == "pending" and self._task_dependencies_met(task):
                available_tasks.append(task)
        
        if not available_tasks:
            # Check if we're waiting for sync points
            sync_waiting_agents = [agent_id for agent_id, status in self.agent_status.items() 
                                 if status == "sync_waiting"]
            if sync_waiting_agents:
                return {
                    "status": "sync_waiting", 
                    "message": f"{len(sync_waiting_agents)} agents waiting for sync point"
                }
            
            return {"status": "no_available_tasks", "message": "No tasks ready for assignment"}
        
        # 🎯 PARALLEL TASK ASSIGNMENT
        # For large agent pools, assign multiple tasks simultaneously
        assignments_made = []
        max_parallel_assignments = min(len(idle_agents), len(available_tasks), 10)  # Max 10 at once
        
        for i in range(max_parallel_assignments):
            if i >= len(available_tasks) or i >= len(idle_agents):
                break
                
            task = available_tasks[i]
            
            # Get suitable agents for this specific task
            suitable_agents = [agent for agent in idle_agents 
                             if self._agent_can_handle_task(agent, task)]
            
            if not suitable_agents:
                suitable_agents = idle_agents  # Fallback to any idle agent
            
            # Choose best agent for this task
            best_agent = self._choose_best_agent_for_task(task, suitable_agents)
            
            if best_agent and best_agent in idle_agents:
                # Assign task
                self.agent_assignments[best_agent] = task
                self.agent_status[best_agent] = "assigned"
                task["assigned_agent"] = best_agent
                task["status"] = "assigned"
                task["assigned_at"] = datetime.now().isoformat()
                
                # Remove from idle list for next iteration
                idle_agents.remove(best_agent)
                
                assignments_made.append({
                    "agent_id": best_agent,
                    "task_title": task["title"],
                    "task_type": task.get("classified_type", "general")
                })
                
                logger.info(f"📋 Task '{task['title']}' assigned to {best_agent}")
        
        if assignments_made:
            return {
                "status": "assigned",
                "assignments": assignments_made,
                "message": f"Assigned {len(assignments_made)} tasks to agents",
                "total_idle_agents": len(self.agent_status) - len([s for s in self.agent_status.values() if s != "idle"]),
                "total_agents": len(self.agent_status)
            }
        else:
            return {
                "status": "assignment_failed",
                "message": "No suitable agent-task matches found"
            }
    
    def _agent_can_handle_task(self, agent_id: str, task: Dict[str, Any]) -> bool:
        """Check if agent can handle specific task type"""
        task_type = task.get("classified_type", "backend")
        capabilities = self._get_agent_capabilities(agent_id)
        
        return (task_type in capabilities.get("primary", []) or 
                task_type in capabilities.get("secondary", []))
    
    def _task_dependencies_met(self, task: Dict[str, Any]) -> bool:
        """Check if task dependencies are satisfied"""
        # For now, simple sequence-based dependency
        task_sequence = task.get("sequence", 0)
        
        # Check if all previous tasks are completed
        for prev_task in self.task_queue:
            prev_sequence = prev_task.get("sequence", 0)
            if prev_sequence < task_sequence and prev_task["status"] != "completed":
                return False
                
        return True
    
    def _choose_best_agent_for_task(self, task: Dict[str, Any], idle_agents: List[str]) -> str:
        """Choose the best agent for a specific task using dynamic scoring based on specialization,
        skills tags, and dedicated/shared boundary enforcement."""
        if not idle_agents:
            return None

        # 1. Classify the task into Testing or Development
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        task_text = f"{title} {description}"
        task_project_token = task.get("project_token") or task.get("projectToken")

        test_keywords = ["test", "qa", "assert", "check", "verify", "mock", "unittest", "pytest"]
        is_testing = any(keyword in task_text for keyword in test_keywords)
        classified_spec = "Testing" if is_testing else "Development"

        logger.info(f"Classified task '{task.get('title')}' as specialization: {classified_spec}")

        # 2. Open DB session to fetch specialization, skills_tags, AND agent kind/project binding
        agent_db_map = {}
        session = SessionLocal()
        try:
            db_agents = session.query(models.Agent).filter(models.Agent.id.in_(idle_agents)).all()
            for a in db_agents:
                agent_db_map[a.id] = {
                    "specialization": a.specialization,
                    "skills_tags": a.skills_tags,
                    "agent_kind": "shared",       # default
                    "assigned_project_token": None # default
                }

            # Fetch org mapping to get agent_kind and project_token binding
            mappings = session.query(
                models.OrganizationAgentMapping.agent_id,
                models.OrganizationAgentMapping.agent_kind,
                models.OrganizationAgentMapping.project_token,
            ).filter(
                models.OrganizationAgentMapping.agent_id.in_(idle_agents)
            ).all()
            for m in mappings:
                if m.agent_id in agent_db_map:
                    agent_db_map[m.agent_id]["agent_kind"] = m.agent_kind or "shared"
                    agent_db_map[m.agent_id]["assigned_project_token"] = m.project_token

        except Exception as e:
            logger.error(f"Error fetching agent data from DB: {e}")
        finally:
            session.close()

        # 3. Score idle agents dynamically
        agent_scores = {}
        for agent_id in idle_agents:
            agent_data = agent_db_map.get(agent_id, {})
            score = 0

            # ── Dedicated/Shared boundary enforcement ───────────────────────────
            agent_kind = agent_data.get("agent_kind", "shared")
            assigned_project = agent_data.get("assigned_project_token")

            if agent_kind == "dedicated":
                if task_project_token and assigned_project and assigned_project != task_project_token:
                    # Dedicated agent is bound to a DIFFERENT project — SKIP
                    logger.info(
                        f"Agent {agent_id} is DEDICATED to project {assigned_project}, "
                        f"skipping for task on project {task_project_token}"
                    )
                    continue
                elif assigned_project and assigned_project == task_project_token:
                    # Perfect dedicated match — strong bonus
                    score += 300
                    logger.info(f"Agent {agent_id} is DEDICATED to this project — +300 bonus")
            else:
                # Shared agent — eligible for any project, moderate bonus
                score += 50
                logger.info(f"Agent {agent_id} is SHARED — +50 bonus")

            # ── Specialization match ────────────────────────────────────────────
            spec = agent_data.get("specialization")
            if spec and spec.strip().lower() == classified_spec.lower():
                score += 500

            # ── Skills tags keyword match ───────────────────────────────────────
            skills_tags = agent_data.get("skills_tags")
            tags = []
            if isinstance(skills_tags, list):
                tags = skills_tags
            elif isinstance(skills_tags, str):
                try:
                    import json as _json
                    tags = _json.loads(skills_tags)
                except Exception:
                    pass

            if tags:
                for tag in tags:
                    if tag and str(tag).lower() in task_text:
                        score += 50

            agent_scores[agent_id] = score
            logger.info(f"Agent {agent_id} final score: {score} (kind: {agent_kind}, spec: {spec}, tags: {tags})")

        if not agent_scores:
            # All agents were dedicated to other projects — fall back to any idle agent
            logger.warning("No eligible agents after kind boundary enforcement — falling back to any idle agent")
            return idle_agents[0] if idle_agents else None

        # 4. Select highest-scoring agent; break ties with least-busy
        max_score = max(agent_scores.values())
        highest_scoring_agents = [aid for aid, s in agent_scores.items() if s == max_score]

        if len(highest_scoring_agents) == 1:
            best_agent = highest_scoring_agents[0]
            logger.info(f"Selected highest scoring agent: {best_agent} with score {max_score}")
            return best_agent
        else:
            best_agent = self._select_least_busy_agent(highest_scoring_agents)
            logger.info(f"Tie on max score {max_score} between {highest_scoring_agents}. Selected least-busy: {best_agent}")
            return best_agent
    
    def _get_agent_capabilities(self, agent_id: str) -> Dict[str, List[str]]:
        """Get agent capabilities - FLEXIBLE ASSIGNMENT SYSTEM"""
        
        # 🎯 PRIORITY ORDER FOR AGENT TYPE DETECTION:
        # 1. Explicit configuration (highest priority)
        # 2. Master Agent decision (AI-based)
        # 3. Agent name pattern recognition (automatic)
        # 4. Default fallback (democratic)
        
        # 1️⃣ CHECK EXPLICIT CONFIGURATION FIRST
        explicit_config = self._get_explicit_agent_config(agent_id)
        if explicit_config:
            return explicit_config
        
        # 2️⃣ CHECK MASTER AGENT DECISION
        master_decision = self._get_master_agent_decision(agent_id)
        if master_decision:
            return master_decision
        
        # 3️⃣ AUTOMATIC PATTERN RECOGNITION (fallback)
        return self._get_agent_capabilities_by_pattern(agent_id)
    
    def _get_explicit_agent_config(self, agent_id: str) -> Optional[Dict[str, List[str]]]:
        """Get explicitly configured agent capabilities"""
        
        # Check if there's explicit configuration for this agent
        # This could come from database, config file, or API
        explicit_configs = getattr(self, 'explicit_agent_configs', {})
        
        if agent_id in explicit_configs:
            config = explicit_configs[agent_id]
            return {
                "primary": config.get("primary_skills", []),
                "secondary": config.get("secondary_skills", []),
                "assigned_by": "explicit_config"
            }
        
        return None
    
    def _get_master_agent_decision(self, agent_id: str) -> Optional[Dict[str, List[str]]]:
        """Get Master Agent's AI decision on agent capabilities"""
        
        # Check if Master Agent has made a decision about this agent
        master_decisions = getattr(self, 'master_agent_decisions', {})
        
        if agent_id in master_decisions:
            decision = master_decisions[agent_id]
            return {
                "primary": decision.get("primary_skills", []),
                "secondary": decision.get("secondary_skills", []),
                "assigned_by": "master_agent",
                "reasoning": decision.get("reasoning", "")
            }
        
        return None
    
    def _get_agent_capabilities_by_pattern(self, agent_id: str) -> Dict[str, List[str]]:
        """Get agent capabilities based on ID pattern - AUTOMATIC DETECTION"""
        
        agent_lower = agent_id.lower()
        
        # Frontend specialists (any agent with 'frontend', 'ui', 'react', etc.)
        if any(keyword in agent_lower for keyword in ['frontend', 'ui', 'react', 'vue', 'angular', 'web']):
            return {
                "primary": ["frontend"],
                "secondary": ["integration", "setup"],
                "assigned_by": "pattern_recognition"
            }
        
        # Backend specialists  
        elif any(keyword in agent_lower for keyword in ['backend', 'api', 'server', 'db', 'database']):
            return {
                "primary": ["backend"],
                "secondary": ["setup", "integration"],
                "assigned_by": "pattern_recognition"
            }
        
        # DevOps/Setup specialists
        elif any(keyword in agent_lower for keyword in ['devops', 'deploy', 'infra', 'setup', 'config']):
            return {
                "primary": ["setup", "integration"],
                "secondary": ["backend"],
                "assigned_by": "pattern_recognition"
            }
        
        # Full-stack agents (can do everything)
        elif any(keyword in agent_lower for keyword in ['fullstack', 'full', 'stack', 'general']):
            return {
                "primary": ["backend", "frontend", "setup", "integration"],
                "secondary": [],
                "assigned_by": "pattern_recognition"
            }
        
        # Numeric agent pattern recognition
        elif agent_id.startswith('agent_') and agent_id[6:].isdigit():
            agent_num = int(agent_id[6:])
            if 1 <= agent_num <= 10:
                return {
                    "primary": ["backend", "frontend", "setup", "integration"],
                    "secondary": [],
                    "assigned_by": "numeric_pattern"
                }
            elif 11 <= agent_num <= 20:
                return {
                    "primary": ["backend"],
                    "secondary": ["setup", "integration"],
                    "assigned_by": "numeric_pattern"
                }
            elif 21 <= agent_num <= 30:
                return {
                    "primary": ["frontend"],
                    "secondary": ["integration"],
                    "assigned_by": "numeric_pattern"
                }
            else:
                return {
                    "primary": ["backend", "frontend"],
                    "secondary": ["setup", "integration"],
                    "assigned_by": "numeric_pattern"
                }
        
        # Default: All agents can do all work (democratic fallback)
        else:
            return {
                "primary": ["backend", "frontend", "setup", "integration"],
                "secondary": [],
                "assigned_by": "default_fallback"
            }
    
    def set_explicit_agent_config(self, agent_id: str, primary_skills: List[str], secondary_skills: List[str] = None):
        """Explicitly configure an agent's capabilities - MANUAL OVERRIDE"""
        
        if not hasattr(self, 'explicit_agent_configs'):
            self.explicit_agent_configs = {}
        
        self.explicit_agent_configs[agent_id] = {
            "primary_skills": primary_skills,
            "secondary_skills": secondary_skills or [],
            "configured_at": datetime.now().isoformat()
        }
        
        logger.info(f"🎯 Explicit config set for {agent_id}: primary={primary_skills}, secondary={secondary_skills}")
    
    async def master_agent_assign_capabilities(self, agent_id: str, project_context: str = "") -> Dict[str, Any]:
        """Master Agent uses AI to decide agent capabilities - INTELLIGENT ASSIGNMENT"""
        
        # This would call your AI service to make intelligent decisions
        # For now, implementing a smart heuristic system
        
        if not hasattr(self, 'master_agent_decisions'):
            self.master_agent_decisions = {}
        
        # Analyze project context and agent performance to make decision
        decision = await self._ai_analyze_agent_capabilities(agent_id, project_context)
        
        self.master_agent_decisions[agent_id] = {
            "primary_skills": decision["primary"],
            "secondary_skills": decision["secondary"],
            "reasoning": decision["reasoning"],
            "confidence": decision["confidence"],
            "decided_at": datetime.now().isoformat()
        }
        
        logger.info(f"🤖 Master Agent assigned {agent_id}: {decision['primary']} (confidence: {decision['confidence']}%)")
        
        return decision
    
    async def _ai_analyze_agent_capabilities(self, agent_id: str, project_context: str) -> Dict[str, Any]:
        """AI analysis of agent capabilities based on project needs"""
        
        # Get project task distribution
        task_types = {}
        for task in self.task_queue:
            task_type = task.get("classified_type", "backend")
            task_types[task_type] = task_types.get(task_type, 0) + 1
        
        # Get current agent distribution
        current_specialists = {"frontend": 0, "backend": 0, "setup": 0, "integration": 0}
        for aid in self.agent_status.keys():
            if aid != agent_id:  # Don't count the agent we're analyzing
                caps = self._get_agent_capabilities_by_pattern(aid)
                for skill in caps.get("primary", []):
                    if skill in current_specialists:
                        current_specialists[skill] += 1
        
        # AI Decision Logic
        total_tasks = sum(task_types.values())
        if total_tasks == 0:
            # No tasks yet, make balanced decision
            least_covered = min(current_specialists.keys(), key=lambda x: current_specialists[x])
            return {
                "primary": [least_covered],
                "secondary": ["integration"],
                "reasoning": f"Balanced assignment - {least_covered} specialists needed",
                "confidence": 85
            }
        
        # Find the most needed skill based on task distribution vs current specialists
        skill_need_ratio = {}
        for skill, task_count in task_types.items():
            if skill in current_specialists:
                current_count = current_specialists[skill]
                need_ratio = task_count / max(current_count, 1)  # Avoid division by zero
                skill_need_ratio[skill] = need_ratio
        
        if skill_need_ratio:
            most_needed = max(skill_need_ratio.keys(), key=lambda x: skill_need_ratio[x])
            confidence = min(95, 60 + (skill_need_ratio[most_needed] * 10))
            
            return {
                "primary": [most_needed],
                "secondary": ["integration"] if most_needed != "integration" else ["backend"],
                "reasoning": f"High demand for {most_needed} specialists (ratio: {skill_need_ratio[most_needed]:.1f})",
                "confidence": int(confidence)
            }
        
        # Fallback to full-stack
        return {
            "primary": ["backend", "frontend"],
            "secondary": ["setup", "integration"],
            "reasoning": "Full-stack assignment for flexibility",
            "confidence": 70
        }
    
    def _select_least_busy_agent(self, candidate_agents: List[str]) -> str:
        """Select the least busy agent from candidates - LOAD BALANCING"""
        if not candidate_agents:
            return None
            
        # 🎯 LOAD BALANCING: Track agent workload
        agent_workload = {}
        
        for agent_id in candidate_agents:
            # Count current tasks assigned to this agent
            current_tasks = sum(1 for task in self.task_queue 
                              if task.get("assigned_agent") == agent_id and 
                                 task.get("status") in ["assigned", "in_progress"])
            
            # Count completed tasks (experience factor)
            completed_tasks = sum(1 for task in self.task_queue 
                                if task.get("assigned_agent") == agent_id and 
                                   task.get("status") == "completed")
            
            # Calculate workload score (lower is better)
            # Current tasks heavily weighted, completed tasks slightly reduce score (experience)
            workload_score = (current_tasks * 10) - (completed_tasks * 0.1)
            agent_workload[agent_id] = workload_score
        
        # Return agent with lowest workload
        return min(agent_workload.keys(), key=lambda x: agent_workload[x])
    
    async def request_file_lock(self, agent_id: str, file_path: str) -> Dict[str, Any]:
        """Agent requests exclusive access to a file"""
        
        # Check if file is already locked
        if file_path in self.file_locks:
            current_owner = self.file_locks[file_path]
            if current_owner != agent_id:
                logger.warning(f"🔒 File {file_path} locked by {current_owner}, denying {agent_id}")
                return {
                    "granted": False,
                    "message": f"File locked by {current_owner}",
                    "current_owner": current_owner
                }
        
        # Grant lock
        self.file_locks[file_path] = agent_id
        logger.info(f"🔓 File lock granted: {file_path} → {agent_id}")
        
        return {
            "granted": True,
            "message": f"File lock granted for {file_path}",
            "owner": agent_id
        }
    
    async def release_file_lock(self, agent_id: str, file_path: str) -> Dict[str, Any]:
        """Agent releases file lock"""
        
        if file_path not in self.file_locks:
            return {"status": "not_locked", "message": "File was not locked"}
            
        if self.file_locks[file_path] != agent_id:
            return {
                "status": "not_owner", 
                "message": f"File locked by {self.file_locks[file_path]}, not {agent_id}"
            }
        
        del self.file_locks[file_path]
        logger.info(f"🔓 File lock released: {file_path} by {agent_id}")
        
        return {"status": "released", "message": f"File lock released for {file_path}"}
    
    async def report_task_progress(self, agent_id: str, progress: Dict[str, Any]) -> Dict[str, Any]:
        """Agent reports progress on current task"""
        
        current_task = self.agent_assignments.get(agent_id)
        if not current_task:
            return {"status": "no_task", "message": "Agent has no assigned task"}
        
        # Update task progress
        current_task["progress"] = progress.get("progress", 0)
        current_task["status"] = progress.get("status", "in_progress")
        current_task["last_update"] = datetime.now().isoformat()
        
        # Update agent status
        self.agent_status[agent_id] = progress.get("status", "working")
        
        logger.info(f"📊 Progress update from {agent_id}: {progress.get('progress', 0)}%")
        
        return {"status": "updated", "message": "Progress recorded"}
    
    async def complete_task(self, agent_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Agent completes their assigned task"""
        
        current_task = self.agent_assignments.get(agent_id)
        if not current_task:
            return {"status": "no_task", "message": "Agent has no assigned task"}
        
        # Mark task as completed
        current_task["status"] = "completed"
        current_task["completed_at"] = datetime.now().isoformat()
        current_task["result"] = result
        
        # Free up the agent
        self.agent_assignments[agent_id] = None
        self.agent_status[agent_id] = "idle"
        
        # Release any file locks held by this agent
        files_to_release = [file_path for file_path, owner in self.file_locks.items() 
                           if owner == agent_id]
        for file_path in files_to_release:
            del self.file_locks[file_path]
        
        logger.info(f"✅ Task completed by {agent_id}: {current_task['title']}")
        
        # Check if we need a sync point
        await self._check_sync_point_needed()
        
        return {
            "status": "completed",
            "message": f"Task completed by {agent_id}",
            "next_assignment": await self._try_assign_next_task(agent_id)
        }
    
    async def _check_sync_point_needed(self) -> bool:
        """Check if we need to pause all agents for synchronization"""
        
        completed_tasks = [task for task in self.task_queue if task["status"] == "completed"]
        total_tasks = len(self.task_queue)
        
        # Sync points at 25%, 50%, 75% completion
        completion_percentage = len(completed_tasks) / total_tasks * 100
        
        sync_thresholds = [25, 50, 75]
        for threshold in sync_thresholds:
            if (completion_percentage >= threshold and 
                f"sync_{threshold}" not in self.sync_points):
                
                await self._initiate_sync_point(f"sync_{threshold}")
                return True
                
        return False
    
    async def _initiate_sync_point(self, sync_name: str):
        """Pause all agents for synchronization"""
        
        logger.info(f"🔄 Initiating sync point: {sync_name}")
        
        # Mark sync point as active
        self.sync_points.add(sync_name)
        
        # Pause all working agents
        for agent_id, status in self.agent_status.items():
            if status in ["working", "assigned"]:
                self.agent_status[agent_id] = "sync_waiting"
        
        # TODO: Trigger git merge, code review, integration tests
        # For now, just log and resume after a delay
        await asyncio.sleep(2)  # Simulate sync operations
        
        # Resume all agents
        for agent_id, status in self.agent_status.items():
            if status == "sync_waiting":
                self.agent_status[agent_id] = "idle"
        
        logger.info(f"✅ Sync point completed: {sync_name}")
    
    async def _try_assign_next_task(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Try to immediately assign next task to newly idle agent"""
        
        assignment = await self.assign_next_task("current_project")  # TODO: pass proper project_token
        
        if assignment["status"] == "assigned" and assignment["agent_id"] == agent_id:
            return assignment["task"]
            
        return None
    
    def get_coordination_status(self, project_token: str) -> Dict[str, Any]:
        """Get current coordination status for dashboard"""
        
        completed_tasks = [task for task in self.task_queue if task["status"] == "completed"]
        in_progress_tasks = [task for task in self.task_queue if task["status"] in ["assigned", "in_progress"]]
        pending_tasks = [task for task in self.task_queue if task["status"] == "pending"]
        
        return {
            "project_token": project_token,
            "total_tasks": len(self.task_queue),
            "completed_tasks": len(completed_tasks),
            "in_progress_tasks": len(in_progress_tasks),
            "pending_tasks": len(pending_tasks),
            "completion_percentage": len(completed_tasks) / len(self.task_queue) * 100 if self.task_queue else 0,
            "agents": {
                agent_id: {
                    "status": status,
                    "current_task": self.agent_assignments.get(agent_id, {}).get("title") if self.agent_assignments.get(agent_id) else None
                }
                for agent_id, status in self.agent_status.items()
            },
            "file_locks": self.file_locks,
            "active_sync_points": list(self.sync_points)
        }
    
    def get_agent_pool_analytics(self, project_token: str) -> Dict[str, Any]:
        """Get analytics for large agent pools - PERFORMANCE MONITORING"""
        
        if project_token not in self.project_state:
            return {"error": "Project not found"}
            
        project_data = self.project_state[project_token]
        agent_performance = project_data.get("agent_performance", {})
        
        # 🎯 AGENT POOL ANALYTICS
        analytics = {
            "pool_size": len(self.agent_status),
            "active_agents": len([s for s in self.agent_status.values() if s != "idle"]),
            "idle_agents": len([s for s in self.agent_status.values() if s == "idle"]),
            "utilization_rate": 0,
            "top_performers": [],
            "bottlenecks": [],
            "specialization_distribution": {},
            "load_balance_score": 0
        }
        
        if analytics["pool_size"] > 0:
            analytics["utilization_rate"] = (analytics["active_agents"] / analytics["pool_size"]) * 100
        
        # Top performing agents
        sorted_agents = sorted(
            agent_performance.items(),
            key=lambda x: (x[1].get("tasks_completed", 0), x[1].get("success_rate", 0)),
            reverse=True
        )
        analytics["top_performers"] = [
            {
                "agent_id": agent_id,
                "tasks_completed": data.get("tasks_completed", 0),
                "success_rate": data.get("success_rate", 100)
            }
            for agent_id, data in sorted_agents[:5]
        ]
        
        # Identify bottlenecks (agents with low performance)
        analytics["bottlenecks"] = [
            {
                "agent_id": agent_id,
                "tasks_completed": data.get("tasks_completed", 0),
                "success_rate": data.get("success_rate", 100)
            }
            for agent_id, data in sorted_agents[-3:]
            if data.get("success_rate", 100) < 80 or data.get("tasks_completed", 0) == 0
        ]
        
        # Specialization distribution
        for agent_id in self.agent_status.keys():
            capabilities = self._get_agent_capabilities(agent_id)
            for skill in capabilities.get("primary", []):
                analytics["specialization_distribution"][skill] = analytics["specialization_distribution"].get(skill, 0) + 1
        
        # Load balance score (0-100, higher is better)
        if analytics["pool_size"] > 1:
            task_counts = [data.get("tasks_completed", 0) for data in agent_performance.values()]
            if task_counts:
                avg_tasks = sum(task_counts) / len(task_counts)
                variance = sum((x - avg_tasks) ** 2 for x in task_counts) / len(task_counts)
                # Convert variance to a 0-100 score (lower variance = higher score)
                analytics["load_balance_score"] = max(0, 100 - (variance * 10))
        
        return analytics
    
    def optimize_agent_assignments(self, project_token: str) -> Dict[str, Any]:
        """Optimize task assignments for large agent pools"""
        
        analytics = self.get_agent_pool_analytics(project_token)
        
        optimizations = {
            "recommendations": [],
            "auto_applied": [],
            "pool_health": "good"
        }
        
        # Check utilization rate
        if analytics["utilization_rate"] < 50:
            optimizations["recommendations"].append(
                f"Low utilization ({analytics['utilization_rate']:.1f}%). Consider reducing agent pool size or increasing task parallelism."
            )
            optimizations["pool_health"] = "underutilized"
        elif analytics["utilization_rate"] > 90:
            optimizations["recommendations"].append(
                f"High utilization ({analytics['utilization_rate']:.1f}%). Consider adding more agents to prevent bottlenecks."
            )
            optimizations["pool_health"] = "overloaded"
        
        # Check load balance
        if analytics["load_balance_score"] < 70:
            optimizations["recommendations"].append(
                f"Poor load balancing (score: {analytics['load_balance_score']:.1f}). Some agents are overworked while others are idle."
            )
        
        # Check for bottlenecks
        if analytics["bottlenecks"]:
            optimizations["recommendations"].append(
                f"Found {len(analytics['bottlenecks'])} underperforming agents. Consider retraining or reassigning."
            )
        
        return optimizations

# 🎯 GLOBAL INSTANCE - Handles unlimited agents
master_task_manager = MasterTaskManager()