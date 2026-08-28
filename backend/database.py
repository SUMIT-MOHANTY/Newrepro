import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "sql_app.db").replace("\\", "/")
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine_kwargs = {
    "pool_size": 30,
    "max_overflow": 60,
    "pool_timeout": 60.0,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 60,
        "isolation_level": None  # Autocommit mode for better cross-session visibility
    }

from sqlalchemy import event

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# Enable WAL mode for better concurrent access and run migrations
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA busy_timeout=60000"))
    
    # Check if project_type and repo columns exist in governance_responses table
    try:
        cursor = conn.execute(text("PRAGMA table_info(governance_responses)"))
        columns = [row[1] for row in cursor.fetchall()]
        if columns:
            if "project_type" not in columns:
                print("Migrating database: Adding project_type column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN project_type VARCHAR DEFAULT 'greenfield'"))
            if "source_repo_url" not in columns:
                print("Migrating database: Adding source_repo_url column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN source_repo_url VARCHAR"))
            if "source_repo_token" not in columns:
                print("Migrating database: Adding source_repo_token column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN source_repo_token VARCHAR"))
            if "dest_repo_url" not in columns:
                print("Migrating database: Adding dest_repo_url column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN dest_repo_url VARCHAR"))
            if "dest_repo_token" not in columns:
                print("Migrating database: Adding dest_repo_token column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN dest_repo_token VARCHAR"))
            if "is_archived" not in columns:
                print("Migrating database: Adding is_archived column to governance_responses")
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
        
        sp_cursor = conn.execute(text("PRAGMA table_info(share_projects)"))
        sp_columns = [row[1] for row in sp_cursor.fetchall()]
        if sp_columns:
            if "is_archived" not in sp_columns:
                print("Migrating database: Adding is_archived column to share_projects")
                conn.execute(text("ALTER TABLE share_projects ADD COLUMN is_archived BOOLEAN DEFAULT 0"))

        # Ensure ai_usage_logs has organization_name and usage_status columns
        ai_cursor = conn.execute(text("PRAGMA table_info(ai_usage_logs)"))
        ai_columns = [row[1] for row in ai_cursor.fetchall()]
        if ai_columns:
            if "organization_name" not in ai_columns:
                print("Migrating database: Adding organization_name column to ai_usage_logs")
                conn.execute(text("ALTER TABLE ai_usage_logs ADD COLUMN organization_name VARCHAR"))
            if "organization_id" not in ai_columns:
                print("Migrating database: Adding organization_id column to ai_usage_logs")
                conn.execute(text("ALTER TABLE ai_usage_logs ADD COLUMN organization_id VARCHAR(36)"))
            if "usage_status" not in ai_columns:
                print("Migrating database: Adding usage_status column to ai_usage_logs")
                conn.execute(text("ALTER TABLE ai_usage_logs ADD COLUMN usage_status VARCHAR NOT NULL DEFAULT 'COMPLETED'"))

        # Ensure organization_wallet has payg_grace_period_months and other required columns
        ow_cursor = conn.execute(text("PRAGMA table_info(organization_wallet)"))
        ow_columns = [row[1] for row in ow_cursor.fetchall()]
        if ow_columns:
            if "payg_grace_period_months" not in ow_columns:
                print("Migrating database: Adding payg_grace_period_months column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_grace_period_months INTEGER NOT NULL DEFAULT 3"))
            if "payg_reserved_spend_usd" not in ow_columns:
                print("Migrating database: Adding payg_reserved_spend_usd column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_reserved_spend_usd NUMERIC(20, 8) NOT NULL DEFAULT 0.0"))
            if "payg_billing_email" not in ow_columns:
                print("Migrating database: Adding payg_billing_email column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_billing_email VARCHAR"))
            if "payg_soft_limit_usd" not in ow_columns:
                print("Migrating database: Adding payg_soft_limit_usd column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_soft_limit_usd NUMERIC(10, 2)"))
            if "payg_hard_limit_usd" not in ow_columns:
                print("Migrating database: Adding payg_hard_limit_usd column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_hard_limit_usd NUMERIC(10, 2)"))
            if "payg_current_spend_usd" not in ow_columns:
                print("Migrating database: Adding payg_current_spend_usd column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN payg_current_spend_usd NUMERIC(20, 8) NOT NULL DEFAULT 0.0"))
            if "organization_id" not in ow_columns:
                print("Migrating database: Adding organization_id column to organization_wallet")
                conn.execute(text("ALTER TABLE organization_wallet ADD COLUMN organization_id VARCHAR(36)"))
    except Exception as e:
        print(f"Database migration check skipped: {e}")
        
    conn.commit()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
