"""
Database connection setup (SQLite + SQLAlchemy).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app import config

# The engine is the connection to the database.
# check_same_thread=False is needed for SQLite because FastAPI may use
# different threads to handle requests.
engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})

# A "session" is one conversation with the database (add rows, query, commit).
SessionLocal = sessionmaker(bind=engine, autoflush=False)

# All table classes in models.py inherit from this Base.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency: gives each request its own database session
    and always closes it when the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
