"""
Database Initialization: Create all tables and seed default data.
This script sets up a fresh database from scratch in one go.
"""
import os
import sys
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in the import path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import SQLALCHEMY_DATABASE_URL, Base
import models
from config import settings
import agent_service
from governance_scoring import GOVERNANCE_QUESTIONS

def upgrade(db_url=None):
    """Set up WAL mode, create all tables and indexes, and seed default data."""
    target_url = db_url or SQLALCHEMY_DATABASE_URL
    print(f"Target Database URL: {target_url}")
    
    engine = create_engine(
        target_url,
        connect_args={"check_same_thread": False}
    )
    
    # 1. Enable WAL mode for SQLite
    if target_url.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.commit()
            print("✓ SQLite WAL mode enabled")
            
    # 2. Create all tables defined in models.py and models_bootstrap_state.py
    print("Creating all tables and indexes...")
    Base.metadata.create_all(bind=engine)
    print("✓ All tables and indexes created successfully.")
    
    # Create Session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # 3. Seed Default Governance Questions & Options
        q_count = db.query(models.GovernanceQuestion).count()
        if q_count == 0:
            print("Seeding default governance questions...")
            for q_data in GOVERNANCE_QUESTIONS:
                q = models.GovernanceQuestion(
                    id=q_data["id"],
                    dimension=q_data["dimension"],
                    question_text=q_data["question"],
                    order=q_data["id"],
                    is_active=True
                )
                db.add(q)
                db.flush() # ensure ID is set/known
                
                for opt_data in q_data["options"]:
                    opt = models.GovernanceQuestionOption(
                        question_id=q.id,
                        label=opt_data["label"],
                        score=opt_data["score"]
                    )
                    db.add(opt)
            db.commit()
            print(f"✓ Seeded {len(GOVERNANCE_QUESTIONS)} governance questions and options.")
        else:
            print(f"✓ Governance questions already seeded (count: {q_count}).")

        # 4. Seed Default Agents
        agent_count = db.query(models.Agent).filter(models.Agent.project_token.is_(None)).count()
        if agent_count == 0:
            print("Seeding default agents...")
            default_agents = agent_service.get_default_agents()
            for agent in default_agents:
                stored_id = agent["id"] # for default agents, stored_id is same as id (no project token prefix)
                db.add(
                    models.Agent(
                        id=stored_id,
                        name=agent["name"],
                        type=agent.get("type"),
                        project_token=None
                    )
                )
            db.commit()
            print(f"✓ Seeded {len(default_agents)} default agents.")
        else:
            print(f"✓ Default agents already exist (count: {agent_count}).")
            
        # 5. Seed Default OAuth Clients
        oauth_count = db.query(models.OAuthClient).count()
        if oauth_count == 0:
            print("Seeding default OAuth clients...")
            defaults = [
                {
                    "name": "Nxdune",
                    "client_id": settings.oauth_nxdune_client_id,
                    "client_secret": settings.oauth_nxdune_client_secret,
                    "redirect_uri": settings.oauth_nxdune_redirect_uri,
                    "login_url": settings.oauth_nxdune_login_url,
                },
                {
                    "name": "Kaktox",
                    "client_id": settings.oauth_kaktox_client_id,
                    "client_secret": settings.oauth_kaktox_client_secret,
                    "redirect_uri": settings.oauth_kaktox_redirect_uri,
                    "login_url": settings.oauth_kaktox_login_url,
                },
                {
                    "name": "CloudSpx",
                    "client_id": settings.oauth_cloudspx_client_id,
                    "client_secret": settings.oauth_cloudspx_client_secret,
                    "redirect_uri": settings.oauth_cloudspx_redirect_uri,
                    "login_url": settings.oauth_cloudspx_login_url,
                },
            ]
            seeded_oauth = 0
            for plugin in defaults:
                client_id = plugin.get("client_id")
                redirect_uri = plugin.get("redirect_uri")
                client_secret = plugin.get("client_secret")
                if not client_id or not redirect_uri or not client_secret:
                    continue
                db.add(
                    models.OAuthClient(
                        name=plugin["name"],
                        client_id=client_id,
                        client_secret=client_secret,
                        redirect_uri=redirect_uri,
                        login_url=plugin.get("login_url") or None,
                        is_active=True
                    )
                )
                seeded_oauth += 1
            db.commit()
            print(f"✓ Seeded {seeded_oauth} default OAuth clients.")
        else:
            print(f"✓ OAuth clients already exist (count: {oauth_count}).")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Error during database seeding: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Initializing Database Schema & Default Seed Data")
    print("=" * 60)
    try:
        upgrade()
        print()
        print("=" * 60)
        print("✅ Database initialization completed successfully!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Database initialization failed: {e}")
        print("=" * 60)
        sys.exit(1)
