 
"""
Migration: Add user progress tracking fields
Adds last_page_path and last_project_token to users table
"""
from sqlalchemy import text
from database import engine
 
def upgrade():
    """Add progress tracking columns to users table"""
    with engine.connect() as conn:
        # Add last_page_path column
        try:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN last_page_path VARCHAR
            """))
            conn.commit()
            print("✓ Added last_page_path column")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠ last_page_path column already exists")
            else:
                raise
       
        # Add last_project_token column
        try:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN last_project_token VARCHAR
            """))
            conn.commit()
            print("✓ Added last_project_token column")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠ last_project_token column already exists")
            else:
                raise
 
def downgrade():
    """Remove progress tracking columns from users table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users DROP COLUMN last_page_path"))
            conn.execute(text("ALTER TABLE users DROP COLUMN last_project_token"))
            conn.commit()
            print("✓ Removed progress tracking columns")
        except Exception as e:
            print(f"⚠ Error removing columns: {e}")
 
if __name__ == "__main__":
    print("Running migration: Add user progress tracking...")
    upgrade()
    print("Migration complete!")
