"""
Migration: Add claude.md and skills.md file storage
Adds claude_md_files and skills_md_files JSON columns to governance_responses table
"""
from sqlalchemy import text
from database import engine
 
 
def upgrade():
    """Add claude.md and skills.md storage columns to governance_responses table"""
    with engine.connect() as conn:
        # Add claude_md_files column
        try:
            conn.execute(text("""
                ALTER TABLE governance_responses
                ADD COLUMN claude_md_files JSON
            """))
            conn.commit()
            print("✓ Added claude_md_files column")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ claude_md_files column already exists")
            else:
                raise
       
        # Add skills_md_files column
        try:
            conn.execute(text("""
                ALTER TABLE governance_responses
                ADD COLUMN skills_md_files JSON
            """))
            conn.commit()
            print("✓ Added skills_md_files column")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ skills_md_files column already exists")
            else:
                raise
 
 
def downgrade():
    """Remove claude.md and skills.md storage columns from governance_responses table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE governance_responses DROP COLUMN claude_md_files"))
            conn.execute(text("ALTER TABLE governance_responses DROP COLUMN skills_md_files"))
            conn.commit()
            print("✓ Removed claude.md and skills.md columns")
        except Exception as e:
            print(f"⚠ Error removing columns: {e}")
 
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add claude.md and skills.md storage")
    print("=" * 60)
    print()
    print("This migration adds two JSON columns to governance_responses:")
    print("  • claude_md_files  - Always loaded for all agents (mandatory)")
    print("  • skills_md_files  - Selectively loaded based on task relevance")
    print()
   
    try:
        upgrade()
        print()
        print("=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Migration failed: {e}")
        print("=" * 60)
        raise
 
 
