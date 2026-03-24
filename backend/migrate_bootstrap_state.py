"""
Migration script to add bootstrap_states table
"""
from sqlalchemy import create_engine
from database import SQLALCHEMY_DATABASE_URL
from models_bootstrap_state import Base as BootstrapBase

def migrate():
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    BootstrapBase.metadata.create_all(bind=engine)
    print("✅ bootstrap_states table created successfully")

if __name__ == "__main__":
    migrate()
