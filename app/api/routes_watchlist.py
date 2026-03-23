from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.db import get_conn
from app.core.security import verify_api_key
from app.models.schemas import WatchlistCreate
from app.repository import watchlist as watchlist_repo

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist():
    with get_conn() as conn:
        data = watchlist_repo.list_watchlist(conn)
        conn.commit()
        return data


@router.post("", dependencies=[Depends(verify_api_key)])
def create_watchlist_item(payload: WatchlistCreate):
    with get_conn() as conn:
        item_id = watchlist_repo.create_watchlist_item(
            conn,
            item_type=payload.type,
            value=payload.value,
            label=payload.label,
        )
        conn.commit()
        return {"id": item_id}


@router.delete("/{watchlist_id}", dependencies=[Depends(verify_api_key)])
def delete_watchlist_item(watchlist_id: int):
    with get_conn() as conn:
        watchlist_repo.delete_watchlist_item(conn, watchlist_id)
        conn.commit()
        return {"status": "ok"}
