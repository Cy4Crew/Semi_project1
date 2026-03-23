from __future__ import annotations

from fastapi import APIRouter

from app.core.db import get_conn
from app.repository import pages as pages_repo

router = APIRouter(prefix="/api/pages", tags=["pages"])


@router.get("/recent")
def recent_pages(limit: int = 100):
    with get_conn() as conn:
        data = pages_repo.list_recent_pages(conn, limit)
        conn.commit()
        return data
