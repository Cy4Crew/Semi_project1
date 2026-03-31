# app/routers/rl.py
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import get_conn
from app.repository import rl_cache

import json
import re
from pathlib import Path   # 🔥 추가

CORP_KEYWORDS = [
    "corp","inc","ltd","group","holdings","company","co",
    "revenue","employees","nda","internal data",
    "financial report","ceo","admin"
]

def classify_category(text: str) -> str:
    t = (text or "").lower()
    if "ransomware" in t:
        return "ransomware"
    if "database" in t or "leak" in t:
        return "database"
    if "drug" in t:
        return "drug"
    if "phishing" in t:
        return "phishing"
    return "general_crime"

def detect_corp(text: str):
    t = (text or "").lower()
    hits = [k for k in CORP_KEYWORDS if k in t]
    return len(hits) > 0, hits

TELEGRAM_RE = re.compile(r"(?:https?://)?t\.me/[a-zA-Z0-9_]+")

def extract_telegram(text: str):
    if not text:
        return []
    return list(set(TELEGRAM_RE.findall(text)))

router = APIRouter(prefix="/api/rl", tags=["ransomware-live"])

RL_BASE = "https://api-pro.ransomware.live"

_HEADERS = {
    "User-Agent": "DarkwebMonitor/2.0",
    "Accept": "application/json",
    "X-API-KEY": settings.ransomware_live_api_key,
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


# ── /info  ────────────────────────────────────────────────
@router.get("/info")
def rl_info():
    with get_conn() as conn:
        row = rl_cache.get_cache(conn)
        conn.commit()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="캐시 없음 — 현행화 버튼을 눌러 데이터를 가져오세요.",
        )

    return JSONResponse(content={
        "payload":    row["payload"],
        "fetched_at": row["fetched_at"],
        "source":     "cache",
    })


# ── /info/refresh ─────────────────────────────────────────
@router.post("/info/refresh")
async def rl_info_refresh():
    data = await _rl_get("/statistics")

    with get_conn() as conn:
        fetched_at = rl_cache.upsert_cache(conn, data)
        conn.commit()

    return JSONResponse(content={
        "status":     "ok",
        "fetched_at": fetched_at,
        "payload":    data,
        "source":     "live",
    })


# ── groups ───────────────────────────────────────────────
@router.get("/groups")
async def rl_groups():
    data = await _rl_get("/groups")
    return JSONResponse(content=data)


# ── victims ──────────────────────────────────────────────
@router.get("/victims")
async def rl_victims(order: str = Query(default="discovered")):
    data = await _rl_get(f"/victims/recent?order={order}")
    victims = data.get("victims", [])

    with get_conn() as conn:
        cur = conn.cursor()

        for v in victims:
            text = f"{v.get('victim','')} {v.get('description','')} {v.get('activity','')}"

            category = classify_category(text)
            is_corp, matched_keywords = detect_corp(text)
            telegrams = extract_telegram(text)

            cur.execute("""
                INSERT INTO darkweb_posts (
                    source, victim, group_name, description,
                    post_url, discovered_at, attack_date,
                    category, is_corp, matched_keywords,
                    telegram_links, raw
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (
                "ransomware.live",
                v.get("victim"),
                v.get("group"),
                v.get("description"),
                v.get("post_url"),
                v.get("discovered"),
                v.get("attackdate"),
                category,
                is_corp,
                matched_keywords,
                telegrams,
                json.dumps(v)
            ))

        conn.commit()

    return JSONResponse(content={
        "status": "ok",
        "count": len(victims),
        "victims": victims
    })


# ── group detail ─────────────────────────────────────────
@router.get("/group/{name}")
async def rl_group_detail(name: str):
    data = await _rl_get(f"/groups/{name}")
    return JSONResponse(content=data)

TARGETS_PATH = Path("targets.json")  # 프로젝트 루트 기준

@router.post("/targets/update")
async def update_targets(payload: dict):
    onions = payload.get("onions", [])

    if not isinstance(onions, list):
        raise HTTPException(status_code=400, detail="onions must be list")

    # 기존 파일 읽기
    if TARGETS_PATH.exists():
        with open(TARGETS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    # 기존 onion set (중복 방지)
    existing_urls = set(item.get("seed_url") for item in existing)

    new_items = []
    for i, onion in enumerate(onions):
        url = f"http://{onion}/"
        if url in existing_urls:
            continue

        new_items.append({
            "seed_url": url,
            "label": f"auto-{len(existing)+len(new_items)+1:03d}"
        })

    merged = existing + new_items

    with open(TARGETS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return {
        "status": "ok",
        "added": len(new_items),
        "total": len(merged)
    }