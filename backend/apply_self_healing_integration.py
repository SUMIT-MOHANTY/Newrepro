"""
Automated Integration Script for Self-Healing System

This script applies all necessary changes to integrate:
1. Persistent bootstrap state
2. Agent communication hooks
3. Coordination monitor

Run: python backend/apply_self_healing_integration.py
"""
import os
import shutil
from datetime import datetime

def backup_file(filepath):
    """Create backup of file before modifying"""
    backup_path = f"{filepath}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backed up {filepath} to {backup_path}")
    return backup_path

def integrate_bootstrap_persistence():
    """Replace _bootstrap_pushed with persistent state"""
    filepath = "backend/agent_service.py"
    backup_file(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import at top
    if "from bootstrap_persistence import" not in content:
        # Find the imports section
        import_pos = content.find("import logging")
        if import_pos != -1:
            content = content[:import_pos] + "from bootstrap_persistence import is_bootstrap_pushed, set_bootstrap_success\n" + content[import_pos:]
            print("✅ Added bootstrap_persistence import")
    
    # Replace _bootstrap_pushed dict declaration
    content = content.replace(
        "_bootstrap_pushed: Dict[str, bool] = {}",
        "# _bootstrap_pushed replaced with persistent bootstrap_persistence module"
    )
    
    # Replace set operation
    content = content.replace(
        '_bootstrap_pushed[_project_key(project_token)] = True',
        'set_bootstrap_success(project_token)  # Persistent bootstrap state'
    )
    
    # Replace get operations
    content = content.replace(
        '_bootstrap_pushed.get(_proj_key, False)',
        'is_bootstrap_pushed(project_token)'
    )
    
    content = content.replace(
        '_bootstrap_pushed.get(_project_key(project_token), False)',
        'is_bootstrap_pushed(project_token)'
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Integrated persistent bootstrap state into agent_service.py")

def integrate_communication_hooks():
    """Add communication hooks to agent execution"""
    filepath = "backend/agent_service.py"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import
    if "from agent_communication_hooks import" not in content:
        import_pos = content.find("from bootstrap_persistence import")
        if import_pos != -1:
            end_line = content.find("\n", import_pos)
            content = content[:end_line+1] + "from agent_communication_hooks import broadcast_task_started, broadcast_task_completed, broadcast_task_failed, broadcast_bootstrap_waiting\n" + content[end_line+1:]
            print("✅ Added agent_communication_hooks import")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Integrated communication hooks into agent_service.py")
    print("⚠️  Manual step required: Add broadcast calls at task start/complete/fail points")
    print("   See INTEGRATION_STEPS.md for exact locations")

def integrate_coordination_monitor():
    """Add coordination monitor to LangGraph workflow"""
    filepath = "backend/langgraph_workflow.py"
    backup_file(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import
    if "from coordination_monitor import" not in content:
        import_pos = content.find("import logging")
        if import_pos != -1:
            content = content[:import_pos] + "from coordination_monitor import start_coordination_monitor, stop_coordination_monitor\n" + content[import_pos:]
            print("✅ Added coordination_monitor import to langgraph_workflow.py")
    
    # Add monitor start/stop in _run_parallel_agents
    # This is complex, so we'll just add a comment for manual integration
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Added coordination_monitor import to langgraph_workflow.py")
    print("⚠️  Manual step required: Start/stop monitor in _run_parallel_agents")
    print("   See INTEGRATION_STEPS.md for exact code")

def main():
    print("=" * 60)
    print("Self-Healing System Integration")
    print("=" * 60)
    print()
    
    print("Step 1: Integrating persistent bootstrap state...")
    integrate_bootstrap_persistence()
    print()
    
    print("Step 2: Integrating communication hooks...")
    integrate_communication_hooks()
    print()
    
    print("Step 3: Integrating coordination monitor...")
    integrate_coordination_monitor()
    print()
    
    print("=" * 60)
    print("Integration Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review INTEGRATION_STEPS.md for manual integration points")
    print("2. Add broadcast calls at task execution points")
    print("3. Add monitor start/stop in langgraph_workflow.py")
    print("4. Test bootstrap persistence")
    print("5. Test agent communication")
    print("6. Test coordination monitor")
    print()
    print("Backups created with .backup.YYYYMMDD_HHMMSS extension")

if __name__ == "__main__":
    main()
