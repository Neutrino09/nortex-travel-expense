from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

engine = None


def init_engine(url: str | None = None):
    """(Re)create the global engine. Tests call this with a temp SQLite file."""
    global engine
    url = url or get_settings().database_url
    if url.startswith("sqlite:///") and ":memory:" not in url:
        from pathlib import Path
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    return engine


def create_all() -> None:
    from . import models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
