"""
Migration: Add face, tags, skills_content, skills_summary, and specialization fields to agents table

This migration adds columns to store custom agent properties including:
- face: Base64 avatar icon
- skills_tags: JSON list of capabilities/specialization tags
- skills_content: Markdown content of the skills
- skills_summary: High-level summary of skills
- specialization: Testing vs Development classification
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Add custom agent columns to agents table"""
    with engine.connect() as conn:
        # Add skills_content column
        try:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_content TEXT"))
            conn.commit()
            print("✓ Added skills_content column to agents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ skills_content column already exists")
            else:
                raise

        # Add skills_summary column
        try:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_summary VARCHAR"))
            conn.commit()
            print("✓ Added skills_summary column to agents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ skills_summary column already exists")
            else:
                raise

        # Add skills_tags column
        try:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_tags JSON"))
            conn.commit()
            print("✓ Added skills_tags column to agents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ skills_tags column already exists")
            else:
                raise

        # Add specialization column
        try:
            conn.execute(text("ALTER TABLE agents ADD COLUMN specialization VARCHAR"))
            conn.commit()
            print("✓ Added specialization column to agents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ specialization column already exists")
            else:
                raise

        # Add face column
        try:
            conn.execute(text("ALTER TABLE agents ADD COLUMN face TEXT"))
            conn.commit()
            print("✓ Added face column to agents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ face column already exists")
            else:
                raise


def downgrade():
    """Remove custom agent columns from agents table"""
    with engine.connect() as conn:
        # Note: SQLite supports DROP COLUMN in newer versions (3.35.0+).
        # We try to drop columns, catching errors if the SQLite version doesn't support it.
        columns_to_drop = ["skills_content", "skills_summary", "skills_tags", "specialization", "face"]
        for col in columns_to_drop:
            try:
                conn.execute(text(f"ALTER TABLE agents DROP COLUMN {col}"))
                conn.commit()
                print(f"✓ Removed {col} column from agents table")
            except Exception as e:
                print(f"⚠ Error removing column {col}: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add custom agent avatar and skills columns")
    print("=" * 60)
    print()
    print("This migration adds the following fields to the agents table:")
    print("  • face            - Base64-encoded agent avatar icon/image")
    print("  • skills_tags     - JSON tags denoting specialization and technical stack")
    print("  • skills_content  - Raw markdown skills uploaded by the end user")
    print("  • skills_summary  - AI-generated summary of agent skills")
    print("  • specialization  - Dev vs Testing classification")
    print()
    print("Features:")
    print("  • Custom avatar display in list rows and custom cards")
    print("  • Smart task routing by Master Agent based on skills/specialization tags")
    print("  • Full sanitization of default system prompts using user skills")
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
