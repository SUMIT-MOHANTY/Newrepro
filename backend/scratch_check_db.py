import sqlite3

def check_db():
    conn = sqlite3.connect("sql_app.db")
    cursor = conn.cursor()
    
    print("--- AGENTS ---")
    cursor.execute("SELECT id, name, type, project_token, specialization, skills_summary FROM agents")
    for r in cursor.fetchall():
        print(f"ID: {r[0]}, Name: {r[1]}, Type: {r[2]}, ProjToken: {r[3]}, Spec: {r[4]}, Summary: {r[5]}")
        
    print("\n--- MAPPINGS ---")
    cursor.execute("SELECT agent_id, organization_name, is_default, project_token, agent_kind, agent_sub_type FROM organization_agent_mappings")
    for r in cursor.fetchall():
        print(f"AgentID: {r[0]}, Org: {r[1]}, Default: {r[2]}, ProjToken: {r[3]}, Kind: {r[4]}, SubType: {r[5]}")
        
    conn.close()

if __name__ == "__main__":
    check_db()
