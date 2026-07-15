"""
Script to reset project runtime states for testing agent execution and loop resumption.
Keeps the generated tasks and onboarded agents, but resets execution progress.
Usage: python reset_project_runtime.py <project_token>
"""
import sys
import os

# Add parent directory to path so database.py can be found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import SessionLocal

def reset_project(project_token: str):
    db = SessionLocal()
    try:
        print(f"🔄 Resetting execution state for project: {project_token}")
        
        # 1. Clear Project Runtime State (our new table)
        res = db.execute(text("""
            DELETE FROM project_runtime_states WHERE project_token = :token
        """), {"token": project_token})
        db.commit()
        print(f"✓ Cleared project_runtime_states ({res.rowcount} row(s) deleted)")

        # 2. Reset Bootstrap State
        res = db.execute(text("""
            DELETE FROM bootstrap_states WHERE project_token = :token
        """), {"token": project_token})
        db.commit()
        print(f"✓ Cleared bootstrap_states ({res.rowcount} row(s) deleted)")

        # 3. Clear Agent Messages/Blockers
        res = db.execute(text("""
            DELETE FROM agent_messages WHERE project_token = :token
        """), {"token": project_token})
        db.commit()
        print(f"✓ Cleared agent_messages log ({res.rowcount} row(s) deleted)")

        # 4. Optional: Reset local Task sync flag if needed to re-sync
        res = db.execute(text("""
            UPDATE tasks SET synced_to_nxdune = 0 WHERE project_token = :token
        """), {"token": project_token})
        db.commit()
        print(f"✓ Reset synced_to_nxdune flag on local tasks table ({res.rowcount} row(s) updated)")

        print("\n🎉 Project reset successfully! You can now test the agent execution and loop resumption from the beginning.")
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to reset project state: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reset_project_runtime.py <project_token>")
        
        # Find the latest project token to suggest
        db = SessionLocal()
        try:
            latest = db.execute(text("SELECT project_token, project_name FROM governance_responses ORDER BY submission_date DESC LIMIT 1")).first()
            if latest:
                print(f"\nSuggested command for your latest project ({latest.project_name}):")
                print(f"python reset_project_runtime.py {latest.project_token}")
        except Exception:
            pass
        finally:
            db.close()
            
        sys.exit(1)
        
    reset_project(sys.argv[1])
