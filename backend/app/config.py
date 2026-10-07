"""Env settings. Real env vars win; otherwise the repo-root .env is read (never printed)."""
import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)  # empty-but-set env var still wins


_load_dotenv(REPO_ROOT / ".env")


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    app_today: str
    session_secret: str
    cookie_secure: bool
    database_url: str
    pack_dir: Path
    fixtures_dir: Path
    storage_dir: Path
    static_dir: Path


def get_settings() -> Settings:
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/app.db")
    if db_url.startswith("sqlite:///./"):  # keep the DB under backend/ regardless of cwd
        db_url = "sqlite:///" + str(BACKEND_DIR / db_url[len("sqlite:///./"):])
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", ""),
        app_today=os.environ.get("APP_TODAY", ""),
        session_secret=os.environ.get("SESSION_SECRET", "change-me"),
        cookie_secure=os.environ.get("COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes"),
        database_url=db_url,
        pack_dir=_resolve(os.environ.get("PACK_DIR", "../pack")),
        fixtures_dir=BACKEND_DIR / "fixtures" / "extractions",
        storage_dir=_resolve(os.environ.get("STORAGE_DIR", "./data/evidence")),
        static_dir=_resolve(os.environ.get("STATIC_DIR", "../frontend/dist")),
    )
