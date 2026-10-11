"""
Shared test setup (pytest "fixtures").

Every test gets:
  - a fresh in-memory SQLite database (so tests never touch certificates.db)
  - a temporary folder for PDFs (so tests never touch the real certificates/ folder)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # In-memory database. StaticPool makes every connection share the same
    # in-memory database (otherwise each connection would get an empty one).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    # Tell FastAPI: "in tests, use the test database instead of the real one"
    app.dependency_overrides[get_db] = override_get_db

    # Save PDFs in a temporary folder that pytest deletes automatically
    monkeypatch.setattr(config, "CERTIFICATES_DIR", tmp_path / "certificates")

    yield TestClient(app)

    app.dependency_overrides.clear()


def make_payload(recipients=None, **extra):
    """Helper that builds a valid request body; tests change only what they need."""
    if recipients is None:
        recipients = [
            {"name": "Asha Raman", "email": "asha@example.com"},
            {"name": "Ravi Kumar", "email": "ravi@example.com"},
        ]
    payload = {"course_name": "Python Workshop 2026", "recipients": recipients}
    payload.update(extra)
    return payload
