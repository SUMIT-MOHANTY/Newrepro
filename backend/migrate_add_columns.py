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

        print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
