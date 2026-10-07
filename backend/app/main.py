"""FastAPI app: /api routers, static frontend + SPA fallback."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from . import db
from .config import get_settings
from .routers import approvals, auth, evidence, finance, requests, settlements
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.engine is None:
        db.init_engine()
    db.create_all()
    with Session(db.engine) as s:
        seed_if_empty(s)
    yield


app = FastAPI(title="Nortex Travel Expense", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret,
                   same_site="lax", https_only=False)

for r in (auth.router, requests.router, settlements.router, approvals.router,
          finance.router, evidence.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
               include_in_schema=False)
def api_not_found(rest: str):
    raise HTTPException(404, "Not found")


_static = get_settings().static_dir
if _static.exists():
    if (_static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (_static / path).resolve()
        if path and f.is_file() and _static.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(_static / "index.html")  # SPA fallback
