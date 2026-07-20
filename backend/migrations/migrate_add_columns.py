"""Migration script to add missing columns to the governance_responses table."""
from sqlalchemy import create_engine, text
from database import SQLALCHEMY_DATABASE_URL

def migrate():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

    with engine.connect() as conn:
        # Check if columns exist
        result = conn.execute(text("PRAGMA table_info(governance_responses)"))
        columns = [row[1] for row in result.fetchall()]

        print(f"Current columns in governance_responses: {columns}")

        # Add client_id column if it doesn't exist
        if 'client_id' not in columns:
            print("Adding client_id column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN client_id VARCHAR"))
            conn.commit()
            print("[OK] client_id column added")
        else:
            print("[OK] client_id column already exists")

        # Add client_secret column if it doesn't exist
        if 'client_secret' not in columns:
            print("Adding client_secret column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN client_secret VARCHAR"))
            conn.commit()
            print("[OK] client_secret column added")
        else:
            print("[OK] client_secret column already exists")

        # Add prerequisites_completed_at column if it doesn't exist
        if 'prerequisites_completed_at' not in columns:
            print("Adding prerequisites_completed_at column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN prerequisites_completed_at DATETIME"))
            conn.commit()
            print("[OK] prerequisites_completed_at column added")
        else:
            print("[OK] prerequisites_completed_at column already exists")

        # Add steps_data column if it doesn't exist (stores roadmap steps as JSON)
        if 'steps_data' not in columns:
            print("Adding steps_data column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN steps_data TEXT"))
            conn.commit()
            print("[OK] steps_data column added")
        else:
            print("[OK] steps_data column already exists")

        # Add azure_devops_client_id column if it doesn't exist
        if 'azure_devops_client_id' not in columns:
            print("Adding azure_devops_client_id column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN azure_devops_client_id VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_client_id column added")
        else:
            print("[OK] azure_devops_client_id column already exists")

        # Add azure_devops_client_secret column if it doesn't exist
        if 'azure_devops_client_secret' not in columns:
            print("Adding azure_devops_client_secret column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN azure_devops_client_secret VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_client_secret column added")
        else:
            print("[OK] azure_devops_client_secret column already exists")

        # Add azure_devops_organization column if it doesn't exist
        if 'azure_devops_organization' not in columns:
            print("Adding azure_devops_organization column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN azure_devops_organization VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_organization column added")
        else:
            print("[OK] azure_devops_organization column already exists")

        # Add azure_devops_project column if it doesn't exist
        if 'azure_devops_project' not in columns:
            print("Adding azure_devops_project column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN azure_devops_project VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_project column added")
        else:
            print("[OK] azure_devops_project column already exists")

        # Add azure_devops_tenant_id column if it doesn't exist
        if 'azure_devops_tenant_id' not in columns:
            print("Adding azure_devops_tenant_id column...")
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN azure_devops_tenant_id VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_tenant_id column added")
        else:
            print("[OK] azure_devops_tenant_id column already exists")

        # Table: agents
        result = conn.execute(text("PRAGMA table_info(agents)"))
        agent_columns = [row[1] for row in result.fetchall()]
        if 'project_token' not in agent_columns:
            print("Adding project_token column to agents...")
            conn.execute(text("ALTER TABLE agents ADD COLUMN project_token VARCHAR"))
            conn.commit()
            print("[OK] project_token column added to agents")

        # Table: agent_credentials
        result = conn.execute(text("PRAGMA table_info(agent_credentials)"))
        cred_columns = [row[1] for row in result.fetchall()]
        if 'project_token' not in cred_columns:
            print("Adding project_token column to agent_credentials...")
            conn.execute(text("ALTER TABLE agent_credentials ADD COLUMN project_token VARCHAR"))
            conn.commit()
            print("[OK] project_token column added to agent_credentials")

        # Table: organization_agent_mappings
        result = conn.execute(text("PRAGMA table_info(organization_agent_mappings)"))
        mapping_columns = [row[1] for row in result.fetchall()]
        if 'agent_kind' not in mapping_columns:
            print("Adding agent_kind column to organization_agent_mappings...")
            conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN agent_kind VARCHAR"))
            conn.commit()
            print("[OK] agent_kind column added to organization_agent_mappings")

        # Table: users
        result = conn.execute(text("PRAGMA table_info(users)"))
        user_columns = [row[1] for row in result.fetchall()]
        print(f"Current columns in users: {user_columns}")

        if 'last_login' not in user_columns:
            print("Adding last_login column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
            conn.commit()
            print("[OK] last_login column added to users")
        else:
            print("[OK] last_login column already exists in users")

        if 'first_name' not in user_columns:
            print("Adding first_name column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR"))
            conn.commit()
            print("[OK] first_name column added to users")

        if 'last_name' not in user_columns:
            print("Adding last_name column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR"))
            conn.commit()
            print("[OK] last_name column added to users")

        if 'organization_name' not in user_columns:
            print("Adding organization_name column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN organization_name VARCHAR"))
            conn.commit()
            print("[OK] organization_name column added to users")

        if 'is_org_admin' not in user_columns:
            print("Adding is_org_admin column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN is_org_admin BOOLEAN DEFAULT 0"))
            conn.commit()
            print("[OK] is_org_admin column added to users")

        if 'azure_devops_token' not in user_columns:
            print("Adding azure_devops_token column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_token VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_token column added to users")

        if 'azure_devops_username' not in user_columns:
            print("Adding azure_devops_username column to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_username VARCHAR"))
            conn.commit()
            print("[OK] azure_devops_username column added to users")

        # Table: password_resets
        print("Ensuring password_resets table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash VARCHAR NOT NULL,
                expires_at DATETIME NOT NULL,
                used_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_token_hash ON password_resets (token_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_user_id ON password_resets (user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_expires_at ON password_resets (expires_at)"))
        conn.commit()
        print("[OK] password_resets table ensured")

        # Table: governance_questions
        print("Ensuring governance_questions table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS governance_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dimension VARCHAR NOT NULL,
                question_text VARCHAR NOT NULL,
                "order" INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_governance_questions_dimension ON governance_questions (dimension)"))
        conn.commit()
        print("[OK] governance_questions table ensured")

        # Table: governance_question_options
        print("Ensuring governance_question_options table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS governance_question_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                label VARCHAR NOT NULL,
                score INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(question_id) REFERENCES governance_questions(id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_governance_question_options_question_id ON governance_question_options (question_id)"))
        conn.commit()
        print("[OK] governance_question_options table ensured")

        # Seed default governance questions if empty
        result = conn.execute(text("SELECT count(*) FROM governance_questions"))
        count = result.fetchone()[0]
        if count == 0:
            print("Seeding default governance questions...")
            try:
                import sys
                import os
                sys.path.append(os.getcwd())
                from governance_scoring import GOVERNANCE_QUESTIONS
                
                for q_data in GOVERNANCE_QUESTIONS:
                    res = conn.execute(text("""
                        INSERT INTO governance_questions (id, dimension, question_text, "order", is_active)
                        VALUES (:id, :dimension, :question_text, :order, :is_active)
                    """), {
                        "id": q_data["id"],
                        "dimension": q_data["dimension"],
                        "question_text": q_data["question"],
                        "order": q_data["id"],
                        "is_active": 1
                    })
                    q_id = q_data["id"]
                    
                    for opt_data in q_data["options"]:
                        conn.execute(text("""
                            INSERT INTO governance_question_options (question_id, label, score)
                            VALUES (:question_id, :label, :score)
                        """), {
                            "question_id": q_id,
                            "label": opt_data["label"],
                            "score": opt_data["score"]
                        })
                conn.commit()
                print("[OK] Governance questions seeded")
            except Exception as e:
                print(f"[ERROR] Failed to seed governance questions: {e}")
        else:
            print(f"[OK] Governance questions already exist (count: {count})")

        print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
