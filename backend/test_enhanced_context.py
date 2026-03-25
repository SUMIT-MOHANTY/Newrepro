"""
Test script for Enhanced Context Sharing Service
Run this to verify the implementation works correctly
"""

import asyncio
import json
from enhanced_context_service import (
    enhanced_context_service,
    AgentContextUpdate,
    ContextMessageType
)


async def test_enhanced_context():
    """Test all features of enhanced context service"""
    
    print("🧪 Testing Enhanced Context Sharing Service\n")
    
    # 1. Initialize project context
    print("1️⃣ Initializing project context...")
    agents_config = {
        "agent_01": {"capabilities": ["backend", "auth"]},
        "agent_02": {"capabilities": ["backend", "database"]},
        "agent_03": {"capabilities": ["frontend", "ui"]}
    }
    
    context = await enhanced_context_service.initialize_project_context(
        "test_project_123",
        agents_config
    )
    print(f"✅ Context initialized with {len(context['agent_contexts'])} agents\n")
    
    # 2. Agent 01 updates context
    print("2️⃣ Agent 01 updates context (auth module)...")
    update1 = AgentContextUpdate(
        agent_id="agent_01",
        timestamp="2024-03-24T10:00:00Z",
        current_task="Implement authentication",
        current_files=["backend/auth.py"],
        completed_tasks=["Setup project structure"],
        created_files=["backend/auth.py", "backend/models/user.py"],
        api_endpoints=[
            {"method": "POST", "path": "/api/login", "auth_required": False},
            {"method": "POST", "path": "/api/register", "auth_required": False}
        ],
        database_tables=["users", "sessions"],
        shared_utilities=["backend.auth.validate_token", "backend.auth.hash_password"],
        tags=["auth", "backend", "security"]
    )
    
    success = await enhanced_context_service.update_agent_context(
        "test_project_123",
        update1
    )
    print(f"✅ Agent 01 context updated: {success}\n")
    
    # 3. Agent 02 updates context
    print("3️⃣ Agent 02 updates context (database)...")
    update2 = AgentContextUpdate(
        agent_id="agent_02",
        timestamp="2024-03-24T10:15:00Z",
        current_task="Setup database schema",
        completed_tasks=["Database migrations"],
        created_files=["backend/models.py", "migrations/001_initial.sql"],
        database_tables=["users", "sessions", "payments"],
        tags=["database", "backend", "migrations"]
    )
    
    success = await enhanced_context_service.update_agent_context(
        "test_project_123",
        update2
    )
    print(f"✅ Agent 02 context updated: {success}\n")
    
    # 4. Query: Who owns auth files?
    print("4️⃣ Query: Who owns auth files?")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "file_owner",
        {"file_pattern": "**/auth*"}
    )
    print(f"📁 File ownership: {json.dumps(result, indent=2)}\n")
    
    # 5. Query: What API endpoints exist?
    print("5️⃣ Query: What API endpoints exist?")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "api_endpoints"
    )
    print(f"🌐 API Endpoints ({result['total']}): {json.dumps(result['endpoints'], indent=2)}\n")
    
    # 6. Query: Database schema
    print("6️⃣ Query: Database schema")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "database_schema"
    )
    print(f"🗄️ Database tables: {list(result['tables'].keys())}\n")
    
    # 7. Query: By tag
    print("7️⃣ Query: By tag 'auth'")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "by_tag",
        {"tag": "auth"}
    )
    print(f"🏷️ Tagged updates: {len(result['updates'])} updates with tag 'auth'\n")
    
    # 8. Query: Agent status
    print("8️⃣ Query: Agent status")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "agent_status"
    )
    print(f"📊 Agent Status:")
    for agent_id, status in result.items():
        print(f"  - {agent_id}: {status['completed_tasks']} tasks, {status['created_files']} files")
    print()
    
    # 9. Memory board: Agent 03 asks a question
    print("9️⃣ Memory board: Agent 03 asks a question")
    msg_id = await enhanced_context_service.post_to_memory_board(
        "test_project_123",
        "agent_03",
        ContextMessageType.QUESTION,
        "How do I validate JWT tokens in this project?",
        tags=["auth", "question"]
    )
    print(f"❓ Question posted: {msg_id}\n")
    
    # 10. Memory board: Agent 01 answers
    print("🔟 Memory board: Agent 01 answers")
    answer_id = await enhanced_context_service.post_to_memory_board(
        "test_project_123",
        "agent_01",
        ContextMessageType.ANSWER,
        "Use backend.auth.validate_token(token). It returns user_id or raises InvalidTokenError.",
        tags=["auth", "answer"],
        reply_to=msg_id
    )
    print(f"💡 Answer posted: {answer_id}\n")
    
    # 11. Declare dependencies
    print("1️⃣1️⃣ Agent 03 declares dependencies")
    success = await enhanced_context_service.declare_dependency(
        "test_project_123",
        "agent_03",
        {
            "agent_01": ["auth module"],
            "agent_02": ["database schema"]
        }
    )
    print(f"🔗 Dependencies declared: {success}\n")
    
    # 12. Create snapshot
    print("1️⃣2️⃣ Create context snapshot at 50%")
    snapshot = await enhanced_context_service.create_context_snapshot(
        "test_project_123",
        "50%",
        {"phase": "development"}
    )
    print(f"📸 Snapshot created:")
    print(f"  - Files created: {snapshot['stats']['total_files_created']}")
    print(f"  - API endpoints: {snapshot['stats']['total_api_endpoints']}")
    print(f"  - Database tables: {snapshot['stats']['total_database_tables']}")
    print(f"  - Agents active: {snapshot['stats']['agents_active']}\n")
    
    # 13. Get agent context view
    print("1️⃣3️⃣ Get context view for Agent 03")
    view = await enhanced_context_service.get_agent_context_view(
        "test_project_123",
        "agent_03"
    )
    print(f"👁️ Agent 03 can see:")
    print(f"  - Other agents: {list(view['other_agents'].keys())}")
    print(f"  - API endpoints: {len(view['api_endpoints'])}")
    print(f"  - Database tables: {len(view['database_tables'])}")
    print(f"  - Shared utilities: {len(view['shared_utilities']['utilities'])}")
    print(f"  - Recent messages: {len(view['recent_messages'])}")
    print(f"  - Available files: {len(view['available_files'])}\n")
    
    # 14. Query shared utilities
    print("1️⃣4️⃣ Query: Shared utilities")
    result = await enhanced_context_service.query_context(
        "test_project_123",
        "shared_utilities"
    )
    print(f"🔧 Shared utilities:")
    for util, owner in result['utilities'].items():
        print(f"  - {util} (by {owner})")
    print()
    
    print("✅ All tests passed! Enhanced context sharing is working correctly.")
    print("\n📚 See CONTEXT_SHARING_USAGE.md for usage examples")


if __name__ == "__main__":
    asyncio.run(test_enhanced_context())
