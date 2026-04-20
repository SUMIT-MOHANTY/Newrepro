from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={
        "check_same_thread": False,
        "isolation_level": None  # Autocommit mode for better cross-session visibility
    }
)

# Enable WAL mode for better concurrent access
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.commit()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
