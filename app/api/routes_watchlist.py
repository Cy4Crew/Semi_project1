from __future__ import annotations

import re
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.db import get_conn
from app.core.security import verify_api_key
from app.repository import watchlist as watchlist_repo

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])
logger = logging.getLogger(__name__)


@router.get("")
def list_watchlist():
    with get_conn() as conn:
        data = watchlist_repo.list_watchlist(conn)
        conn.commit()
        return data


@router.post("", dependencies=[Depends(verify_api_key)])
def create_watchlist(payload: list[dict] | dict):
    """watchlist 항목을 등록한다.

    단일 객체 또는 배열 모두 허용.

    지원 필드:
    - type       (필수) : "email" | "domain" | "phone" | ...
    - pattern    : 단일 패턴 문자열 (하위 호환)
    - patterns   : 패턴 문자열 배열 (다중 지원)
    - is_regex   : true 이면 patterns 를 정규표현식으로 처리 (기본 false)
    - label      : 식별용 라벨
    """
    with get_conn() as conn:
        items = payload if isinstance(payload, list) else [payload]
        created_ids: list[int] = []

        for item in items:
            item_type = str(item.get("type", "")).strip().lower()
            label = item.get("label")
            is_regex = bool(item.get("is_regex", False))

            # patterns 배열 우선, 없으면 단일 pattern 하위 호환
            raw_patterns: list[str] = []
            if "patterns" in item and isinstance(item["patterns"], list):
                raw_patterns = [str(p).strip() for p in item["patterns"] if str(p).strip()]
            else:
                single = str(item.get("pattern", item.get("value", ""))).strip()
                if single:
                    raw_patterns = [single]

            if not item_type:
                raise HTTPException(status_code=422, detail="'type' 필드가 필요합니다.")
            if not raw_patterns:
                raise HTTPException(status_code=422, detail="'patterns' 또는 'pattern' 필드가 필요합니다.")

            for pattern in raw_patterns:
                # is_regex 항목은 컴파일 유효성 검증
                if is_regex:
                    try:
                        re.compile(pattern, re.IGNORECASE)
                    except re.error as exc:
                        raise HTTPException(
                            status_code=422,
                            detail=f"잘못된 정규표현식: {pattern!r} — {exc}",
                        )

                item_id = watchlist_repo.create_watchlist_item(
                    conn,
                    item_type=item_type,
                    value=pattern,
                    label=label,
                    is_regex=is_regex,
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
