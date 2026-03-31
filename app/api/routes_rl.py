from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import get_conn
from app.repository import rl_cache

router = APIRouter(prefix="/api/rl", tags=["ransomware-live"])

RL_BASE = "https://api.ransomware.live/v2"

_HEADERS = {
    "User-Agent": "DarkwebMonitor/2.0",
    "Accept": "application/json",
}


async def _rl_get(path: str) -> dict | list:
    url = f"{RL_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=_HEADERS)
        res.raise_for_status()
        return res.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"ransomware.live timeout: {url}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ransomware.live 연결 오류: {e}")


@router.get("/info")
def rl_info():
    with get_conn() as conn:
        row = rl_cache.get_cache(conn)
        conn.commit()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="캐시 없음 — 우측 상단 '현행화' 버튼을 눌러 데이터를 가져오세요.",
        )

    return JSONResponse(content={
        "payload":    row["payload"],
        "fetched_at": row["fetched_at"],
        "source":     "cache",
    })


@router.post("/info/refresh")
async def rl_info_refresh():
    data = await _rl_get("/info")

    with get_conn() as conn:
        fetched_at = rl_cache.upsert_cache(conn, data)
        conn.commit()

    return JSONResponse(content={
        "status":     "ok",
        "fetched_at": fetched_at,
        "payload":    data,
        "source":     "live",
    })


@router.get("/groups")
async def rl_groups():
    data = await _rl_get("/groups")
    return JSONResponse(content=data)


@router.get("/victims")
async def rl_victims():
    data = await _rl_get("/recentvictims")
    return JSONResponse(content=data)


@router.get("/group/{name}")
async def rl_group_detail(name: str):
    data = await _rl_get(f"/group/{name}")
    return JSONResponse(content=data)