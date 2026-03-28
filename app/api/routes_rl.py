from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import get_conn
from app.repository import rl_cache

router = APIRouter(prefix="/api/rl", tags=["ransomware-live"])

RL_BASE = settings.ransomware_live_api_base_url.rstrip("/")

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


# ── /info  (DB 캐시에서 조회) ────────────────────────────────────────────────
@router.get("/info")
def rl_info():
    """
    캐시된 ransomware.live /info 메타데이터를 반환한다.
    DB에 데이터가 없으면 404를 반환하므로 프론트에서 /refresh를 먼저 호출해야 한다.
    """
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


# ── /info/refresh  (ransomware.live 직접 호출 → DB 저장) ────────────────────
@router.post("/info/refresh")
async def rl_info_refresh():
    """
    ransomware.live /v2/info를 직접 호출해 DB에 저장(upsert)한다.
    하루 1회 수동 현행화 용도.
    """
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


# ── 기타 프록시 (캐시 없이 직접 조회) ────────────────────────────────────────
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
