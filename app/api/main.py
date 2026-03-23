from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_hits import router as hits_router
from app.api.routes_pages import router as pages_router
from app.api.routes_targets import router as targets_router
from app.api.routes_watchlist import router as watchlist_router
from app.core.config import settings
from app.core.db import get_conn
from app.core.security import verify_api_key
from app.core.seed_loader import load_targets_file, load_watchlist_file
from app.models.schemas import ReloadResponse

app = FastAPI(title=settings.app_name)
app.include_router(targets_router)
app.include_router(watchlist_router)
app.include_router(hits_router)
app.include_router(pages_router)

if settings.evidence_dir.exists():
    app.mount("/evidence", StaticFiles(directory=str(settings.evidence_dir)), name="evidence")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(Path(settings.ui_dir) / "index.html")


@app.get("/api/summary")
def summary() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM targets) AS targets,
                    (SELECT COUNT(*) FROM pages) AS pages,
                    (SELECT COUNT(*) FROM extracted_items) AS extracted,
                    (SELECT COUNT(*) FROM watchlist_hits) AS hits,
                    (SELECT COUNT(*) FROM alerts) AS alerts
                """
            )
            row = cur.fetchone()
        conn.commit()
        return row


@app.post("/api/reload", response_model=ReloadResponse, dependencies=[Depends(verify_api_key)])
def reload_now() -> ReloadResponse:
    with get_conn() as conn:
        loaded_targets = load_targets_file(conn, settings.targets_seed_path)
        loaded_watchlist = load_watchlist_file(conn, settings.watchlist_seed_path)
        conn.commit()
        return ReloadResponse(status="ok", loaded_targets=loaded_targets, loaded_watchlist=loaded_watchlist)
