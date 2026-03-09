# MASTER AGENT SYSTEM IMPROVEMENTS - ANALYSIS & PLAN

## 🎯 YOUR REQUIREMENTS SUMMARY

1. **Master Agent as Active Manager:**
   - Should assign tasks to agents (not just recommend)
   - Use API to assign tasks
   - Ensure all agents work (no idle when tasks available)

2. **Master Agent as Problem Solver:**
   - Detect when agents fail/get stuck
   - Analyze the issue
   - Decide what agent should do
   - Provide prompt/input to help agent continue

3. **Proper Coordination:**
   - Master Agent verifies structure (no issues)
   - All agents follow structure strictly (no duplication)
   - All agents work in sync
   - Git Manager syncs with Master Agent

4. **Integration & Deployment:**
   - Integration branch should have deploy-ready project
   - Git Manager coordinates with Master Agent
   - Everything works like humans would

---

## ❌ CURRENT SYSTEM ISSUES

### Issue 1: Master Agent Only Recommends (Doesn't Assign)
**Current Behavior:**
- Master Agent creates `recommended_assignments` list
- Agents pick tasks themselves via `_pick_next_task()`
- No enforcement of recommendations
- No API call to actually assign tasks

**Code Location:**
- `_build_master_recommended_assignments()` - only creates recommendations
- `_pick_next_task()` - agents self-select tasks
- No call to `task_service.assign_task()`

### Issue 2: No Failure Detection & Intervention
**Current Behavior:**
- Agents retry 3 times automatically
- If all retries fail, agent just stops
- Master Agent doesn't know about failures
- No Master Agent analysis of why agent failed
- No recovery prompts generated

**Code Location:**
- `run_agent()` - has retry logic but no Master Agent notification
- No failure callback to Master Agent
- No recovery prompt generation

### Issue 3: Agents Can Sit Idle
**Current Behavior:**
- `run_all_agents()` launches agents but doesn't monitor
- Agents can finish and sit idle
- No supervisor loop to redistribute work
- No check if agents are idle when tasks available

**Code Location:**
- `run_all_agents()` - launches agents but doesn't monitor continuously
- No supervisor/orchestrator loop

### Issue 4: No Structure Validation During Execution
**Current Behavior:**
- Master Agent creates structure once
- No continuous validation during development
- No check for duplication
- No enforcement that agents follow structure

**Code Location:**
- Master note created once
- No validation loop during agent execution

### Issue 5: Git Manager Not Synced
**Current Behavior:**
- Git Manager operates independently
- No coordination with Master Agent
- No check if integration branch is ready
- No coordination for merges

**Code Location:**
- Git Manager agent (`agent_03`) - no Master Agent coordination

---

## ✅ WHAT NEEDS TO BE DONE

### **PHASE 1: Master Agent as Active Task Assigner**

#### 1.1 Add Task Assignment Function
```python
async def _master_assign_task_to_agent(
    task_id: str,
    agent_id: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> bool:
    """Master Agent actively assigns task to agent via API."""
    # Use task_service.assign_task() API
    # Update task with assigned_agent
    # Log assignment in Master Agent
```

#### 1.2 Modify Master Agent to Assign Tasks
- After creating recommended assignments
- Actually call API to assign tasks
- Don't just recommend - ENFORCE assignments

#### 1.3 Update Agent Task Picking Logic
- Agents should check if they have assigned task first
- If assigned, use that task
- If not assigned, then pick next available

### **PHASE 2: Master Agent Failure Detection & Intervention**

#### 2.1 Add Failure Detection
```python
async def _master_detect_agent_failures(
    project_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Detect agents that failed or are stuck."""
    # Check agent status
    # Check if agent has been stuck for too long
    # Check if agent failed multiple times
    # Return list of failed agents with context
```

#### 2.2 Add Failure Analysis
```python
async def _master_analyze_failure(
    agent_id: str,
    task: Dict[str, Any],
    error: str,
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Master Agent analyzes why agent failed."""
    # Get agent output logs
    # Get task details
    # Get error details
    # Use AI to analyze root cause
    # Return analysis + recovery plan
```

#### 2.3 Add Recovery Prompt Generation
```python
async def _master_generate_recovery_prompt(
    agent_id: str,
    task: Dict[str, Any],
    failure_analysis: Dict[str, Any],
    project_token: Optional[str] = None,
) -> str:
    """Master Agent generates recovery prompt for stuck agent."""
    # Use AI to generate specific recovery instructions
    # Include context about what went wrong
    # Provide clear next steps
    # Return recovery prompt
```

#### 2.4 Add Failure Callback
- When agent fails after all retries
- Notify Master Agent
- Master Agent analyzes and provides recovery prompt
- Agent retries with Master Agent guidance

### **PHASE 3: Supervisor Loop - Ensure All Agents Work**

#### 3.1 Add Supervisor Loop
```python
async def _master_supervisor_loop(
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    check_interval: int = 30,  # seconds
) -> None:
    """Continuous loop to ensure all agents work."""
    while True:
        # 1. Get all agents
        # 2. Get all available tasks
        # 3. Find idle agents
        # 4. Assign tasks to idle agents
        # 5. Check for stuck/failed agents
        # 6. Intervene if needed
        # 7. Sleep and repeat
```

#### 3.2 Monitor Agent Status
- Track agent status continuously
- Detect idle agents
- Detect stuck agents (running too long)
- Detect failed agents

#### 3.3 Redistribute Work
- When agent finishes task
- Immediately assign next task
- When agent fails
- Reassign task to another agent

### **PHASE 4: Structure Validation & Duplication Prevention**

#### 4.1 Add Continuous Structure Validation
```python
async def _master_validate_structure(
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Master Agent validates structure continuously."""
    # Get current repo tree
    # Compare with canonical tree
    # Check for duplicates
    # Check for violations
    # Return validation results
```

#### 4.2 Add Duplication Detection
- Before agent creates file
- Check if file already exists
- Check if similar file exists
- Prevent duplicate creation

#### 4.3 Add Structure Enforcement
- Agents must check structure before creating files
- Master Agent validates all file creations
- Reject files that violate structure

### **PHASE 5: Git Manager Coordination**

#### 5.1 Add Master-Git Manager Sync
```python
async def _master_coordinate_git_manager(
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Master Agent coordinates with Git Manager."""
    # Check integration branch status
    # Verify all tasks completed
    # Coordinate merge timing
    # Ensure deploy-ready state
```

#### 5.2 Integration Branch Readiness Check
- Master Agent checks if all tasks done
- Verifies integration branch is ready
- Coordinates with Git Manager for merge
- Ensures deploy-ready state

---

## 📋 IMPLEMENTATION PRIORITY

### **HIGH PRIORITY (Do First):**
1. ✅ Master Agent active task assignment (Phase 1)
2. ✅ Supervisor loop to ensure all agents work (Phase 3)
3. ✅ Failure detection and intervention (Phase 2)

### **MEDIUM PRIORITY:**
4. ✅ Structure validation and duplication prevention (Phase 4)
5. ✅ Git Manager coordination (Phase 5)

---

## 🔧 TECHNICAL CHANGES NEEDED

### **File: `backend/agent_service.py`**

#### New Functions to Add:
1. `async def _master_assign_task_to_agent()` - Assign task via API
2. `async def _master_detect_agent_failures()` - Detect failures
3. `async def _master_analyze_failure()` - Analyze failures
4. `async def _master_generate_recovery_prompt()` - Generate recovery
5. `async def _master_supervisor_loop()` - Supervisor loop
6. `async def _master_validate_structure()` - Validate structure
7. `async def _master_coordinate_git_manager()` - Coordinate Git Manager

#### Functions to Modify:
1. `ensure_master_workspace_note()` - Add task assignment after recommendations
2. `_build_master_recommended_assignments()` - Actually assign, not just recommend
3. `run_agent()` - Add failure callback to Master Agent
4. `_pick_next_task()` - Check for assigned tasks first
5. `run_all_agents()` - Add supervisor loop

---

## 🎯 EXPECTED OUTCOMES

After implementation:

1. ✅ **Master Agent actively assigns tasks** - No idle agents when tasks available
2. ✅ **Master Agent intervenes on failures** - Agents get help when stuck
3. ✅ **All agents work continuously** - Supervisor ensures work distribution
4. ✅ **Structure strictly enforced** - No duplication, all follow canonical tree
5. ✅ **Git Manager synced** - Integration branch ready, coordinated merges
6. ✅ **Human-like coordination** - Agents work together like a team

---

## 📝 NEXT STEPS

1. Review this analysis
2. Approve the plan
3. Start implementing Phase 1 (Task Assignment)
4. Then Phase 3 (Supervisor Loop)
5. Then Phase 2 (Failure Intervention)
6. Then Phase 4 & 5 (Structure & Git Coordination)
