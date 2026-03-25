from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.db import get_conn
from app.core.security import verify_api_key
from app.repository import watchlist as watchlist_repo

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist():
    with get_conn() as conn:
        data = watchlist_repo.list_watchlist(conn)
        conn.commit()
        return data


@router.post("", dependencies=[Depends(verify_api_key)])
def create_watchlist(payload: list[dict] | dict):
    with get_conn() as conn:
        items = payload if isinstance(payload, list) else [payload]
        created_ids = []

        for item in items:
            item_id = watchlist_repo.create_watchlist_item(
                conn,
                item_type=item["type"],
                value=item["pattern"],
                label=item.get("label"),
            )
            created_ids.append(item_id)

        conn.commit()
        return {"ids": created_ids, "count": len(created_ids)}


@router.delete("/{watchlist_id}", dependencies=[Depends(verify_api_key)])
def delete_watchlist_item(watchlist_id: int):
    with get_conn() as conn:
        watchlist_repo.delete_watchlist_item(conn, watchlist_id)
        conn.commit()
        return {"status": "ok"}