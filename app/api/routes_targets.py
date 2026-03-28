from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.db import get_conn
from app.core.security import verify_api_key
from app.models.schemas import TargetCreate
from app.repository import targets as targets_repo

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("")
def list_targets():
    with get_conn() as conn:
        data = targets_repo.list_targets(conn)
        conn.commit()
        return data


@router.post("", dependencies=[Depends(verify_api_key)])
def create_target(payload: TargetCreate):
    with get_conn() as conn:
        target_id = targets_repo.create_target(conn, name=payload.name, seed_url=payload.seed_url)
        conn.commit()
        return {"id": target_id}


@router.delete("/{target_id}", dependencies=[Depends(verify_api_key)])
def delete_target(target_id: int):
    with get_conn() as conn:
        targets_repo.delete_target(conn, target_id)
        conn.commit()
        return {"status": "ok"}
