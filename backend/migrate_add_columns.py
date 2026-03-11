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

        print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
