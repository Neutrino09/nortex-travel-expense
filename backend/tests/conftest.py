import os

# Must be set BEFORE the app is imported: no network, frozen clock, offline extraction.
os.environ["APP_TODAY"] = "2026-06-22"
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_MODEL"] = ""
os.environ["SESSION_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Fresh temp SQLite, tables created and seeded, for every test."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "evidence"))
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    from app.seed import seed_if_empty
    with Session(db.engine) as s:
        seed_if_empty(s)
    yield db.engine


@pytest.fixture()
def session(tmp_db):
    with Session(tmp_db) as s:
        yield s


@pytest.fixture()
def login_as(tmp_db):
    """login_as('NX-4471') -> a TestClient with its own cookie jar, logged in as that person."""
    clients = []

    def _login(emp_code: str) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        r = c.post("/api/auth/login", json={"emp_code": emp_code})
        assert r.status_code == 200, r.text
        return c

    yield _login
    for c in clients:
        c.__exit__(None, None, None)
