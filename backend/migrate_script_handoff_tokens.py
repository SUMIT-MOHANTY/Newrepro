from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from datetime import datetime
import os
 
# Get database URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./brd_analyzer.db")
 
engine = create_engine(DATABASE_URL)
Base = declarative_base()
 
def upgrade():
    print("Creating handoff_tokens table...")
   
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS handoff_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id VARCHAR UNIQUE NOT NULL,
                payload TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                used_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
 
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_handoff_tokens_token_id ON handoff_tokens(token_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_handoff_tokens_created_at ON handoff_tokens(created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_handoff_tokens_expires_at ON handoff_tokens(expires_at)"))
 
    print("✅ handoff_tokens table created successfully")
def downgrade():
    """Remove handoff_tokens table"""
    print("Dropping handoff_tokens table...")
   
    with engine.connect() as conn:
        conn.execute("DROP TABLE IF EXISTS handoff_tokens")
        conn.commit()
   
    print("✅ handoff_tokens table dropped successfully")
 
if __name__ == "__main__":
    import sys
   
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
