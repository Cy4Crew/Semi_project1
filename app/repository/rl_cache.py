from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def get_cache(conn) -> dict | None:
    """캐시된 /info 데이터 반환. 없으면 None."""
    with conn.cursor() as cur:
        cur.execute("SELECT payload, fetched_at FROM rl_info_cache WHERE id = 1")
        row = cur.fetchone()
    if not row:
        return None
    return {
        "payload": row["payload"],
        "fetched_at": row["fetched_at"].isoformat() if isinstance(row["fetched_at"], datetime) else str(row["fetched_at"]),
    }


def upsert_cache(conn, payload: dict | list) -> str:
    """payload를 DB에 저장(upsert)하고 저장 시각을 반환."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rl_info_cache (id, payload, fetched_at)
            VALUES (1, %s::jsonb, %s)
            ON CONFLICT (id) DO UPDATE
                SET payload    = EXCLUDED.payload,
                    fetched_at = EXCLUDED.fetched_at
            """,
            (json.dumps(payload), now),
        )
    return now.isoformat()
