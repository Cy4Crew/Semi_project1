from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.db import get_conn
from app.repository import alerts as alerts_repo
from app.repository import extracted_items as extracted_repo
from app.repository import watchlist_hits as hits_repo

router = APIRouter(tags=["results"])


@router.get("/api/hits/recent")
def recent_hits(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    with get_conn() as conn:
        data = hits_repo.list_recent_hits(conn, limit=limit, offset=offset)
        conn.commit()
        return data


@router.get("/api/extracted/recent")
def recent_extracted(
    limit: int = Query(default=100, ge=1, le=500),
):
    with get_conn() as conn:
        data = extracted_repo.list_recent_extracted_items(conn, limit)
        conn.commit()
        return data


@router.get("/api/alerts/recent")
def recent_alerts(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    with get_conn() as conn:
        data = alerts_repo.list_recent_alerts(conn, limit=limit, offset=offset)
        conn.commit()
        return data
